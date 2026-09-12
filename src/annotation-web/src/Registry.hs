{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

-- | Which package may be shown to anyone, and the sealed content it serves.
--
-- Simple pilot mode (2026-09-12): one shared link. There is no per-person
-- issuance record, no bearer token, no eligibility gate at the door -- the
-- pilot is two people the facilitator invited directly, and the earlier
-- issuance/bearer-token machinery (still in git history, `research/python/
-- metrics/issuance.py`, and the "controlled pilot mode" note in the runbook)
-- turned out to buy more assurance than a two-person pilot needs. What is
-- still worth proving at start, and still proven here: the package this
-- process would serve is genuinely the sealed one, not a modified copy --
-- a frozen or unsealed package is refused before it ever reaches a browser.
--
-- The registry says which package is issuable and pins its seal; the sealed
-- package's own manifest names its annotator slots, active ontology labels
-- and ontology version. Every hash here is re-derived from the files at load
-- time; a disagreement is a refusal to start, not a warning.
module Registry
  ( PackageStatus (..)
  , RegistryEntry (..)
  , Registry (..)
  , parseRegistry
  , PilotSlot (..)
  , PilotConfig (..)
  , RegistryFault (..)
  , renderRegistryFault
  , loadPilotConfig
  ) where

import Control.Exception (IOException, try)
import Control.Monad (forM, unless)
import qualified Data.Aeson as A
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KM
import Data.Aeson.Types (Parser, parseEither, (.:))
import qualified Data.ByteString as BS
import qualified Data.Text as T
import Data.Text (Text)
import Data.Either (partitionEithers)
import qualified Data.Map.Strict as Map
import qualified Data.Text.Encoding as TE
import Ontology (OntologyLabel, parseOntology)
import Packet (PresentedItem, checksumFor, parseChecksums, parsePresentation, renderPacketFault, sha256Hex)
import System.Directory (doesFileExist)
import System.FilePath ((</>))

data PackageStatus
  = Issuable
  | FrozenNonIssuable
  | OtherStatus Text
  deriving stock (Eq, Show)

data RegistryEntry = RegistryEntry
  { reDir :: FilePath
  , reStatus :: PackageStatus
  , reChecksumsSha :: Maybe Text
  , reInstructionsFile :: Maybe FilePath
  , reInstructionsSha :: Maybe Text
  }
  deriving stock (Eq, Show)

newtype Registry = Registry (Map.Map Text RegistryEntry)
  deriving stock (Eq, Show)

parseRegistry :: BS.ByteString -> Either Text Registry
parseRegistry raw = do
  value <- either (Left . T.pack) Right (A.eitherDecodeStrict raw)
  either (Left . T.pack) Right (parseEither registryParser value)
  where
    registryParser :: A.Value -> Parser Registry
    registryParser (A.Object o) = do
      schema <- o .: "schema_version"
      unless (schema == ("rf.package-registry.v1" :: Text)) $ fail "unknown registry schema_version"
      packages <- o .: "packages"
      entries <- case packages of
        A.Object ps -> forM (KM.toList ps) $ \(k, v) -> (,) (Key.toText k) <$> entryParser v
        _ -> fail "packages is not an object"
      pure (Registry (Map.fromList entries))
    registryParser _ = fail "registry is not an object"
    entryParser :: A.Value -> Parser RegistryEntry
    entryParser (A.Object o) = do
      dir <- o .: "dir"
      status <- o .: "status"
      pin <- o A..:? "checksums_sha256"
      instructions <- o A..:? "instructions_file"
      instructionsSha <- o A..:? "instructions_sha256"
      pure RegistryEntry
        { reDir = T.unpack dir
        , reStatus = case status of
            "issuable" -> Issuable
            "frozen_non_issuable" -> FrozenNonIssuable
            other -> OtherStatus other
        , reChecksumsSha = pin
        , reInstructionsFile = T.unpack <$> instructions
        , reInstructionsSha = instructionsSha
        }
    entryParser _ = fail "registry entry is not an object"

-- | One annotator's presented items, in the order the sealed presentation
-- file has them.
data PilotSlot = PilotSlot
  { psAnnotatorId :: Text
  , psItems :: [PresentedItem]
  }

-- | Everything the server proved about the one issuable package at start.
data PilotConfig = PilotConfig
  { pcPackageId :: Text
  , pcSlots :: [PilotSlot]
  , pcInstructions :: Text
  , pcOntologyVersion :: Text
  , pcOntology :: [OntologyLabel]
  }

data RegistryFault
  = RegistryUnreadable FilePath Text
  | NoIssuablePackage FilePath
  | MultipleIssuablePackages FilePath [Text]
  | SealPinMissing Text
  | SealMissing Text FilePath
  | SealPinMismatch Text Text Text
  | SealUnreadable Text Text
  | SealEntryMissing Text Text
  | FileHashMismatch Text Text Text Text
  | FileMissing Text Text
  | ManifestUnreadable Text Text
  | PresentationInvalid Text Text
  | OntologyInvalid Text Text
  deriving stock (Eq, Show)

renderRegistryFault :: RegistryFault -> Text
renderRegistryFault fault = case fault of
  RegistryUnreadable f e -> "package registry " <> p f <> ": " <> e
  NoIssuablePackage f -> "package registry " <> p f <> ": no package has status issuable"
  MultipleIssuablePackages f ids -> "package registry " <> p f <> ": more than one issuable package (" <> T.intercalate ", " ids <> ") -- simple pilot mode serves exactly one"
  SealPinMissing pid -> "registry: issuable package " <> pid <> " has no checksums_sha256 pin"
  SealMissing pid path -> "package " <> pid <> ": no CHECKSUMS.sha256 at " <> p path <> " -- an unsealed package is not served"
  SealPinMismatch pid expected actual -> "package " <> pid <> ": CHECKSUMS.sha256 hashes to " <> short actual <> ", registry pins " <> short expected
  SealUnreadable pid e -> "package " <> pid <> ": CHECKSUMS.sha256: " <> e
  SealEntryMissing pid name -> "package " <> pid <> ": CHECKSUMS.sha256 has no entry for " <> name
  FileHashMismatch pid name expected actual -> "package " <> pid <> ": " <> name <> " hashes to " <> short actual <> ", seal says " <> short expected
  FileMissing pid name -> "package " <> pid <> ": file missing: " <> name
  ManifestUnreadable pid e -> "package " <> pid <> ": pilot-manifest.json: " <> e
  PresentationInvalid pid e -> "package " <> pid <> ": " <> e
  OntologyInvalid pid e -> "package " <> pid <> ": ontology: " <> e
  where
    p = T.pack
    short h = T.take 12 h <> "…"

-- | Find the one issuable package, prove its seal, load every presentation
-- file its manifest names as a slot, its instruction document (from the
-- registry, not the sealed manifest) and its pinned ontology. Nothing
-- partial: any single fault refuses the whole load.
loadPilotConfig :: FilePath -> FilePath -> IO (Either [RegistryFault] PilotConfig)
loadPilotConfig repoRoot registryFile = do
  registryRaw <- try (BS.readFile registryFile)
  case registryRaw of
    Left err -> pure (Left [RegistryUnreadable registryFile (T.pack (show (err :: IOException)))])
    Right bytes -> case parseRegistry bytes of
      Left err -> pure (Left [RegistryUnreadable registryFile err])
      Right (Registry registry) ->
        case [(k, v) | (k, v) <- Map.toList registry, reStatus v == Issuable] of
          [] -> pure (Left [NoIssuablePackage registryFile])
          [(pid, entry)] -> proveOne pid entry
          many -> pure (Left [MultipleIssuablePackages registryFile (map fst many)])
  where
    proveOne pid entry = case reChecksumsSha entry of
      Nothing -> pure (Left [SealPinMissing pid])
      Just pin -> do
        let packageDir = repoRoot </> reDir entry
            sealPath = packageDir </> "CHECKSUMS.sha256"
        sealed <- doesFileExist sealPath
        if not sealed
          then pure (Left [SealMissing pid sealPath])
          else do
            sealBytes <- BS.readFile sealPath
            let sealSha = sha256Hex sealBytes
            if sealSha /= T.toLower pin
              then pure (Left [SealPinMismatch pid (T.toLower pin) sealSha])
              else case parseChecksums (TE.decodeUtf8 sealBytes) of
                Left err -> pure (Left [SealUnreadable pid err])
                Right checksums -> proveManifest pid entry packageDir checksums

    proveManifest pid entry packageDir checksums =
      hashedFile pid (packageDir </> "pilot-manifest.json") "pilot-manifest.json" checksums >>= \case
        Left faults -> pure (Left faults)
        Right manifestBytes -> case A.eitherDecodeStrict manifestBytes of
          Left err -> pure (Left [ManifestUnreadable pid (T.pack err)])
          Right value -> case parseEither manifestParser value of
            Left err -> pure (Left [ManifestUnreadable pid (T.pack err)])
            Right (annotators, activeLabels, ontologyVersion, ontologySha) ->
              proveSlots pid entry packageDir checksums annotators activeLabels ontologyVersion ontologySha

    manifestParser :: A.Value -> Parser ([Text], [Text], Text, Text)
    manifestParser (A.Object o) = (,,,) <$> o .: "annotators" <*> o .: "active_labels" <*> o .: "ontology_version" <*> o .: "ontology_sha256"
    manifestParser _ = fail "pilot-manifest.json is not an object"

    proveSlots pid entry packageDir checksums annotators activeLabels ontologyVersion ontologySha = do
      slots <- forM annotators $ \annotator -> do
        let presName = "presentation/" <> annotator <> ".jsonl"
        hashedFile pid (packageDir </> T.unpack presName) presName checksums >>= \case
          Left faults -> pure (Left faults)
          Right presBytes -> case parsePresentation presBytes of
            Left err -> pure (Left [PresentationInvalid pid (renderPacketFault err)])
            Right items -> pure (Right (PilotSlot annotator items))
      let (faults, ok) = partitionEithers slots
      if not (null faults)
        then pure (Left (concat faults))
        else proveInstructionsAndOntology pid entry activeLabels ontologyVersion ontologySha ok

    proveInstructionsAndOntology pid entry activeLabels ontologyVersion ontologySha slots = do
      case (,) <$> reInstructionsFile entry <*> reInstructionsSha entry of
        Nothing -> pure (Left [FileMissing pid "registry.instructions_file/instructions_sha256"])
        Just (insRelPath, insSha) -> do
          let insPath = repoRoot </> insRelPath
          insExists <- doesFileExist insPath
          if not insExists
            then pure (Left [FileMissing pid (T.pack insRelPath)])
            else do
              insBytes <- BS.readFile insPath
              let actualInsSha = sha256Hex insBytes
              if actualInsSha /= T.toLower insSha
                then pure (Left [FileHashMismatch pid (T.pack insRelPath) (T.toLower insSha) actualInsSha])
                else proveOntology pid activeLabels ontologyVersion ontologySha insBytes slots

    proveOntology pid activeLabels ontologyVersion ontologySha insBytes slots = do
      let ontFile = "data/ontology" </> T.unpack ontologyVersion <> ".json"
          ontPath = repoRoot </> ontFile
      ontExists <- doesFileExist ontPath
      if not ontExists
        then pure (Left [FileMissing pid (T.pack ontFile)])
        else do
          ontBytes <- BS.readFile ontPath
          let actualOntSha = sha256Hex ontBytes
          if actualOntSha /= T.toLower ontologySha
            then pure (Left [FileHashMismatch pid (T.pack ontFile) (T.toLower ontologySha) actualOntSha])
            else case parseOntology activeLabels ontBytes of
                      Left err -> pure (Left [OntologyInvalid pid err])
                      Right (declaredVersion, labels)
                        | declaredVersion /= ontologyVersion ->
                            pure (Left [OntologyInvalid pid ("file declares " <> declaredVersion <> ", manifest says " <> ontologyVersion)])
                        | otherwise -> pure $ Right PilotConfig
                            { pcPackageId = pid
                            , pcSlots = slots
                            , pcInstructions = TE.decodeUtf8 insBytes
                            , pcOntologyVersion = ontologyVersion
                            , pcOntology = labels
                            }

    hashedFile pid path name checksums = case checksumFor name checksums of
      Nothing -> pure (Left [SealEntryMissing pid name])
      Just expected -> do
        exists <- doesFileExist path
        if not exists
          then pure (Left [FileMissing pid name])
          else do
            bytes <- BS.readFile path
            let actual = sha256Hex bytes
            pure $ if actual == expected then Right bytes else Left [FileHashMismatch pid name expected actual]

