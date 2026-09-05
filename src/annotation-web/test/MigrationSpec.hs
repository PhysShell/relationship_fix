{-# LANGUAGE OverloadedStrings #-}

-- | The migration layer, judged by something other than itself.
--
-- Migrant reports what it applied; that is the producer talking. The checks
-- here ask SQLite what the file actually looks like, ask persistent whether the
-- entity model is satisfied, and ask the historical rows whether they survived.
module MigrationSpec (spec) where

import Control.Exception (try)
import Control.Monad (forM_)
import qualified Data.ByteString as BS
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import qualified Database.SQLite.Simple as Sqlite
import qualified Database.SQLite3 as Direct
import Schema
import Server (makeFoundation, pendingEntityChangesAt)
import System.Directory (doesFileExist)
import System.FilePath ((</>))
import System.IO.Temp (withSystemTempDirectory)
import Test.Hspec

spec :: Spec
spec = do
  freshDatabaseSpec
  legacyDatabaseSpec
  serverGateSpec
  failClosedSpec

-- | A database file inside a temporary directory. The file is not created:
-- whether a path that does not exist yet is allowed to become a database is
-- exactly one of the things under test.
withTempDb :: (FilePath -> IO a) -> IO a
withTempDb act =
  withSystemTempDirectory "annotation-web-migration" $ \dir ->
    act (dir </> "annotation.db")

-- | The committed dump of a real hs-v1 database, replayed into a new file. See
-- test/fixtures/hs-v1-legacy.sql for where that dump came from.
loadLegacyFixture :: FilePath -> IO ()
loadLegacyFixture path = do
  -- Decoded explicitly rather than through the ambient locale: the fixture has
  -- Cyrillic in it, and a test that only passes under a UTF-8 LANG is a test
  -- that will fail on the first machine that does not set one.
  script <- TE.decodeUtf8 <$> BS.readFile ("test" </> "fixtures" </> "hs-v1-legacy.sql")
  Sqlite.withConnection path $ \conn ->
    Direct.exec (Sqlite.connectionHandle conn) script

query1 :: Sqlite.Query -> FilePath -> IO Int
query1 q path = Sqlite.withConnection path $ \conn -> do
  result <- Sqlite.query_ conn q
  pure (case result of [Sqlite.Only n] -> n; _ -> -1)

tableNames :: FilePath -> IO [T.Text]
tableNames path = Sqlite.withConnection path $ \conn ->
  map Sqlite.fromOnly
    <$> Sqlite.query_ conn "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"

baselineOnly :: [SchemaMigration]
baselineOnly = take 1 schemaMigrations

-- | A history whose last step half succeeds: the first statement is fine, the
-- second is not SQL at all.
withBrokenTail :: [SchemaMigration] -> [SchemaMigration]
withBrokenTail history =
  history
    ++ [ SchemaMigration
           { smName = "9999-deliberately-broken"
           , smUp =
               [ "CREATE TABLE \"halfway\"(\"id\" INTEGER PRIMARY KEY)"
               , "THIS IS NOT SQL"
               ]
           }
       ]

freshDatabaseSpec :: Spec
freshDatabaseSpec = describe "a database built from nothing" $ do
  it "runs the whole history and records it" $ withTempDb $ \db -> do
    report <- migrateDatabase db
    mrAdopted report `shouldBe` []
    mrApplied report `shouldBe` migrationNames schemaMigrations
    mrRecorded report `shouldBe` migrationNames schemaMigrations

  it "matches the structure the history describes, with references and file intact" $ withTempDb $ \db -> do
    _ <- migrateDatabase db
    expected <- referenceFingerprint schemaMigrations
    Sqlite.withConnection db $ \conn -> do
      actual <- schemaFingerprint conn
      actual `shouldBe` expected
      foreignKeyViolations conn `shouldReturn` []
      integrityCheck conn `shouldReturn` ["ok"]

  it "leaves persistent with nothing left to change" $ withTempDb $ \db -> do
    _ <- migrateDatabase db
    pendingEntityChangesAt db `shouldReturn` []

  it "does nothing at all the second time" $ withTempDb $ \db -> do
    _ <- migrateDatabase db
    again <- migrateDatabase db
    mrAdopted again `shouldBe` []
    mrApplied again `shouldBe` []
    mrRecorded again `shouldBe` migrationNames schemaMigrations

  it "continues a recorded history forward instead of adopting it again" $ withTempDb $ \db -> do
    first <- migrateDatabaseWith baselineOnly db
    mrApplied first `shouldBe` migrationNames baselineOnly
    second <- migrateDatabase db
    mrAdopted second `shouldBe` []
    mrApplied second `shouldBe` drop 1 (migrationNames schemaMigrations)

  it "distinguishes the versions it is comparing against" $ do
    v1 <- referenceFingerprint baselineOnly
    current <- referenceFingerprint schemaMigrations
    v1 `shouldNotBe` current

legacyDatabaseSpec :: Spec
legacyDatabaseSpec = describe "a real hs-v1 database created by the old binary" $ do
  it "is recognised as the baseline rather than rebuilt" $ withTempDb $ \db -> do
    loadLegacyFixture db
    report <- migrateDatabase db
    mrAdopted report `shouldBe` migrationNames baselineOnly
    mrApplied report `shouldBe` drop 1 (migrationNames schemaMigrations)
    mrRecorded report `shouldBe` migrationNames schemaMigrations

  it "keeps every historical row" $ withTempDb $ \db -> do
    loadLegacyFixture db
    countsBefore <- mapM (`query1` db) counted
    _ <- migrateDatabase db
    countsAfter <- mapM (`query1` db) counted
    countsAfter `shouldBe` countsBefore
    -- and not just the same number of rows, the same rows
    query1 "SELECT count(*) FROM annotation WHERE survey_session_id = 1" db `shouldReturn` 6
    query1 "SELECT count(*) FROM evidence" db `shouldReturn` 6
    query1 "SELECT count(*) FROM annotation WHERE decision = 'abstained' \
           \AND abstention_reason = 'insufficient_context' AND abstention_note IS NOT NULL" db
      `shouldReturn` 1
    query1 "SELECT count(*) FROM annotation WHERE original_revealed = 1" db `shouldReturn` 2
    query1 "SELECT count(*) FROM survey_session WHERE completed_at IS NOT NULL" db `shouldReturn` 1
  where
    counted =
      [ "SELECT count(*) FROM survey_session"
      , "SELECT count(*) FROM annotation"
      , "SELECT count(*) FROM annotation_label"
      , "SELECT count(*) FROM evidence"
      , "SELECT count(*) FROM audit_event"
      ]

serverGateSpec :: Spec
serverGateSpec = describe "the migrated file, checked by someone other than the migrator" $ do
  it "satisfies SQLite and persistent independently" $ withTempDb $ \db -> do
    loadLegacyFixture db
    _ <- migrateDatabase db
    expected <- referenceFingerprint schemaMigrations
    Sqlite.withConnection db $ \conn -> do
      schemaFingerprint conn `shouldReturn` expected
      foreignKeyViolations conn `shouldReturn` []
      integrityCheck conn `shouldReturn` ["ok"]
    pendingEntityChangesAt db `shouldReturn` []

  it "leaves the historical sessions without an instrument row, which is what hs-v1 means" $ withTempDb $ \db -> do
    loadLegacyFixture db
    _ <- migrateDatabase db
    query1 "SELECT count(*) FROM session_instrument" db `shouldReturn` 0
    query1 "SELECT count(*) FROM item_feedback" db `shouldReturn` 0

  it "starts the server, twice" $ withTempDb $ \db -> do
    loadLegacyFixture db
    _ <- migrateDatabase db
    _ <- makeFoundation db (db <> ".key") False
    _ <- makeFoundation db (db <> ".key") False
    pure ()

  it "refuses to start on a legacy database nobody has migrated yet" $ withTempDb $ \db -> do
    loadLegacyFixture db
    outcome <- try (makeFoundation db (db <> ".key") False)
    case outcome of
      -- The old binary left no migration history behind, so from the server's
      -- side this is a database with everything still pending. Whether it is
      -- adoptable at all is the migrator's question, not the server's; the
      -- server's job here is to not serve and to say which tool to run.
      Left (SchemaPending unapplied) ->
        unapplied `shouldBe` migrationNames schemaMigrations
      other -> expectationFailure ("expected a pending schema, got " <> summarise other)

  it "refuses to start on a database that is merely behind" $ withTempDb $ \db -> do
    _ <- migrateDatabaseWith baselineOnly db
    outcome <- try (makeFoundation db (db <> ".key") False)
    case outcome of
      Left (SchemaPending unapplied) ->
        unapplied `shouldBe` drop 1 (migrationNames schemaMigrations)
      other -> expectationFailure ("expected a pending schema, got " <> summarise other)

  it "will not create a database of its own" $ withTempDb $ \db -> do
    outcome <- try (makeFoundation db (db <> ".key") False)
    case outcome of
      Left (SchemaFileMissing path) -> path `shouldBe` db
      other -> expectationFailure ("expected a missing file, got " <> summarise other)
    doesFileExist db `shouldReturn` False

failClosedSpec :: Spec
failClosedSpec = describe "a database the history does not recognise" $ do
  forM_ damaged $ \(what, damage) ->
    it ("is refused, not adopted: " <> what) $ withTempDb $ \db -> do
      loadLegacyFixture db
      Sqlite.withConnection db $ \conn -> mapM_ (Sqlite.execute_ conn) damage
      tablesBefore <- tableNames db
      outcome <- try (migrateDatabase db)
      case outcome of
        Left (SchemaUnrecognised _) -> pure ()
        other -> expectationFailure ("expected an unrecognised schema, got " <> summarise other)
      -- refusing means refusing to have written anything
      tableNames db `shouldReturn` tablesBefore
      query1 "SELECT count(*) FROM sqlite_master WHERE name = '_migrations'" db `shouldReturn` 0

  it "rolls a failing migration back whole, including its bookkeeping" $ withTempDb $ \db -> do
    loadLegacyFixture db
    rowsBefore <- query1 "SELECT count(*) FROM annotation" db
    outcome <- try (migrateDatabaseWith (withBrokenTail baselineOnly) db)
    case outcome of
      Left (_ :: Sqlite.SQLError) -> pure ()
      Right report -> expectationFailure ("expected the broken migration to fail, got " <> show report)
    query1 "SELECT count(*) FROM sqlite_master WHERE name = 'halfway'" db `shouldReturn` 0
    query1 "SELECT count(*) FROM sqlite_master WHERE name = '_migrations'" db `shouldReturn` 0
    query1 "SELECT count(*) FROM annotation" db `shouldReturn` rowsBefore

  it "refuses a history it cannot reach without rolling something back" $ withTempDb $ \db -> do
    _ <- migrateDatabase db
    Sqlite.withConnection db $ \conn ->
      Sqlite.execute_ conn "INSERT INTO _migrations (name) VALUES ('0003-from-the-future')"
    outcome <- try (migrateDatabase db)
    case outcome of
      Left (SchemaDiverged recorded expected) -> do
        recorded `shouldBe` (migrationNames schemaMigrations <> ["0003-from-the-future"])
        expected `shouldBe` migrationNames schemaMigrations
      other -> expectationFailure ("expected a diverged history, got " <> summarise other)
  where
    damaged =
      [ ( "an extra column"
        , ["ALTER TABLE \"evidence\" ADD COLUMN \"extra\" VARCHAR NULL"]
        )
      , ( "a dropped unique constraint"
        , [ "DROP TABLE \"annotation_label\""
          , "CREATE TABLE \"annotation_label\"(\"id\" INTEGER PRIMARY KEY,\
            \\"annotation_id\" INTEGER NOT NULL REFERENCES \"annotation\" ON DELETE RESTRICT ON UPDATE RESTRICT,\
            \\"label_id\" VARCHAR NOT NULL)"
          ]
        )
      , ( "a dropped foreign key"
        , [ "DROP TABLE \"evidence\""
          , "CREATE TABLE \"evidence\"(\"id\" INTEGER PRIMARY KEY,\
            \\"annotation_id\" INTEGER NOT NULL,\
            \\"label_id\" VARCHAR NOT NULL,\
            \\"quote\" VARCHAR NOT NULL,\
            \CONSTRAINT \"unique_evidence\" UNIQUE (\"annotation_id\",\"label_id\"))"
          ]
        )
      , ( "a table nobody asked for"
        , ["CREATE TABLE \"surprise\"(\"id\" INTEGER PRIMARY KEY)"]
        )
      ]

summarise :: Either SchemaFault a -> String
summarise (Left fault) = T.unpack (renderSchemaFault fault)
summarise (Right _) = "no complaint at all"
