{-# LANGUAGE OverloadedStrings #-}

-- | The pilot surface, judged against the web cutover gates: a package is
-- served only through the registry and its seal; a token resolves to exactly
-- one proven packet; the renderer shows exactly those bytes in exactly that
-- order and never a canonical id; the collector stores exactly what was typed
-- and only for its own session; feedback is present on every exported line
-- and empty means empty; the session survives a restart; the export is the
-- canonical layer, complete or refused.
module PilotSpec
  ( Fixture (..)
  , makeFixture
  , RealFixture (..)
  , makeRealFixture
  , pilotSite
  , loaderSpec
  , webSpec
  , realPackageSpec
  ) where

import Control.Monad (forM_, unless)
import Control.Monad.IO.Class (liftIO)
import qualified Data.Aeson as A
import Data.Aeson ((.=), object)
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KeyMap
import qualified Data.ByteString as BS
import qualified Data.ByteString.Char8 as BC
import qualified Data.ByteString.Lazy as BL
import Data.Foldable (toList)
import Data.IORef (IORef, atomicModifyIORef', newIORef, readIORef, writeIORef)
import qualified Data.Map.Strict as Map
import Data.Maybe (fromMaybe, mapMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import Database.Persist.Sql (Entity (..), Filter, SelectOpt (Asc), entityVal, runSqlPool, selectList, (==.))
import Export
import qualified Network.HTTP.Types as HTTP
import qualified Network.Wai as Wai
import Network.Wai.Test (SResponse (..), runSession, simpleBody)
import qualified Network.Wai.Test as WT
import Packet
import Registry
import Schema (migrateDatabase)
import Server
import System.Directory (copyFile, createDirectoryIfMissing, doesDirectoryExist, doesFileExist, listDirectory, removeFile)
import System.FilePath (takeDirectory, (</>))
import System.IO.Temp (withSystemTempDirectory)
import Test.Hspec
import Yesod (toWaiApp)
import Yesod.Test

-- ---------------------------------------------------------------- fixtures

data Fixture = Fixture
  { fxRoot :: FilePath
  , fxConfig :: BindingConfig
  , fxToken :: Text
  , fxToken2 :: Text
  , fxItems :: [PresentedItem]
    -- ^ annotator-1's packet, in its order
  , fxItems2 :: [PresentedItem]
    -- ^ annotator-2's packet: same rows, different order
  , fxInstructions :: Text
  , fxLastDb :: IORef FilePath
  }

fixtureItems :: [PresentedItem]
fixtureItems =
  [ PresentedItem "item-aaaaaa" "ru"
      [ PresentedMessage "item-aaaaaa-m1" "a" "Привет, где ключи?"
      , PresentedMessage "item-aaaaaa-m2" "b" "На крючке, где всегда."
      ] "item-aaaaaa-m2"
  , PresentedItem "item-bbbbbb" "ru"
      [ PresentedMessage "item-bbbbbb-m1" "b" "Я задержусь."
      , PresentedMessage "item-bbbbbb-m2" "a" "Опять?"
      , PresentedMessage "item-bbbbbb-m3" "b" "Ну извини, работа такая."
      ] "item-bbbbbb-m3"
  , PresentedItem "item-cccccc" "en"
      [ PresentedMessage "item-cccccc-m1" "a" "ok whatever, do what you want"
      ] "item-cccccc-m1"
  ]

presentationLine :: PresentedItem -> A.Value
presentationLine item = object
  [ "schema_version" .= ("rf.pilot-item.v1" :: Text)
  , "item_id" .= piId item
  , "language" .= piLanguage item
  , "messages" .= [object ["message_id" .= pmId m, "author" .= pmAuthor m, "text" .= pmText m] | m <- piMessages item]
  , "target_message_id" .= piTargetId item
  ]

jsonl :: [A.Value] -> BS.ByteString
jsonl values = BL.toStrict (BL.concat [A.encode v <> "\n" | v <- values])

activeLabels :: [Text]
activeLabels = ["B.BLAME_CRITICISM", "B.PRESSURE_FOR_CHANGE", "B.VALIDATION", "B.REPAIR_ATTEMPT", "B.AVOIDANCE_TOPIC_SHIFT"]

fixtureOntology :: BS.ByteString
fixtureOntology = BL.toStrict $ A.encode $ object
  [ "ontology_version" .= ("behavior-fixture" :: Text)
  , "labels" .=
      [ object
          [ "id" .= lid
          , "plain_language_name_ru" .= (T.toLower (T.drop 2 lid) <> " (fixture)")
          , "plain_language_name_en" .= (T.toLower (T.drop 2 lid) <> " (fixture en)")
          , "operational_definition" .= ("Определение " <> lid)
          , "inclusion_criteria" .= ["критерий включения" :: Text]
          , "exclusion_criteria" .= ([] :: [Text])
          , "examples" .= [object ["language" .= ("ru" :: Text), "text" .= ("пример для " <> lid), "verdict" .= ("positive" :: Text), "rationale" .= ("потому" :: Text)]]
          ]
      | lid <- activeLabels
      ]
  ]

writeBytes :: FilePath -> BS.ByteString -> IO ()
writeBytes path bytes = do
  createDirectoryIfMissing True (takeDirectory path)
  BS.writeFile path bytes

recordValue :: Text -> Text -> Text -> FilePath -> Text -> Text -> FilePath -> Text -> FilePath -> Text -> FilePath -> Text -> Text -> [Text] -> A.Value
recordValue packageId annotator tokenHash dir itemsSha checksumsSha presFile presSha insFile insSha ontFile ontVersion ontSha active = object
  [ "schema_version" .= ("rf.issuance-record.v1" :: Text)
  , "package_id" .= packageId
  , "annotator_id" .= annotator
  , "token_sha256" .= tokenHash
  , "package" .= object ["dir" .= dir, "items_sha256" .= itemsSha, "checksums_sha256" .= checksumsSha]
  , "presentation" .= object ["file" .= presFile, "sha256" .= presSha]
  , "instructions" .= object ["file" .= insFile, "sha256" .= insSha]
  , "ontology" .= object ["file" .= ontFile, "version" .= ontVersion, "sha256" .= ontSha, "active_labels" .= active]
    -- Eligibility provenance as metrics.issuance writes it: a field this
    -- parser does not read and must keep tolerating, so a record can carry
    -- more than the server needs without a redeploy.
  , "eligibility" .= object ["schema_version" .= ("rf.annotator-eligibility.v1" :: Text), "sha256" .= T.replicate 64 "e", "established_by" .= ("test" :: Text)]
  , "ui_language" .= ("ru" :: Text)
  , "issued_at" .= ("2026-09-08T00:00:00Z" :: Text)
  , "issued_by" .= ("test" :: Text)
  ]

-- | A tiny sealed package with two annotators, a registry that also names a
-- frozen package, an instruction document and an ontology, all under one
-- root -- the same shape the real deployment has.
makeFixture :: FilePath -> IO Fixture
makeFixture root = do
  let items1 = fixtureItems
      items2 = [fixtureItems !! 2, fixtureItems !! 0, fixtureItems !! 1]
      pres1 = jsonl (map presentationLine items1)
      pres2 = jsonl (map presentationLine items2)
      fakeItems = "{\"never\":\"read by the server\"}\n" :: BS.ByteString
      itemsSha = sha256Hex fakeItems
      checksums = TE.encodeUtf8 $ T.unlines
        [ itemsSha <> "  items.jsonl"
        , sha256Hex pres1 <> "  presentation/annotator-1.jsonl"
        , sha256Hex pres2 <> "  presentation/annotator-2.jsonl"
        ]
      instructions = "# Инструкция (fixture)\n\nЧитайте внимательно. Это ровно те байты, что выданы.\n" :: Text
      insBytes = TE.encodeUtf8 instructions
      pkgDir = "data/pilot/test"
      registry = BL.toStrict $ A.encode $ object
        [ "schema_version" .= ("rf.package-registry.v1" :: Text)
        , "packages" .= object
            [ "annotation-pilot-test" .= object ["dir" .= pkgDir, "status" .= ("issuable" :: Text), "checksums_sha256" .= sha256Hex checksums]
            , "annotation-pilot-frozen" .= object ["dir" .= ("data/pilot/frozen" :: Text), "status" .= ("frozen_non_issuable" :: Text)]
            ]
        ]
      token1 = "fixture-token-1"
      token2 = "fixture-token-2"
      record annotator tok presFile presSha = BL.toStrict $ A.encode $ recordValue
        "annotation-pilot-test" annotator (tokenSha tok) pkgDir itemsSha (sha256Hex checksums)
        presFile presSha "docs/instructions.md" (sha256Hex insBytes)
        "ontology.json" "behavior-fixture" (sha256Hex fixtureOntology) activeLabels
  writeBytes (root </> pkgDir </> "CHECKSUMS.sha256") checksums
  writeBytes (root </> pkgDir </> "presentation" </> "annotator-1.jsonl") pres1
  writeBytes (root </> pkgDir </> "presentation" </> "annotator-2.jsonl") pres2
  -- deliberately NOT written: items.jsonl, presentation-map/ -- the server
  -- must not need them, and this fixture proves it does not
  writeBytes (root </> "docs" </> "instructions.md") insBytes
  writeBytes (root </> "ontology.json") fixtureOntology
  writeBytes (root </> "registry.json") registry
  writeBytes (root </> "issuance" </> "annotator-1.json") (record "annotator-1" token1 "presentation/annotator-1.jsonl" (sha256Hex pres1))
  writeBytes (root </> "issuance" </> "annotator-2.json") (record "annotator-2" token2 "presentation/annotator-2.jsonl" (sha256Hex pres2))
  lastDb <- newIORef ""
  pure Fixture
    { fxRoot = root
    , fxConfig = BindingConfig { bcRepoRoot = root, bcRegistryFile = root </> "registry.json", bcIssuanceDir = root </> "issuance" }
    , fxToken = token1
    , fxToken2 = token2
    , fxItems = items1
    , fxItems2 = items2
    , fxInstructions = instructions
    , fxLastDb = lastDb
    }

-- | The real sealed package in the repository, bound for annotator-1 with a
-- test-only token in a temporary issuance directory. Nothing under data/ is
-- written. Absent when the test runs without the repository around it (a
-- nix build of src/annotation-web alone), in which case the spec is pending.
data RealFixture = RealFixture
  { rfRepoRoot :: FilePath
  , rfConfig :: BindingConfig
  , rfToken :: Text
  , rfItems :: [PresentedItem]
  , rfChecksums :: Checksums
  , rfInstructionsSha :: Text
  , rfLastDb :: IORef FilePath
  }

makeRealFixture :: FilePath -> IO (Maybe RealFixture)
makeRealFixture scratch = do
  let root = ".." </> ".."
      pkgDir = "data/pilot/v0.1"
      checksumsPath = root </> pkgDir </> "CHECKSUMS.sha256"
  present <- doesFileExist checksumsPath
  if not present
    then pure Nothing
    else do
      checksumsBytes <- BS.readFile checksumsPath
      checksums <- either (fail . T.unpack) pure (parseChecksums (TE.decodeUtf8 checksumsBytes))
      presBytes <- BS.readFile (root </> pkgDir </> "presentation" </> "annotator-1.jsonl")
      items <- either (fail . T.unpack . renderPacketFault) pure (parsePresentation presBytes)
      insBytes <- BS.readFile (root </> "docs" </> "pilot-v0.1-instructions.md")
      ontBytes <- BS.readFile (root </> "data" </> "ontology" </> "behavior-v0.1.json")
      manifest <- BS.readFile (root </> pkgDir </> "pilot-manifest.json")
      let manifestValue = fromMaybe A.Null (A.decodeStrict manifest)
          active = case field "active_labels" manifestValue of
            Just (A.Array xs) -> [t | A.String t <- toList xs]
            _ -> activeLabels
          ontologyVersion = case field "ontology_version" manifestValue of
            Just (A.String v) -> v
            _ -> "behavior-v0.1"
          token = "e2e-real-package-token"
          itemsSha = fromMaybe "" (checksumFor "items.jsonl" checksums)
          record = BL.toStrict $ A.encode $ recordValue
            "annotation-pilot-v0.1" "annotator-1" (tokenSha token) pkgDir itemsSha (sha256Hex checksumsBytes)
            "presentation/annotator-1.jsonl" (sha256Hex presBytes)
            "docs/pilot-v0.1-instructions.md" (sha256Hex insBytes)
            "data/ontology/behavior-v0.1.json" ontologyVersion (sha256Hex ontBytes) active
      writeBytes (scratch </> "issuance" </> "annotator-1.json") record
      lastDb <- newIORef ""
      pure $ Just RealFixture
        { rfRepoRoot = root
        , rfConfig = BindingConfig { bcRepoRoot = root, bcRegistryFile = root </> "data/pilot/package-registry.json", bcIssuanceDir = scratch </> "issuance" }
        , rfToken = token
        , rfItems = items
        , rfChecksums = checksums
        , rfInstructionsSha = sha256Hex insBytes
        , rfLastDb = lastDb
        }

field :: Text -> A.Value -> Maybe A.Value
field name (A.Object o) = KeyMap.lookup (Key.fromText name) o
field _ _ = Nothing

-- | A site with the fixture's bindings proven and the dogfood surface off,
-- on a fresh database per spec item. The database path is remembered so a
-- test can stand up a second server on the same file.
pilotSite :: BindingConfig -> IORef FilePath -> FilePath -> IORef Int -> IO App
pilotSite config lastDb dir counter = do
  n <- atomicModifyIORef' counter (\i -> (i + 1, i))
  let db = dir </> ("pilot-" <> show n <> ".db")
  writeIORef lastDb db
  _ <- migrateDatabase db
  bindings <- loadBindings config >>= either (fail . T.unpack . T.unlines . map renderBindingFault) pure
  makeFoundationWith FoundationConfig
    { fcDbPath = db
    , fcSessionKeyPath = dir </> "pilot-session-key.aes"
    , fcSecureCookies = False
    , fcBindings = bindings
    , fcDogfoodEnabled = False
    }

-- ---------------------------------------------------------------- loader

copyTree :: FilePath -> FilePath -> IO ()
copyTree from to = do
  createDirectoryIfMissing True to
  entries <- listDirectory from
  forM_ entries $ \name -> do
    let src = from </> name
        dst = to </> name
    isDir <- doesDirectoryExist src
    if isDir then copyTree src dst else copyFile src dst

-- | A mutated copy of the fixture root, loaded.
withVariant :: Fixture -> (FilePath -> IO ()) -> (Either [BindingFault] (Map.Map Text Binding) -> IO ()) -> IO ()
withVariant fixture mutate check = withSystemTempDirectory "pilot-variant" $ \copy -> do
  copyTree (fxRoot fixture) copy
  mutate copy
  loadBindings BindingConfig { bcRepoRoot = copy, bcRegistryFile = copy </> "registry.json", bcIssuanceDir = copy </> "issuance" } >>= check

faultsMatch :: (BindingFault -> Bool) -> Either [BindingFault] a -> IO ()
faultsMatch predicate outcome = case outcome of
  Left faults | any predicate faults -> pure ()
  Left faults -> expectationFailure ("unexpected faults: " <> T.unpack (T.unlines (map renderBindingFault faults)))
  Right _ -> expectationFailure "expected a refusal, got bindings"

rewriteJson :: FilePath -> (A.Value -> A.Value) -> IO ()
rewriteJson path f = do
  bytes <- BS.readFile path
  let value = fromMaybe A.Null (A.decodeStrict bytes)
  BS.writeFile path (BL.toStrict (A.encode (f value)))

setField :: [Text] -> A.Value -> A.Value -> A.Value
setField [] new _ = new
setField (k : ks) new (A.Object o) =
  A.Object (KeyMap.insert (Key.fromText k) (setField ks new (fromMaybe A.Null (KeyMap.lookup (Key.fromText k) o))) o)
setField _ _ other = other

loaderSpec :: Fixture -> Spec
loaderSpec fixture = describe "issuance bindings are proven at load, or refused" $ do
  it "loads the fixture: two annotators, packets in their own order, no items.jsonl needed" $ do
    outcome <- loadBindings (fxConfig fixture)
    case outcome of
      Left faults -> expectationFailure (T.unpack (T.unlines (map renderBindingFault faults)))
      Right bindings -> do
        Map.size bindings `shouldBe` 2
        case (Map.lookup (tokenSha (fxToken fixture)) bindings, Map.lookup (tokenSha (fxToken2 fixture)) bindings) of
          (Just b1, Just b2) -> do
            map piId (bindItems b1) `shouldBe` map piId (fxItems fixture)
            map piId (bindItems b2) `shouldBe` map piId (fxItems2 fixture)
            bindInstructions b1 `shouldBe` fxInstructions fixture
            length (bindOntology b1) `shouldBe` 5
          _ -> expectationFailure "both tokens should be bound"
        doesFileExist (fxRoot fixture </> "data/pilot/test/items.jsonl") `shouldReturn` False

  it "refuses a presentation file whose bytes changed after issuance" $
    withVariant fixture
      (\copy -> BS.appendFile (copy </> "data/pilot/test/presentation/annotator-1.jsonl") "\n")
      (faultsMatch (\f -> case f of FileHashMismatch {} -> True; _ -> False))

  it "refuses when the seal no longer matches the registry pin" $
    withVariant fixture
      (\copy -> BS.appendFile (copy </> "data/pilot/test/CHECKSUMS.sha256") "deadbeef  extra\n")
      (faultsMatch (\f -> case f of SealPinMismatch {} -> True; _ -> False))

  it "refuses an unsealed package" $
    withVariant fixture
      (\copy -> removeFile (copy </> "data/pilot/test/CHECKSUMS.sha256"))
      (faultsMatch (\f -> case f of SealMissing {} -> True; _ -> False))

  it "refuses a frozen package even with a perfect record" $
    withVariant fixture
      (\copy -> rewriteJson (copy </> "registry.json")
          (setField ["packages", "annotation-pilot-test", "status"] (A.String "frozen_non_issuable")))
      (faultsMatch (\f -> case f of PackageNotIssuable {} -> True; _ -> False))

  it "refuses a package the registry does not know" $
    withVariant fixture
      (\copy -> rewriteJson (copy </> "issuance/annotator-1.json") (setField ["package_id"] (A.String "annotation-pilot-ghost")))
      (faultsMatch (\f -> case f of RegistryUnknownPackage {} -> True; _ -> False))

  it "refuses an instruction document that is not the one recorded" $
    withVariant fixture
      (\copy -> BS.appendFile (copy </> "docs/instructions.md") "P.S.\n")
      (faultsMatch (\f -> case f of FileHashMismatch _ name _ _ -> name == "docs/instructions.md"; _ -> False))

  it "refuses a presentation row that carries authoring metadata" $
    withVariant fixture
      (\copy -> do
          let path = copy </> "data/pilot/test/presentation/annotator-1.jsonl"
              leaked = jsonl [setField ["authoring"] (object ["origin" .= ("human" :: Text)]) (presentationLine (fixtureItems !! 0))]
          BS.writeFile path leaked
          checksums <- BS.readFile (copy </> "data/pilot/test/CHECKSUMS.sha256")
          let fixed = TE.encodeUtf8 $ T.unlines
                [ if "presentation/annotator-1.jsonl" `T.isSuffixOf` line then sha256Hex leaked <> "  presentation/annotator-1.jsonl" else line
                | line <- T.lines (TE.decodeUtf8 checksums)
                ]
          BS.writeFile (copy </> "data/pilot/test/CHECKSUMS.sha256") fixed
          rewriteJson (copy </> "registry.json") (setField ["packages", "annotation-pilot-test", "checksums_sha256"] (A.String (sha256Hex fixed)))
          rewriteJson (copy </> "issuance/annotator-1.json") (setField ["package", "checksums_sha256"] (A.String (sha256Hex fixed)))
          rewriteJson (copy </> "issuance/annotator-1.json") (setField ["presentation", "sha256"] (A.String (sha256Hex leaked)))
          rewriteJson (copy </> "issuance/annotator-2.json") (setField ["package", "checksums_sha256"] (A.String (sha256Hex fixed))))
      (faultsMatch (\f -> case f of PresentationInvalid _ (PacketNotStimulus _) -> True; _ -> False))

  it "refuses two records that share a token" $
    withVariant fixture
      (\copy -> rewriteJson (copy </> "issuance/annotator-2.json") (setField ["token_sha256"] (A.String (tokenSha (fxToken fixture)))))
      (faultsMatch (\f -> case f of DuplicateToken {} -> True; _ -> False))

-- ---------------------------------------------------------------- web helpers

followTo :: Text -> YesodExample App ()
followTo expected = do
  statusIs 303
  redirected <- followRedirect
  case redirected of
    Left err -> liftIO $ expectationFailure (T.unpack err)
    Right url -> assertEq "redirect target" expected url

openToken :: Text -> YesodExample App ()
openToken token = do
  get (TokenR token)
  followTo "/intro"

submitStep :: Route App -> [(Text, Text)] -> YesodExample App ()
submitStep route params = request $ do
  setMethod "POST"
  setUrl route
  addToken_ "#step-form"
  mapM_ (uncurry addPostParam) params

submitFeedback :: Int -> [(Text, Text)] -> YesodExample App ()
submitFeedback index params = request $ do
  setMethod "POST"
  setUrl (FeedbackR index)
  addToken_ "#feedback-form"
  mapM_ (uncurry addPostParam) params

-- | Decide one item without touching the feedback disclosure.
noneObserved :: Int -> YesodExample App ()
noneObserved index = do
  get (ItemR index)
  statusIs 200
  submitStep (DecisionR index) [("decision", "none_observed")]
  followTo (itemPath index)

itemPath :: Int -> Text
itemPath index = T.pack ("/item/" <> show index)

bodyBytes :: YesodExample App BS.ByteString
bodyBytes = withResponse (pure . BL.toStrict . simpleBody)

bindingFor :: Text -> YesodExample App Binding
bindingFor token = do
  site <- getTestYesod
  case Map.lookup (tokenSha token) (appBindings site) of
    Just b -> pure b
    Nothing -> liftIO (fail "token not bound in this site")

exportFor :: Text -> YesodExample App (Either ExportFault PilotExport)
exportFor token = do
  site <- getTestYesod
  binding <- bindingFor token
  liftIO (exportPilot (appPool site) binding)

decodedResponses :: PilotExport -> [A.Value]
decodedResponses = peResponses

stringField :: Text -> A.Value -> Maybe Text
stringField name value = case field name value of
  Just (A.String t) -> Just t
  _ -> Nothing

-- | Stand up a second server on the same database and open the token there
-- with a fresh client: what a restart plus a reopened link looks like.
resumeAfterRestart :: Text -> FilePath -> YesodExample App Text
resumeAfterRestart token db = do
  site <- getTestYesod
  liftIO $ do
    app2 <- makeFoundationWith FoundationConfig
      { fcDbPath = db, fcSessionKeyPath = db <> ".key2", fcSecureCookies = False
      , fcBindings = appBindings site, fcDogfoodEnabled = False }
    wai2 <- toWaiApp app2
    runSession (do
      opened <- WT.request (WT.setPath Wai.defaultRequest (TE.encodeUtf8 ("/t/" <> token)))
      -- 303 on HTTP/1.1, 302 on the HTTP/1.0 request wai-test sends: both are the redirect
      unless (HTTP.statusCode (simpleStatus opened) `elem` [302, 303]) $ liftIO (expectationFailure "reopening the token did not redirect")
      let cookie = BC.takeWhile (/= ';') (fromMaybe "" (lookup "Set-Cookie" (simpleHeaders opened)))
      -- wai-test keeps its own cookie jar and prepends a Cookie header of its
      -- own on every request; a hand-made Cookie header would sit behind it.
      -- Rely on the jar, as a browser would, and only diagnose if it fails.
      jar <- WT.getClientCookies
      landing <- WT.request (WT.setPath Wai.defaultRequest "/done")
      let location = TE.decodeUtf8 (fromMaybe "" (lookup HTTP.hLocation (simpleHeaders landing)))
      unless ("/item/" `T.isPrefixOf` location) $ liftIO $ expectationFailure $
        "resume did not land on an item: location=" <> T.unpack location
          <> " jar=" <> show jar
          <> " set-cookie=" <> show cookie
          <> " landing status=" <> show (simpleStatus landing)
      pure location) wai2

-- ---------------------------------------------------------------- web spec

webSpec :: Fixture -> YesodSpec App
webSpec fixture = ydescribe "the token-bound pilot surface" $ do
  let token = fxToken fixture
      items = fxItems fixture
      textsOf item = map pmText (piMessages item)
      targetOf item = fromMaybe "" (presentedTarget item)

  yit "keeps the dogfood surface closed" $ do
    get HomeR
    statusIs 200
    bodyContains "нет открытого исследования"
    request $ do
      setMethod "POST"
      setUrl LanguageR
      addPostParam "language" "ru"
    statusIs 404

  yit "answers an unknown token with 404 and nothing else" $ do
    get (TokenR "not-a-token")
    statusIs 404

  yit "opens the bound intro: the instruction hash and the pinned ontology, not the dogfood glossary" $ do
    openToken token
    statusIs 200
    bodyContains "annotator-1"
    bodyContains (T.unpack (sha256Text (fxInstructions fixture)))
    bodyContains "blame_criticism (fixture)"
    bodyContains "Определение B.VALIDATION"
    bodyContains "пример для B.REPAIR_ATTEMPT"
    bodyNotContains "счёт за электричество"
    bodyNotContains "Кстати, соседи"

  yit "serves the instruction document byte for byte" $ do
    openToken token
    get InstructionsR
    statusIs 200
    body <- bodyBytes
    assertEq "exact bytes" (TE.encodeUtf8 (fxInstructions fixture)) body

  yit "renders each item as the packet has it: every text, in order, one target, no id" $ do
    openToken token
    forM_ (zip [0 ..] items) $ \(index, item) -> do
      get (ItemR index)
      statusIs 200
      bodyContains (show (index + 1 :: Int) <> " / 3")
      forM_ (textsOf item) (bodyContains . T.unpack)
      htmlAnyContain ".bubble.target" (T.unpack (targetOf item))
      htmlCount ".bubble.target" 1
      htmlCount ".bubble.context" (length (piMessages item) - 1)
      bodyNotContains (T.unpack (piId item))
      bodyNotContains "Показать оригинал"
      bodyNotContains "Источник"
      -- move on so the next index is reachable in order
      submitStep (DecisionR index) [("decision", "none_observed")]
      followTo (itemPath index)

  yit "shows annotator-2 the same rows in annotator-2's order" $ do
    openToken (fxToken2 fixture)
    get (ItemR 0)
    statusIs 200
    bodyContains "ok whatever, do what you want"
    bodyNotContains "Привет, где ключи?"

  yit "stores a quote exactly as typed and rejects one that is not a span" $ do
    openToken token
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    submitStep (LabelsR 0) [("labels", "B.BLAME_CRITICISM")]
    followTo "/item/0"
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "На крючке ")]
    statusIs 200
    htmlCount ".field-error" 1
    quotesBefore <- quotesFor "item-aaaaaa"
    assertEq "nothing stored for a rejected quote" [] quotesBefore
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", " где всегда")]
    followTo "/item/0"
    quotes <- quotesFor "item-aaaaaa"
    assertEq "the quote is stored with its leading space, as typed" [" где всегда"] quotes

  yit "finishes with thanks and no download" $ do
    openToken token
    forM_ [0 .. 2] noneObserved
    get DoneR
    statusIs 200
    bodyContains "анонимным id"
    bodyNotContains "submission.json"
    get SubmissionR
    statusIs 404

  yit "exports one canonical line per item, packet order, feedback on every line, empty meaning empty" $ do
    openToken token
    -- item 0: disclosure never opened; item 1: opened and left empty; item 2: flagged
    noneObserved 0
    get (ItemR 1)
    submitFeedback 1 []
    followTo "/item/1"
    submitStep (DecisionR 1) [("decision", "none_observed")]
    followTo "/item/1"
    get (ItemR 2)
    submitFeedback 2 [("feedback_flags", "unnatural_example"), ("feedback_note", "  звучит как учебник  ")]
    followTo "/item/2"
    submitStep (DecisionR 2) [("decision", "abstained")]
    followTo "/item/2"
    submitStep (AbstainR 2) [("reason", "insufficient_context")]
    followTo "/item/2"
    get DoneR
    statusIs 200
    outcome <- exportFor token
    export <- either (liftIO . fail . T.unpack . renderExportFault) pure outcome
    let responses = decodedResponses export
    assertEq "one line per item" (map piId items) (mapMaybe (stringField "item_id") responses)
    assertEq "decisions" [Just "none_observed", Just "none_observed", Just "abstained"] (map (stringField "decision") responses)
    assertEq "abstention reason" (Just "insufficient_context") (stringField "abstention_reason" (responses !! 2))
    assertEq "feedback present on every line" [True, True, True] (map (\r -> field "feedback" r /= Nothing) responses)
    assertEq "never opened: empty" (Just (A.Array mempty)) (field "feedback" (responses !! 0) >>= field "flags")
    assertEq "never opened: note is the empty string, not null" (Just (A.String "")) (field "feedback" (responses !! 0) >>= field "note")
    assertEq "opened and left empty: still empty" (Just (A.Array mempty)) (field "feedback" (responses !! 1) >>= field "flags")
    assertEq "flag recorded" (Just (A.Array (pure (A.String "unnatural_example")))) (field "feedback" (responses !! 2) >>= field "flags")
    assertEq "note recorded, trimmed" (Just (A.String "звучит как учебник")) (field "feedback" (responses !! 2) >>= field "note")
    assertEq "schema" (Just "rf.pilot-response.v1") (stringField "schema_version" (responses !! 0))
    assertEq "annotator" (Just "annotator-1") (stringField "annotator_id" (responses !! 0))
    let bytes = responsesJsonl responses
        recordJson = exportRecordValue export bytes
    assertEq "export record repeats the binding" (Just "annotation-pilot-test") (stringField "package_id" recordJson)
    assertEq "export record hashes the layer" (Just (sha256Hex bytes)) (stringField "responses_sha256" recordJson)

  yit "refuses to export an incomplete session and says which items" $ do
    openToken token
    noneObserved 0
    outcome <- exportFor token
    assertEq "incomplete" (Left (ExportIncomplete ["item-bbbbbb", "item-cccccc"])) (either Left (const (Right ())) outcome)

  yit "keeps two tokens' sessions apart" $ do
    openToken token
    noneObserved 0
    openToken (fxToken2 fixture)
    forM_ [0 .. 2] noneObserved
    second <- exportFor (fxToken2 fixture)
    assertEq "annotator-2 complete" (Right 3) (fmap (length . peResponses) second)
    first <- exportFor token
    assertEq "annotator-1 still incomplete" (Left (ExportIncomplete ["item-bbbbbb", "item-cccccc"])) (either Left (const (Right ())) first)

  yit "resumes after a restart at the first incomplete item, with earlier answers intact" $ do
    openToken token
    noneObserved 0
    noneObserved 1
    db <- liftIO (readIORef (fxLastDb fixture))
    landing <- resumeAfterRestart token db
    assertEq "resumed at the first incomplete item" "/item/2" landing
    -- the reopened token did not start a second session
    sessions <- sessionCount
    assertEq "one session for the token" 1 sessions
    noneObserved 2
    outcome <- exportFor token
    assertEq "complete after resuming" (Right 3) (fmap (length . peResponses) outcome)
  where
    quotesFor iid = do
      site <- getTestYesod
      liftIO $ flip runSqlPool (appPool site) $ do
        anns <- selectList [AnnotationItemId ==. iid] []
        case anns of
          [] -> pure []
          (Entity aid _ : _) -> map (evidenceQuote . entityVal) <$> selectList [EvidenceAnnotationId ==. aid] [Asc EvidenceId]
    sessionCount = do
      site <- getTestYesod
      liftIO $ flip runSqlPool (appPool site) $ length <$> selectList ([] :: [Filter PilotBinding]) []

-- ---------------------------------------------------------------- the real package

realPackageSpec :: Maybe RealFixture -> YesodSpec App
realPackageSpec Nothing = ydescribe "the sealed v0.1 package" $
  yit "is not available here (running outside the repository); nothing to prove" $ pure ()
realPackageSpec (Just real) = ydescribe "the sealed v0.1 package, end to end" $
  yit "token -> 40 items -> restart -> resume -> complete -> canonical export with the sealed hashes" $ do
    let token = rfToken real
        items = rfItems real
        total = length items
    assertEq "the packet has 40 items" 40 total
    openToken token
    statusIs 200
    bodyContains (T.unpack (rfInstructionsSha real))
    bodyContains "B.PRESSURE_FOR_CHANGE"
    -- first and last items: exact texts, no canonical ids anywhere on the page
    forM_ [0, total - 1] $ \index -> do
      get (ItemR index)
      statusIs 200
      forM_ (piMessages (items !! index)) (bodyContains . T.unpack . pmText)
      bodyNotContains (T.unpack (piId (items !! index)))
      forM_ ["pc-0", "pc-1", "pc-2", "pn-0", "pn-1", "pn-2"] bodyNotContains
    -- one assigned with an exact quote, one abstained, the rest none_observed
    let targetText index = fromMaybe "" (presentedTarget (items !! index))
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    submitStep (LabelsR 0) [("labels", "B.BLAME_CRITICISM")]
    followTo "/item/0"
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", targetText 0)]
    followTo "/item/0"
    get (ItemR 1)
    submitFeedback 1 []
    followTo "/item/1"
    submitStep (DecisionR 1) [("decision", "abstained")]
    followTo "/item/1"
    submitStep (AbstainR 1) [("reason", "insufficient_context")]
    followTo "/item/1"
    forM_ [2 .. 19] noneObserved
    db <- liftIO (readIORef (rfLastDb real))
    landing <- resumeAfterRestart token db
    assertEq "resumed at item 21" "/item/20" landing
    forM_ [20 .. total - 1] noneObserved
    get DoneR
    statusIs 200
    bodyNotContains "submission.json"
    outcome <- exportFor token
    export <- either (liftIO . fail . T.unpack . renderExportFault) pure outcome
    let responses = peResponses export
        ids = mapMaybe (stringField "item_id") responses
    assertEq "40/40, packet order, each exactly once" (map piId items) ids
    assertEq "feedback on every line" total (length (filter (\r -> field "feedback" r /= Nothing) responses))
    assertEq "the quote is the exact target" (Just (A.String (targetText 0)))
      (field "quotes" (responses !! 0) >>= \q -> case q of A.Array xs | not (null xs) -> field "quote" (toList xs !! 0); _ -> Nothing)
    let rec = peRecord export
    assertEq "items hash is the sealed one" (checksumFor "items.jsonl" (rfChecksums real)) (Just (irItemsSha rec))
    assertEq "presentation hash is the sealed one" (checksumFor "presentation/annotator-1.jsonl" (rfChecksums real)) (Just (irPresentationSha rec))
    assertEq "instruction hash is the issued one" (rfInstructionsSha real) (irInstructionsSha rec)
    let bytes = responsesJsonl responses
    assertEq "export record carries the layer hash" (Just (sha256Hex bytes)) (stringField "responses_sha256" (exportRecordValue export bytes))
