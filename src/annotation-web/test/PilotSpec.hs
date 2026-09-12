{-# LANGUAGE OverloadedStrings #-}

-- | The pilot surface: a package is served only through the registry and its
-- seal; a fresh visitor claims one of exactly as many slots as the sealed
-- package's manifest names, first-come, never twice; the renderer shows
-- exactly those bytes in exactly that order and never a canonical id; the
-- collector stores exactly what was typed and only for its own session;
-- feedback is present on every exported line and empty means empty; the
-- session survives a restart; the export is the canonical layer, complete or
-- refused.
module PilotSpec
  ( Fixture (..)
  , makeFixture
  , RegistryFixture (..)
  , makeRegistryFixture
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
import Data.Maybe (fromMaybe, mapMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import Data.Time (getCurrentTime)
import Database.Persist.Sql (Entity (..), Filter, SelectOpt (Asc), entityVal, getBy, insert, insert_, runSqlPool, selectList, (==.))
import Export
import qualified Network.HTTP.Types as HTTP
import qualified Network.Wai as Wai
import Network.Wai.Test (SResponse (..), runSession, simpleBody)
import qualified Network.Wai.Test as WT
import Ontology (parseOntology)
import Packet
import Registry
import Schema (migrateDatabase)
import Server
import System.Directory (createDirectoryIfMissing, doesFileExist, removeFile)
import System.FilePath (takeDirectory, (</>))
import System.IO.Temp (withSystemTempDirectory)
import Test.Hspec
import Yesod (toWaiAppPlain, defaultMiddlewaresNoLogging)
import Yesod.Test

-- ---------------------------------------------------------------- fixtures

data Fixture = Fixture
  { fxConfig :: PilotConfig
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

fixtureOntologyBytes :: BS.ByteString
fixtureOntologyBytes = BL.toStrict $ A.encode $ object
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

-- | Everything needed to exercise 'loadPilotConfig' against real files on
-- disk: a registry naming one issuable and one frozen package, and the
-- issuable one's seal, manifest, two presentation files, an instruction
-- document and an ontology file.
data RegistryFixture = RegistryFixture
  { rgRoot :: FilePath
  , rgRegistryFile :: FilePath
  , rgItems1 :: [PresentedItem]
  , rgItems2 :: [PresentedItem]
  , rgInstructions :: Text
  }

manifestBytesFor :: BS.ByteString -> [Text] -> BS.ByteString
manifestBytesFor ontologyBytes annotators = BL.toStrict $ A.encode $ object
  [ "schema_version" .= ("rf.pilot-manifest.v1" :: Text)
  , "pilot_id" .= ("annotation-pilot-test" :: Text)
  , "annotators" .= annotators
  , "active_labels" .= activeLabels
  , "ontology_version" .= ("behavior-fixture" :: Text)
  , "ontology_sha256" .= sha256Hex ontologyBytes
  ]

makeRegistryFixture :: FilePath -> IO RegistryFixture
makeRegistryFixture root = do
  let items1 = fixtureItems
      items2 = [fixtureItems !! 2, fixtureItems !! 0, fixtureItems !! 1]
      pres1 = jsonl (map presentationLine items1)
      pres2 = jsonl (map presentationLine items2)
      manifestBytes = manifestBytesFor fixtureOntologyBytes ["annotator-1", "annotator-2"]
      checksums = TE.encodeUtf8 $ T.unlines
        [ sha256Hex manifestBytes <> "  pilot-manifest.json"
        , sha256Hex pres1 <> "  presentation/annotator-1.jsonl"
        , sha256Hex pres2 <> "  presentation/annotator-2.jsonl"
        ]
      instructions = "# Инструкция (fixture)\n\nЧитайте внимательно. Это ровно те байты, что выданы.\n" :: Text
      insBytes = TE.encodeUtf8 instructions
      pkgDir = "data/pilot/test"
      registry = BL.toStrict $ A.encode $ object
        [ "schema_version" .= ("rf.package-registry.v1" :: Text)
        , "packages" .= object
            [ "annotation-pilot-test" .= object
                [ "dir" .= pkgDir
                , "status" .= ("issuable" :: Text)
                , "checksums_sha256" .= sha256Hex checksums
                , "instructions_file" .= ("docs/instructions.md" :: Text)
                , "instructions_sha256" .= sha256Hex insBytes
                ]
            , "annotation-pilot-frozen" .= object ["dir" .= ("data/pilot/frozen" :: Text), "status" .= ("frozen_non_issuable" :: Text)]
            ]
        ]
  writeBytes (root </> pkgDir </> "CHECKSUMS.sha256") checksums
  writeBytes (root </> pkgDir </> "pilot-manifest.json") manifestBytes
  writeBytes (root </> pkgDir </> "presentation" </> "annotator-1.jsonl") pres1
  writeBytes (root </> pkgDir </> "presentation" </> "annotator-2.jsonl") pres2
  -- deliberately NOT written: items.jsonl, presentation-map/ -- the server
  -- must not need them, and this fixture proves it does not
  writeBytes (root </> "docs" </> "instructions.md") insBytes
  writeBytes (root </> "data" </> "ontology" </> "behavior-fixture.json") fixtureOntologyBytes
  writeBytes (root </> "registry.json") registry
  pure RegistryFixture
    { rgRoot = root
    , rgRegistryFile = root </> "registry.json"
    , rgItems1 = items1
    , rgItems2 = items2
    , rgInstructions = instructions
    }

-- | The fixture 'webSpec' drives over HTTP: a 'PilotConfig' built directly,
-- with no registry file, seal or ontology file on disk at all. Whether a
-- 'PilotConfig' assembled that way behaves is 'loaderSpec' and
-- 'realPackageSpec''s job (the latter against the real, sealed v0.1
-- package); this fixture only needs one to exist.
makeFixture :: IO Fixture
makeFixture = do
  let items1 = fixtureItems
      items2 = [fixtureItems !! 2, fixtureItems !! 0, fixtureItems !! 1]
      instructions = "# Инструкция (fixture)\n\nЧитайте внимательно. Это ровно те байты, что выданы.\n" :: Text
  ontology <- either (fail . T.unpack) (pure . snd) (parseOntology activeLabels fixtureOntologyBytes)
  lastDb <- newIORef ""
  pure Fixture
    { fxConfig = PilotConfig
        { pcPackageId = "annotation-pilot-test"
        , pcSlots = [PilotSlot "annotator-1" items1, PilotSlot "annotator-2" items2]
        , pcInstructions = instructions
        , pcOntologyVersion = "behavior-fixture"
        , pcOntology = ontology
        }
    , fxItems = items1
    , fxItems2 = items2
    , fxInstructions = instructions
    , fxLastDb = lastDb
    }

-- | The real sealed package in the repository, loaded for real through
-- 'loadPilotConfig'. Absent when the test runs without the repository
-- around it (a nix build of src/annotation-web alone), in which case the
-- spec is pending.
data RealFixture = RealFixture
  { rfConfig :: PilotConfig
  , rfItems :: [PresentedItem]
    -- ^ annotator-1's packet, in its order
  , rfChecksums :: Checksums
  , rfLastDb :: IORef FilePath
  }

makeRealFixture :: IO (Maybe RealFixture)
makeRealFixture = do
  let root = ".." </> ".."
      pkgDir = "data/pilot/v0.1"
      checksumsPath = root </> pkgDir </> "CHECKSUMS.sha256"
  present <- doesFileExist checksumsPath
  if not present
    then pure Nothing
    else do
      loaded <- loadPilotConfig root (root </> "data/pilot/package-registry.json")
      cfg <- either (fail . T.unpack . T.unlines . map renderRegistryFault) pure loaded
      checksumsBytes <- BS.readFile checksumsPath
      checksums <- either (fail . T.unpack) pure (parseChecksums (TE.decodeUtf8 checksumsBytes))
      let items = case [s | s <- pcSlots cfg, psAnnotatorId s == "annotator-1"] of
            (s : _) -> psItems s
            [] -> error "annotator-1 slot missing from the sealed v0.1 package"
      lastDb <- newIORef ""
      pure $ Just RealFixture
        { rfConfig = cfg
        , rfItems = items
        , rfChecksums = checksums
        , rfLastDb = lastDb
        }

field :: Text -> A.Value -> Maybe A.Value
field name (A.Object o) = KeyMap.lookup (Key.fromText name) o
field _ _ = Nothing

-- | A site with the config's package loaded and the dogfood surface off, on
-- a fresh database per spec item. The database path is remembered so a test
-- can stand up a second server on the same file.
pilotSite :: PilotConfig -> IORef FilePath -> FilePath -> IORef Int -> IO App
pilotSite cfg lastDb dir counter = do
  n <- atomicModifyIORef' counter (\i -> (i + 1, i))
  let db = dir </> ("pilot-" <> show n <> ".db")
  writeIORef lastDb db
  _ <- migrateDatabase db
  makeFoundationWith FoundationConfig
    { fcDbPath = db
    , fcSessionKeyPath = dir </> "pilot-session-key.aes"
    , fcSecureCookies = False
    , fcPilotConfig = Just cfg
    , fcDogfoodEnabled = False
    }

-- ---------------------------------------------------------------- loader

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

-- | A mutated copy of the fixture root, loaded.
withVariant :: RegistryFixture -> (FilePath -> IO ()) -> (Either [RegistryFault] PilotConfig -> IO ()) -> IO ()
withVariant fixture mutate check = withSystemTempDirectory "pilot-registry-variant" $ \copy -> do
  copyTree (rgRoot fixture) copy
  mutate copy
  loadPilotConfig copy (copy </> "registry.json") >>= check
  where
    copyTree from to = do
      createDirectoryIfMissing True to
      let cp rel = do
            let src = from </> rel
                dst = to </> rel
            exists <- doesFileExist src
            unless exists (fail ("fixture file missing: " <> src))
            createDirectoryIfMissing True (takeDirectory dst)
            BS.readFile src >>= BS.writeFile dst
      mapM_ cp
        [ "registry.json"
        , "docs/instructions.md"
        , "data/ontology/behavior-fixture.json"
        , "data/pilot/test/CHECKSUMS.sha256"
        , "data/pilot/test/pilot-manifest.json"
        , "data/pilot/test/presentation/annotator-1.jsonl"
        , "data/pilot/test/presentation/annotator-2.jsonl"
        ]

faultsMatch :: (RegistryFault -> Bool) -> Either [RegistryFault] a -> IO ()
faultsMatch predicate outcome = case outcome of
  Left faults | any predicate faults -> pure ()
  Left faults -> expectationFailure ("unexpected faults: " <> T.unpack (T.unlines (map renderRegistryFault faults)))
  Right _ -> expectationFailure "expected a refusal, got a loaded package"

loaderSpec :: RegistryFixture -> Spec
loaderSpec fixture = describe "the sealed package is proven at load, or refused" $ do
  it "loads the fixture: two annotator slots, packets in their own order, no items.jsonl needed" $ do
    outcome <- loadPilotConfig (rgRoot fixture) (rgRegistryFile fixture)
    case outcome of
      Left faults -> expectationFailure (T.unpack (T.unlines (map renderRegistryFault faults)))
      Right cfg -> do
        pcPackageId cfg `shouldBe` "annotation-pilot-test"
        length (pcSlots cfg) `shouldBe` 2
        case [s | s <- pcSlots cfg, psAnnotatorId s == "annotator-1"] of
          (s1 : _) -> map piId (psItems s1) `shouldBe` map piId (rgItems1 fixture)
          [] -> expectationFailure "annotator-1 slot missing"
        case [s | s <- pcSlots cfg, psAnnotatorId s == "annotator-2"] of
          (s2 : _) -> map piId (psItems s2) `shouldBe` map piId (rgItems2 fixture)
          [] -> expectationFailure "annotator-2 slot missing"
        pcInstructions cfg `shouldBe` rgInstructions fixture
        length (pcOntology cfg) `shouldBe` 5
    doesFileExist (rgRoot fixture </> "data/pilot/test/items.jsonl") `shouldReturn` False

  it "refuses a presentation file whose bytes changed after sealing" $
    withVariant fixture
      (\copy -> BS.appendFile (copy </> "data/pilot/test/presentation/annotator-1.jsonl") "\n")
      (faultsMatch (\f -> case f of FileHashMismatch {} -> True; _ -> False))

  it "refuses a manifest whose bytes changed after sealing" $
    withVariant fixture
      (\copy -> rewriteJson (copy </> "data/pilot/test/pilot-manifest.json") (setField ["active_labels"] (A.Array mempty)))
      (faultsMatch (\f -> case f of FileHashMismatch {} -> True; _ -> False))

  it "refuses when the seal no longer matches the registry pin" $
    withVariant fixture
      (\copy -> BS.appendFile (copy </> "data/pilot/test/CHECKSUMS.sha256") "deadbeef  extra\n")
      (faultsMatch (\f -> case f of SealPinMismatch {} -> True; _ -> False))

  it "refuses an unsealed package" $
    withVariant fixture
      (\copy -> removeFile (copy </> "data/pilot/test/CHECKSUMS.sha256"))
      (faultsMatch (\f -> case f of SealMissing {} -> True; _ -> False))

  it "refuses when no package is issuable" $
    withVariant fixture
      (\copy -> rewriteJson (copy </> "registry.json")
          (setField ["packages", "annotation-pilot-test", "status"] (A.String "frozen_non_issuable")))
      (faultsMatch (\f -> case f of NoIssuablePackage {} -> True; _ -> False))

  it "refuses when more than one package is issuable" $
    withVariant fixture
      (\copy -> rewriteJson (copy </> "registry.json")
          (setField ["packages", "annotation-pilot-frozen", "status"] (A.String "issuable")))
      (faultsMatch (\f -> case f of MultipleIssuablePackages {} -> True; _ -> False))

  it "refuses an instruction document that is not the one the registry names" $
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
          rewriteJson (copy </> "registry.json") (setField ["packages", "annotation-pilot-test", "checksums_sha256"] (A.String (sha256Hex fixed))))
      (faultsMatch (\f -> case f of PresentationInvalid _ _ -> True; _ -> False))

-- ---------------------------------------------------------------- web helpers

followTo :: Text -> YesodExample App ()
followTo expected = do
  statusIs 303
  redirected <- followRedirect
  case redirected of
    Left err -> liftIO $ expectationFailure (T.unpack err)
    Right url -> assertEq "redirect target" expected url

-- | The whole claim dance a fresh browser does: GET the landing page (safe,
-- side-effect-free even for a bot's link preview), then POST the "Начать"
-- form, which is the only thing that may claim a slot.
openHome :: YesodExample App ()
openHome = do
  get HomeR
  _ <- claimSlot
  pure ()

-- | Claims a slot and returns the @Set-Cookie@ this browser was just given,
-- for tests that need to replay the exact same session elsewhere (a fresh
-- server process against the same database and session-key file, standing
-- in for a restart -- there is no portable link to reopen with any more,
-- only the cookie the original claim set).
claimSlot :: YesodExample App BS.ByteString
claimSlot = do
  request $ do
    setMethod "POST"
    setUrl HomeR
    addToken_ "#claim-form"
  cookie <- withResponse (pure . BC.takeWhile (/= ';') . fromMaybe "" . lookup "Set-Cookie" . simpleHeaders)
  followTo "/intro"
  pure cookie

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

exportFor :: PilotConfig -> Text -> YesodExample App (Either ExportFault PilotExport)
exportFor cfg annotatorId = do
  site <- getTestYesod
  liftIO (exportPilot (appPool site) cfg annotatorId)

decodedResponses :: PilotExport -> [A.Value]
decodedResponses = peResponses

stringField :: Text -> A.Value -> Maybe Text
stringField name value = case field name value of
  Just (A.String t) -> Just t
  _ -> Nothing

sessionCount :: YesodExample App Int
sessionCount = do
  site <- getTestYesod
  liftIO $ flip runSqlPool (appPool site) $ length <$> selectList ([] :: [Filter PilotBinding]) []

boundSessionFor :: Text -> YesodExample App (Maybe SurveySessionId)
boundSessionFor annotatorId = do
  site <- getTestYesod
  liftIO $ flip runSqlPool (appPool site) $
    fmap (pilotBindingSurveySessionId . entityVal) <$> getBy (UniquePilotBindingAnnotator annotatorId)

-- | Directly inserts a PilotBinding for `annotatorId`, as another request's
-- own claim would have just committed one. Returns its SurveySessionId, the
-- one a correct claimNextSlot must resume into rather than duplicate.
seedCompetingBinding :: Text -> YesodExample App SurveySessionId
seedCompetingBinding annotatorId = do
  site <- getTestYesod
  liftIO $ flip runSqlPool (appPool site) $ do
    now <- liftIO getCurrentTime
    sid <- insert $ SurveySession "ru" now Nothing
    insert_ $ SessionInstrument sid (instrumentVersionCode InstrumentPilot)
    insert_ $ PilotBinding sid annotatorId
    pure sid

-- | Stand up a second server (same database, same session-key file -- a
-- restart, not a different device with a different key) and replay this
-- browser's own cookie against it, exactly as the original browser
-- reconnecting after a redeploy would.
resumeAfterRestart :: PilotConfig -> FilePath -> BS.ByteString -> YesodExample App Text
resumeAfterRestart cfg db cookie = liftIO $ do
  app2 <- makeFoundationWith FoundationConfig
    { fcDbPath = db, fcSessionKeyPath = takeDirectory db </> "pilot-session-key.aes", fcSecureCookies = False
    , fcPilotConfig = Just cfg, fcDogfoodEnabled = False }
  wai2 <- defaultMiddlewaresNoLogging <$> toWaiAppPlain app2
  runSession (do
    landing <- WT.request (WT.setPath Wai.defaultRequest { Wai.requestHeaders = [("Cookie", cookie)] } "/done")
    let location = TE.decodeUtf8 (fromMaybe "" (lookup HTTP.hLocation (simpleHeaders landing)))
    unless ("/item/" `T.isPrefixOf` location) $ liftIO $ expectationFailure $
      "resume did not land on an item: location=" <> T.unpack location
        <> " landing status=" <> show (simpleStatus landing)
    pure location) wai2

-- ---------------------------------------------------------------- web spec

webSpec :: Fixture -> YesodSpec App
webSpec fixture = ydescribe "the sealed pilot surface" $ do
  let cfg = fxConfig fixture
      items = fxItems fixture
      textsOf item = map pmText (piMessages item)
      targetOf item = fromMaybe "" (presentedTarget item)

  yit "keeps the dogfood surface closed" $ do
    request $ do
      setMethod "POST"
      setUrl LanguageR
      addPostParam "language" "ru"
    statusIs 404

  yit "a fresh visitor gets a landing page and claims nothing until the button is pressed" $ do
    get HomeR
    statusIs 200
    htmlCount "#claim-form" 1
    sessions <- sessionCount
    assertEq "no binding created by a bare GET" 0 sessions

  yit "opening it any number of times before claiming is still harmless" $ do
    get HomeR
    get HomeR
    get HomeR
    statusIs 200
    sessions <- sessionCount
    assertEq "however many times it is prefetched, nothing is created" 0 sessions

  yit "only the POST claims a slot; resuming afterwards never opens a second session" $ do
    openHome
    sessions <- sessionCount
    assertEq "one binding after the real claim" 1 sessions
    -- reopening the same (still-cookied) browser resumes
    get HomeR
    statusIs 303
    followTo "/intro"
    sessionsAfterResume <- sessionCount
    assertEq "resuming does not create a second binding" 1 sessionsAfterResume

  yit "a slot claimed elsewhere between the check and the insert resumes there, not a crash" $ do
    -- claimNextSlot's own "is annotator-1 free" check and its own insert are
    -- two separate round trips to the database, not one transaction, so two
    -- POSTs arriving close enough both reach the insert believing the slot
    -- is free. insertUnique is what actually decides that only once, by
    -- refusing the second write rather than letting it corrupt anything.
    -- Manufacturing the conflict directly exercises that same code path
    -- deterministically, rather than gambling on a real thread race.
    get HomeR
    statusIs 200
    winner <- seedCompetingBinding "annotator-1"
    -- the claimant who lost the race for annotator-1 is not left stranded:
    -- claimNextSlot moves on and gives them annotator-2, landing on /intro
    -- exactly as any successful claim does
    _ <- claimSlot
    -- two bindings total: the seeded annotator-1 (unchanged) and the claim
    -- that moved on to annotator-2 -- not a second row for annotator-1
    sessions <- sessionCount
    assertEq "annotator-1 (seeded) plus annotator-2 (this claim), not a duplicate" 2 sessions
    stillOnlyWinner <- boundSessionFor "annotator-1"
    assertEq "annotator-1's row is still the one that was already there" (Just winner) stillOnlyWinner

  yit "both slots taken: a third visitor sees a plain refusal, no crash" $ do
    _ <- seedCompetingBinding "annotator-1"
    _ <- seedCompetingBinding "annotator-2"
    get HomeR
    statusIs 200
    htmlCount "#claim-form" 1
    request $ do
      setMethod "POST"
      setUrl HomeR
      addToken_ "#claim-form"
    statusIs 200
    bodyContains "Оба места уже заняты"

  yit "opens the bound intro: the active ontology labels, not the dogfood glossary" $ do
    openHome
    statusIs 200
    bodyContains "annotator-1"
    bodyContains "blame_criticism (fixture)"
    bodyContains "Определение B.VALIDATION"
    bodyContains "пример для B.REPAIR_ATTEMPT"
    bodyNotContains "счёт за электричество"
    bodyNotContains "Кстати, соседи"

  yit "serves the instruction document byte for byte" $ do
    openHome
    get InstructionsR
    statusIs 200
    body <- bodyBytes
    assertEq "exact bytes" (TE.encodeUtf8 (fxInstructions fixture)) body

  yit "renders each item as the packet has it: every text, in order, one target, no id" $ do
    openHome
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

  yit "the second claimant sees annotator-2's rows in annotator-2's order" $ do
    _ <- seedCompetingBinding "annotator-1"
    openHome
    get (ItemR 0)
    statusIs 200
    bodyContains "ok whatever, do what you want"
    bodyNotContains "Привет, где ключи?"

  yit "stores a quote exactly as typed and rejects one that is not a span" $ do
    openHome
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
    openHome
    forM_ [0 .. 2] noneObserved
    get DoneR
    statusIs 200
    bodyContains "анонимным id"
    bodyNotContains "submission.json"
    get SubmissionR
    statusIs 404

  yit "exports one canonical line per item, packet order, feedback on every line, empty meaning empty" $ do
    openHome
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
    outcome <- exportFor cfg "annotator-1"
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
    assertEq "export record repeats the package" (Just "annotation-pilot-test") (stringField "package_id" recordJson)
    assertEq "export record hashes the layer" (Just (sha256Hex bytes)) (stringField "responses_sha256" recordJson)

  yit "refuses to export an incomplete session and says which items" $ do
    openHome
    noneObserved 0
    outcome <- exportFor cfg "annotator-1"
    assertEq "incomplete" (Left (ExportIncomplete ["item-bbbbbb", "item-cccccc"])) (either Left (const (Right ())) outcome)

  yit "keeps the two slots' sessions apart" $ do
    openHome
    noneObserved 0
    -- annotator-2 is bound separately (as claiming it from a second browser
    -- would leave it: a fresh session, nothing answered yet) and must be
    -- reported incomplete on its own packet order, not annotator-1's
    _ <- seedCompetingBinding "annotator-2"
    second <- exportFor cfg "annotator-2"
    assertEq "annotator-2, nothing answered, incomplete on its own item order"
      (Left (ExportIncomplete (map piId (fxItems2 fixture)))) (either Left (const (Right ())) second)
    first <- exportFor cfg "annotator-1"
    assertEq "annotator-1 still incomplete on its own item order, unaffected by annotator-2"
      (Left (ExportIncomplete ["item-bbbbbb", "item-cccccc"])) (either Left (const (Right ())) first)

  yit "resumes after a restart at the first incomplete item, with earlier answers intact" $ do
    get HomeR
    cookie <- claimSlot
    noneObserved 0
    noneObserved 1
    db <- liftIO (readIORef (fxLastDb fixture))
    landing <- resumeAfterRestart cfg db cookie
    assertEq "resumed at the first incomplete item" "/item/2" landing
    -- the reopened session did not start a second one
    sessions <- sessionCount
    assertEq "one session for the claimed slot" 1 sessions
    noneObserved 2
    outcome <- exportFor cfg "annotator-1"
    assertEq "complete after resuming" (Right 3) (fmap (length . peResponses) outcome)
  where
    quotesFor iid = do
      site <- getTestYesod
      liftIO $ flip runSqlPool (appPool site) $ do
        anns <- selectList [AnnotationItemId ==. iid] []
        case anns of
          [] -> pure []
          (Entity aid _ : _) -> map (evidenceQuote . entityVal) <$> selectList [EvidenceAnnotationId ==. aid] [Asc EvidenceId]

-- ---------------------------------------------------------------- the real package

realPackageSpec :: Maybe RealFixture -> YesodSpec App
realPackageSpec Nothing = ydescribe "the sealed v0.1 package" $
  yit "is not available here (running outside the repository); nothing to prove" $ pure ()
realPackageSpec (Just real) = ydescribe "the sealed v0.1 package, end to end" $
  yit "claim -> 40 items -> restart -> resume -> complete -> canonical export with the sealed hashes" $ do
    let cfg = rfConfig real
        items = rfItems real
        total = length items
    assertEq "the packet has 40 items" 40 total
    get HomeR
    cookie <- claimSlot
    statusIs 200
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
    landing <- resumeAfterRestart cfg db cookie
    assertEq "resumed at item 21" "/item/20" landing
    forM_ [20 .. total - 1] noneObserved
    get DoneR
    statusIs 200
    bodyNotContains "submission.json"
    outcome <- exportFor cfg "annotator-1"
    export <- either (liftIO . fail . T.unpack . renderExportFault) pure outcome
    let responses = peResponses export
        ids = mapMaybe (stringField "item_id") responses
    assertEq "40/40, packet order, each exactly once" (map piId items) ids
    assertEq "feedback on every line" total (length (filter (\r -> field "feedback" r /= Nothing) responses))
    assertEq "the quote is the exact target" (Just (A.String (targetText 0)))
      (field "quotes" (responses !! 0) >>= \q -> case q of A.Array xs | not (null xs) -> field "quote" (toList xs !! 0); _ -> Nothing)
    let bytes = responsesJsonl responses
    assertEq "export record carries the layer hash" (Just (sha256Hex bytes)) (stringField "responses_sha256" (exportRecordValue export bytes))
