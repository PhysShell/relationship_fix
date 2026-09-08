{-# LANGUAGE OverloadedStrings #-}

-- | Which packages may be shown to anyone, and what exactly one person was
-- issued.
--
-- Two files, two different authorities:
--
--   * the package registry says what a package's status is: a frozen package
--     is refused at runtime no matter what any other file says, and a package
--     the registry does not name does not exist as far as the server is
--     concerned;
--   * an issuance record says what one pseudonymous annotator was given: the
--     package, the presentation file and its hash, the instruction document
--     and its hash, the ontology and its hash. The sealed manifest describes
--     the research artifact; the issuance record describes what a person saw.
--     The server follows the record and never "chooses" an instruction path.
--
-- Every hash in a record is re-derived from the files at load time and every
-- disagreement is a refusal to start. A binding that cannot be proven is not
-- served with a warning; it is not served.
module Registry
  ( PackageStatus (..)
  , RegistryEntry (..)
  , Registry (..)
  , parseRegistry
  , IssuanceRecord (..)
  , parseIssuanceRecord
  , Binding (..)
  , BindingConfig (..)
  , BindingFault (..)
  , renderBindingFault
  , loadBindings
  , tokenSha
  ) where

import Control.Exception (IOException, try)
import Control.Monad (forM, unless, when)
import qualified Data.Aeson as A
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KM
import Data.Aeson.Types (Parser, parseEither, (.:), (.:?), (.!=))
import qualified Data.ByteString as BS
import Data.List (isSuffixOf, sort)
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import Domain (Language, parseLanguage)
import Ontology (OntologyLabel, parseOntology)
import Packet
import System.Directory (doesDirectoryExist, doesFileExist, listDirectory)
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
      pin <- o .:? "checksums_sha256"
      pure RegistryEntry
        { reDir = T.unpack dir
        , reStatus = case status of
            "issuable" -> Issuable
            "frozen_non_issuable" -> FrozenNonIssuable
            other -> OtherStatus other
        , reChecksumsSha = pin
        }
    entryParser _ = fail "registry entry is not an object"

data IssuanceRecord = IssuanceRecord
  { irRecordFile :: FilePath
  , irPackageId :: Text
  , irAnnotatorId :: Text
  , irTokenSha :: Text
  , irPackageDir :: FilePath
  , irItemsSha :: Text
  , irChecksumsSha :: Text
  , irPresentationFile :: FilePath
  , irPresentationSha :: Text
  , irInstructionsFile :: FilePath
  , irInstructionsSha :: Text
  , irOntologyFile :: FilePath
  , irOntologyVersion :: Text
  , irOntologySha :: Text
  , irActiveLabels :: [Text]
  , irUiLanguage :: Text
  , irIssuedAt :: Text
  , irIssuedBy :: Text
  }
  deriving stock (Eq, Show)

parseIssuanceRecord :: FilePath -> BS.ByteString -> Either Text IssuanceRecord
parseIssuanceRecord file raw = do
  value <- either (Left . T.pack) Right (A.eitherDecodeStrict raw)
  either (Left . T.pack) Right (parseEither recordParser value)
  where
    recordParser :: A.Value -> Parser IssuanceRecord
    recordParser (A.Object o) = do
      schema <- o .: "schema_version"
      unless (schema == ("rf.issuance-record.v1" :: Text)) $ fail "unknown issuance record schema_version"
      packageId <- o .: "package_id"
      annotatorId <- o .: "annotator_id"
      tokenSha256 <- o .: "token_sha256"
      package <- o .: "package"
      (dir, itemsSha, checksumsSha) <- case package of
        A.Object p -> (,,) <$> p .: "dir" <*> p .: "items_sha256" <*> p .: "checksums_sha256"
        _ -> fail "package is not an object"
      presentation <- o .: "presentation"
      (presFile, presSha) <- case presentation of
        A.Object p -> (,) <$> p .: "file" <*> p .: "sha256"
        _ -> fail "presentation is not an object"
      instructions <- o .: "instructions"
      (insFile, insSha) <- case instructions of
        A.Object p -> (,) <$> p .: "file" <*> p .: "sha256"
        _ -> fail "instructions is not an object"
      ontology <- o .: "ontology"
      (ontFile, ontVersion, ontSha, active) <- case ontology of
        A.Object p -> (,,,) <$> p .: "file" <*> p .: "version" <*> p .: "sha256" <*> p .:? "active_labels" .!= []
        _ -> fail "ontology is not an object"
      uiLanguage <- o .:? "ui_language" .!= "ru"
      issuedAt <- o .: "issued_at"
      issuedBy <- o .:? "issued_by" .!= "facilitator"
      pure IssuanceRecord
        { irRecordFile = file
        , irPackageId = packageId
        , irAnnotatorId = annotatorId
        , irTokenSha = T.toLower tokenSha256
        , irPackageDir = T.unpack dir
        , irItemsSha = T.toLower itemsSha
        , irChecksumsSha = T.toLower checksumsSha
        , irPresentationFile = T.unpack presFile
        , irPresentationSha = T.toLower presSha
        , irInstructionsFile = T.unpack insFile
        , irInstructionsSha = T.toLower insSha
        , irOntologyFile = T.unpack ontFile
        , irOntologyVersion = ontVersion
        , irOntologySha = T.toLower ontSha
        , irActiveLabels = active
        , irUiLanguage = uiLanguage
        , irIssuedAt = issuedAt
        , irIssuedBy = issuedBy
        }
    recordParser _ = fail "issuance record is not an object"

-- | Everything a session needs, proven at load time: the record, the parsed
-- packet in the annotator's order, the exact instruction text and the pinned
-- ontology labels.
data Binding = Binding
  { bindRecord :: IssuanceRecord
  , bindItems :: [PresentedItem]
  , bindInstructions :: Text
  , bindOntology :: [OntologyLabel]
  , bindUiLanguage :: Language
  }

data BindingConfig = BindingConfig
  { bcRepoRoot :: FilePath
    -- ^ Base for every relative path in the registry and the records.
  , bcRegistryFile :: FilePath
  , bcIssuanceDir :: FilePath
    -- ^ Directory of @*.json@ issuance records. May be absent: then nothing is
    -- issued and only the dogfood surface (if enabled) exists.
  }
  deriving stock (Eq, Show)

data BindingFault
  = RegistryUnreadable FilePath Text
  | RecordUnreadable FilePath Text
  | RegistryUnknownPackage FilePath Text
  | PackageNotIssuable FilePath Text PackageStatus
  | RecordDirMismatch FilePath FilePath FilePath
  | SealMissing FilePath FilePath
  | SealPinMissing FilePath Text
  | SealPinMismatch FilePath Text Text Text
  | SealUnreadable FilePath Text
  | SealEntryMissing FilePath Text
  | SealEntryMismatch FilePath Text Text Text
  | FileHashMismatch FilePath Text Text Text
  | FileMissing FilePath Text
  | PresentationInvalid FilePath PacketFault
  | OntologyInvalid FilePath Text
  | UiLanguageUnknown FilePath Text
  | DuplicateToken FilePath FilePath
  | DuplicateAnnotator FilePath Text Text
  deriving stock (Eq, Show)

renderBindingFault :: BindingFault -> Text
renderBindingFault fault = case fault of
  RegistryUnreadable f e -> "package registry " <> p f <> ": " <> e
  RecordUnreadable f e -> "issuance record " <> p f <> ": " <> e
  RegistryUnknownPackage f pid -> "issuance record " <> p f <> ": package " <> pid <> " is not in the registry — unknown packages are not served"
  PackageNotIssuable f pid status -> "issuance record " <> p f <> ": package " <> pid <> " has status " <> T.pack (show status) <> " — not issuable"
  RecordDirMismatch f a b -> "issuance record " <> p f <> ": package dir " <> p a <> " differs from the registry's " <> p b
  SealMissing f path -> "issuance record " <> p f <> ": no CHECKSUMS.sha256 at " <> p path <> " — an unsealed package is not served"
  SealPinMissing f pid -> "registry: issuable package " <> pid <> " has no checksums_sha256 pin (" <> p f <> ")"
  SealPinMismatch f who expected actual -> "issuance record " <> p f <> ": CHECKSUMS.sha256 hash " <> short actual <> " differs from " <> who <> " pin " <> short expected
  SealUnreadable f e -> "CHECKSUMS.sha256 for " <> p f <> ": " <> e
  SealEntryMissing f name -> "issuance record " <> p f <> ": CHECKSUMS.sha256 has no entry for " <> name
  SealEntryMismatch f name recorded sealed -> "issuance record " <> p f <> ": " <> name <> " recorded as " <> short recorded <> " but sealed as " <> short sealed
  FileHashMismatch f name recorded actual -> "issuance record " <> p f <> ": " <> name <> " hashes to " <> short actual <> ", record says " <> short recorded
  FileMissing f name -> "issuance record " <> p f <> ": file missing: " <> name
  PresentationInvalid f e -> "issuance record " <> p f <> ": " <> renderPacketFault e
  OntologyInvalid f e -> "issuance record " <> p f <> ": ontology: " <> e
  UiLanguageUnknown f l -> "issuance record " <> p f <> ": ui_language " <> l <> " is not ru|en"
  DuplicateToken f g -> "issuance records " <> p f <> " and " <> p g <> " share a token"
  DuplicateAnnotator f pid a -> "issuance record " <> p f <> ": annotator " <> a <> " already issued for " <> pid
  where
    p = T.pack
    short h = T.take 12 h <> "…"

-- | The hex sha256 of a raw token as presented in a URL. Tokens are never
-- stored; only this is.
tokenSha :: Text -> Text
tokenSha = sha256Text

-- | Load and prove every issuance record. Returns the bindings keyed by token
-- hash, or every fault found. Nothing partial: one bad record and the server
-- does not start, because "some annotators bound correctly" is not a state a
-- research instrument should be in without somebody noticing.
loadBindings :: BindingConfig -> IO (Either [BindingFault] (Map.Map Text Binding))
loadBindings cfg = do
  registryRaw <- try (BS.readFile (bcRegistryFile cfg))
  case registryRaw of
    Left err -> pure (Left [RegistryUnreadable (bcRegistryFile cfg) (T.pack (show (err :: IOException)))])
    Right bytes -> case parseRegistry bytes of
      Left err -> pure (Left [RegistryUnreadable (bcRegistryFile cfg) err])
      Right registry -> do
        hasDir <- doesDirectoryExist (bcIssuanceDir cfg)
        files <- if hasDir
          then sort . filter (".json" `isSuffixOf`) <$> listDirectory (bcIssuanceDir cfg)
          else pure []
        results <- forM files $ \name -> loadRecord cfg registry (bcIssuanceDir cfg </> name)
        let faults = concat [fs | Left fs <- results]
            bindings = [b | Right b <- results]
        if not (null faults)
          then pure (Left faults)
          else pure (assemble bindings)
  where
    assemble bindings =
      let step (acc, seen) b =
            let rec = bindRecord b
                key = irTokenSha rec
                who = (irPackageId rec, irAnnotatorId rec)
             in case (Map.lookup key acc, Map.lookup who seen) of
                  (Just other, _) -> Left [DuplicateToken (irRecordFile rec) (irRecordFile (bindRecord other))]
                  (_, Just _) -> Left [DuplicateAnnotator (irRecordFile rec) (irPackageId rec) (irAnnotatorId rec)]
                  _ -> Right (Map.insert key b acc, Map.insert who () seen)
          go acc [] = Right (fst acc)
          go acc (b : rest) = step acc b >>= \acc' -> go acc' rest
       in go (Map.empty, Map.empty) bindings

loadRecord :: BindingConfig -> Registry -> FilePath -> IO (Either [BindingFault] Binding)
loadRecord cfg (Registry registry) file = do
  raw <- try (BS.readFile file)
  case raw of
    Left err -> pure (Left [RecordUnreadable file (T.pack (show (err :: IOException)))])
    Right bytes -> case parseIssuanceRecord file bytes of
      Left err -> pure (Left [RecordUnreadable file err])
      Right rec -> proveRecord cfg registry rec

proveRecord :: BindingConfig -> Map.Map Text RegistryEntry -> IssuanceRecord -> IO (Either [BindingFault] Binding)
proveRecord cfg registry rec = do
  let file = irRecordFile rec
      root = bcRepoRoot cfg
  case Map.lookup (irPackageId rec) registry of
    Nothing -> pure (Left [RegistryUnknownPackage file (irPackageId rec)])
    Just entry
      | reStatus entry /= Issuable -> pure (Left [PackageNotIssuable file (irPackageId rec) (reStatus entry)])
      | reDir entry /= irPackageDir rec -> pure (Left [RecordDirMismatch file (irPackageDir rec) (reDir entry)])
      | otherwise -> case reChecksumsSha entry of
          Nothing -> pure (Left [SealPinMissing (bcRegistryFile cfg) (irPackageId rec)])
          Just pin -> do
            let packageDir = root </> reDir entry
                sealPath = packageDir </> "CHECKSUMS.sha256"
            sealed <- doesFileExist sealPath
            if not sealed
              then pure (Left [SealMissing file sealPath])
              else do
                sealBytes <- BS.readFile sealPath
                let sealSha = sha256Hex sealBytes
                if sealSha /= T.toLower pin
                  then pure (Left [SealPinMismatch file "registry" (T.toLower pin) sealSha])
                  else if sealSha /= irChecksumsSha rec
                    then pure (Left [SealPinMismatch file "record" (irChecksumsSha rec) sealSha])
                    else case parseChecksums (TE.decodeUtf8 sealBytes) of
                      Left err -> pure (Left [SealUnreadable file err])
                      Right checksums -> proveFiles cfg rec packageDir checksums

proveFiles :: BindingConfig -> IssuanceRecord -> FilePath -> Checksums -> IO (Either [BindingFault] Binding)
proveFiles cfg rec packageDir checksums = do
  let file = irRecordFile rec
      root = bcRepoRoot cfg
      presName = T.pack (irPresentationFile rec)
  -- Identity of the package the person was issued: the sealed hash of
  -- items.jsonl, read from the seal and never from the file itself.
  let identityFaults = case checksumFor "items.jsonl" checksums of
        Nothing -> [SealEntryMissing file "items.jsonl"]
        Just sealed | sealed /= irItemsSha rec -> [SealEntryMismatch file "items.jsonl" (irItemsSha rec) sealed]
        _ -> []
      presSealFaults = case checksumFor presName checksums of
        Nothing -> [SealEntryMissing file presName]
        Just sealed | sealed /= irPresentationSha rec -> [SealEntryMismatch file presName (irPresentationSha rec) sealed]
        _ -> []
  presentation <- hashedFile file (packageDir </> irPresentationFile rec) presName (irPresentationSha rec)
  instructions <- hashedFile file (root </> irInstructionsFile rec) (T.pack (irInstructionsFile rec)) (irInstructionsSha rec)
  ontology <- hashedFile file (root </> irOntologyFile rec) (T.pack (irOntologyFile rec)) (irOntologySha rec)
  let early = identityFaults ++ presSealFaults ++ concat [fs | Left fs <- [presentation, instructions, ontology]]
  case (presentation, instructions, ontology) of
    (Right presBytes, Right insBytes, Right ontBytes) | null early ->
      let parsedItems = either (Left . pure . PresentationInvalid file) Right (parsePresentation presBytes)
          parsedOntology = either (Left . pure . OntologyInvalid file) Right (parseOntology (irActiveLabels rec) ontBytes)
          uiLanguage = maybe (Left [UiLanguageUnknown file (irUiLanguage rec)]) Right (parseLanguage (irUiLanguage rec))
       in pure $ do
            items <- parsedItems
            (version, labels) <- parsedOntology
            when (version /= irOntologyVersion rec) $
              Left [OntologyInvalid file ("file declares " <> version <> ", record says " <> irOntologyVersion rec)]
            lang <- uiLanguage
            pure Binding
              { bindRecord = rec
              , bindItems = items
              , bindInstructions = TE.decodeUtf8 insBytes
              , bindOntology = labels
              , bindUiLanguage = lang
              }
    _ -> pure (Left early)

hashedFile :: FilePath -> FilePath -> Text -> Text -> IO (Either [BindingFault] BS.ByteString)
hashedFile record path name expected = do
  exists <- doesFileExist path
  if not exists
    then pure (Left [FileMissing record name])
    else do
      bytes <- BS.readFile path
      let actual = sha256Hex bytes
      pure $ if actual == expected then Right bytes else Left [FileHashMismatch record name expected actual]
