{-# LANGUAGE OverloadedStrings #-}

-- | The database schema history, owned explicitly rather than inferred.
--
-- Persistent still defines the entity model, the queries and the
-- serialization. What it no longer does is decide, at server start, how to
-- reshape a production database: persistent-sqlite migrates an added column by
-- rebuilding the table, and rebuilding a table that other rows reference fails
-- the foreign key check on the live file. Schema change is a separate,
-- explicit, append-only list of statements applied by a separate executable,
-- and this module is that list plus the checks that say whether a given file
-- is at the end of it.
--
-- The ordering is enforced by @migrant-core@; the bookkeeping table is
-- @migrant-sqlite-simple@'s @_migrations@. Note what that table does and does
-- not give us: it records applied migration names in order, and nothing else.
-- There is no checksum of the migration body, so migrant alone cannot tell
-- that migration 0001 is still the 0001 that was applied to production. What
-- catches that here is 'schemaFingerprint': every run compares the real
-- structure of the file against the structure the current migration list
-- builds from empty, so an edit to an already-applied migration that changes
-- the resulting schema fails loudly on the next run. An edit that leaves the
-- structure identical is not detected, and is a documented limitation rather
-- than a guarantee.
module Schema
  ( -- * The history
    SchemaMigration (..)
  , schemaMigrations
  , migrationNames
    -- * Applying it
  , MigrateReport (..)
  , migrateDatabase
  , migrateDatabaseWith
    -- * Reading a database without changing it
  , SchemaFault (..)
  , renderSchemaFault
  , assertCurrent
  , recordedMigrations
  , schemaFingerprint
  , referenceFingerprint
  , foreignKeyViolations
  , integrityCheck
  , withDatabase
  ) where

import Control.Exception (Exception (..), throwIO)
import Control.Monad (forM, forM_, unless, when)
import Data.List (isPrefixOf, sort, sortOn)
import Data.Text (Text)
import qualified Data.Text as T
import Database.Migrant (Driver (..))
import Database.Migrant.MigrationName (MigrationName (..))
import Database.Migrant.Run (MigrationDirection (..), executePlan, makePlan)
import Database.Migrant.Driver.Sqlite ()
import qualified Database.SQLite.Simple as Sqlite
import Database.SQLite.Simple (SQLData (..))
import System.Directory (doesFileExist)

-- | One step of the history. @smUp@ is a list of single statements because
-- sqlite-simple executes one statement per call, and because a reviewer should
-- be able to read a migration as a list of things it does.
data SchemaMigration = SchemaMigration
  { smName :: MigrationName
  , smUp :: [Sqlite.Query]
  }

-- | The schema history, oldest first. Append only: a migration that has been
-- applied to a database that exists somewhere is not edited, it is followed.
--
-- 0001 is not "the schema as of this commit". It is the schema the production
-- database was already at when explicit migrations were introduced, copied
-- from a real hs-v1 file created by the deployed binary, so that an existing
-- production file can be recognised as being at 0001 instead of being rebuilt.
schemaMigrations :: [SchemaMigration]
schemaMigrations =
  [ SchemaMigration
      { smName = "0001-baseline-hs-v1"
      , smUp =
          [ "CREATE TABLE \"survey_session\"(\
            \\"id\" INTEGER PRIMARY KEY,\
            \\"presentation_language\" VARCHAR NOT NULL,\
            \\"started_at\" TIMESTAMP NOT NULL,\
            \\"completed_at\" TIMESTAMP NULL)"
          , "CREATE TABLE \"annotation\"(\
            \\"id\" INTEGER PRIMARY KEY,\
            \\"survey_session_id\" INTEGER NOT NULL REFERENCES \"survey_session\" ON DELETE RESTRICT ON UPDATE RESTRICT,\
            \\"item_id\" VARCHAR NOT NULL,\
            \\"decision\" VARCHAR NULL,\
            \\"abstention_reason\" VARCHAR NULL,\
            \\"abstention_note\" VARCHAR NULL,\
            \\"original_revealed\" BOOLEAN NOT NULL,\
            \CONSTRAINT \"unique_session_item\" UNIQUE (\"survey_session_id\",\"item_id\"))"
          , "CREATE TABLE \"annotation_label\"(\
            \\"id\" INTEGER PRIMARY KEY,\
            \\"annotation_id\" INTEGER NOT NULL REFERENCES \"annotation\" ON DELETE RESTRICT ON UPDATE RESTRICT,\
            \\"label_id\" VARCHAR NOT NULL,\
            \CONSTRAINT \"unique_annotation_label\" UNIQUE (\"annotation_id\",\"label_id\"))"
          , "CREATE TABLE \"evidence\"(\
            \\"id\" INTEGER PRIMARY KEY,\
            \\"annotation_id\" INTEGER NOT NULL REFERENCES \"annotation\" ON DELETE RESTRICT ON UPDATE RESTRICT,\
            \\"label_id\" VARCHAR NOT NULL,\
            \\"quote\" VARCHAR NOT NULL,\
            \CONSTRAINT \"unique_evidence\" UNIQUE (\"annotation_id\",\"label_id\"))"
          , "CREATE TABLE \"audit_event\"(\
            \\"id\" INTEGER PRIMARY KEY,\
            \\"survey_session_id\" INTEGER NOT NULL REFERENCES \"survey_session\" ON DELETE RESTRICT ON UPDATE RESTRICT,\
            \\"item_id\" VARCHAR NULL,\
            \\"kind\" VARCHAR NOT NULL,\
            \\"value\" VARCHAR NULL,\
            \\"occurred_at\" TIMESTAMP NOT NULL)"
          ]
      }
  , SchemaMigration
      { smName = "0002-session-instrument-and-item-feedback"
      , smUp =
          [ "CREATE TABLE \"session_instrument\"(\
            \\"id\" INTEGER PRIMARY KEY,\
            \\"survey_session_id\" INTEGER NOT NULL REFERENCES \"survey_session\" ON DELETE RESTRICT ON UPDATE RESTRICT,\
            \\"version\" VARCHAR NOT NULL,\
            \CONSTRAINT \"unique_session_instrument\" UNIQUE (\"survey_session_id\"))"
          , "CREATE TABLE \"item_feedback\"(\
            \\"id\" INTEGER PRIMARY KEY,\
            \\"annotation_id\" INTEGER NOT NULL REFERENCES \"annotation\" ON DELETE RESTRICT ON UPDATE RESTRICT,\
            \\"unnatural_example\" BOOLEAN NOT NULL,\
            \\"insufficient_context\" BOOLEAN NOT NULL,\
            \\"wording_or_translation\" BOOLEAN NOT NULL,\
            \\"other\" BOOLEAN NOT NULL,\
            \\"note\" VARCHAR NULL,\
            \CONSTRAINT \"unique_item_feedback\" UNIQUE (\"annotation_id\"))"
          ]
      }
  ]

migrationNames :: [SchemaMigration] -> [MigrationName]
migrationNames = map smName

-- | What a migration run did. An already-current database yields empty
-- 'mrAdopted' and 'mrApplied': that is what a no-op looks like.
data MigrateReport = MigrateReport
  { mrAdopted :: [MigrationName]
    -- ^ Recorded as already applied because the file already had that
    -- structure. Only ever non-empty on a database that predates @_migrations@.
  , mrApplied :: [MigrationName]
    -- ^ Actually executed against the file.
  , mrRecorded :: [MigrationName]
    -- ^ The full history the file claims once the run is done.
  } deriving stock (Eq, Show)

data SchemaFault
  = SchemaFileMissing FilePath
  | SchemaUnrecognised Text
    -- ^ A database with tables in it, no migration history, and a structure
    -- that is not any version this history knows how to continue from.
  | SchemaDiverged [MigrationName] [MigrationName]
    -- ^ Recorded history is not a prefix of the expected one, so reaching the
    -- target would mean rolling something back. This history has no down
    -- migrations and will not guess.
  | SchemaStructureMismatch Text
  | SchemaForeignKeyViolations [Text]
  | SchemaCorrupt [Text]
  | SchemaPending [MigrationName]
    -- ^ Raised by a reader, not a writer: the file is behind the history.
  | SchemaPersistentDisagrees [Text]
    -- ^ Persistent still has schema statements it would like to run, so the
    -- explicit history did not actually reproduce the entity model.
  deriving stock (Eq, Show)

instance Exception SchemaFault where
  displayException = T.unpack . renderSchemaFault

renderSchemaFault :: SchemaFault -> Text
renderSchemaFault fault = case fault of
  SchemaFileMissing path ->
    "no database at " <> T.pack path <> "; annotation-web-migrate creates one, the server does not"
  SchemaUnrecognised detail ->
    "refusing to migrate: this database has tables but no migration history, \
    \and its structure matches no known schema version.\n" <> detail
  SchemaDiverged recorded expected ->
    "refusing to migrate: recorded history is not a prefix of the expected one, \
    \which would require rolling migrations back.\n\
    \  recorded: " <> names recorded <> "\n\
    \  expected: " <> names expected
  SchemaStructureMismatch detail ->
    "schema structure does not match the migration history.\n" <> detail
  SchemaForeignKeyViolations violations ->
    "PRAGMA foreign_key_check reported " <> T.pack (show (length violations)) <> " violation(s):\n"
      <> T.unlines (map ("  " <>) violations)
  SchemaCorrupt complaints ->
    "PRAGMA integrity_check did not return ok:\n" <> T.unlines (map ("  " <>) complaints)
  SchemaPending pending ->
    "database schema is behind the application; run annotation-web-migrate first.\n\
    \  pending: " <> names pending
  SchemaPersistentDisagrees statements ->
    "persistent still wants to change this schema after the explicit migrations ran, \
    \so the migration history does not reproduce the entity model:\n"
      <> T.unlines (map ("  " <>) statements)
  where
    names [] = "(none)"
    names ns = T.intercalate ", " (map unpackMigrationName ns)

-- | Open a database file, run an action, close it. No pooling: the migrator is
-- a one-shot process and the readers below are startup checks.
withDatabase :: FilePath -> (Sqlite.Connection -> IO a) -> IO a
withDatabase path = Sqlite.withConnection path

-- | Bring @path@ to the end of the history, creating the file if it is absent.
migrateDatabase :: FilePath -> IO MigrateReport
migrateDatabase = migrateDatabaseWith schemaMigrations

-- | The same, against an arbitrary history. Tests use this to build a database
-- at an older version, and to watch a failing migration roll back.
migrateDatabaseWith :: [SchemaMigration] -> FilePath -> IO MigrateReport
migrateDatabaseWith history path = withDatabase path $ \conn ->
  -- One transaction covers reading the history, deciding, writing the schema
  -- and verifying the result. SQLite rolls DDL back like anything else, so a
  -- statement that throws leaves the file exactly as it was found.
  Sqlite.withTransaction conn $ do
    initMigrations conn
    recorded0 <- getMigrations conn
    adopted <-
      if null recorded0
        then adoptExistingSchema history conn
        else pure []
    recorded <- getMigrations conn
    let target = migrationNames history
        steps = makePlan target recorded
    when (any ((== MigrateDown) . fst) steps) $
      throwIO (SchemaDiverged recorded target)
    executePlan steps (runUp history) refuseDown conn
    final <- getMigrations conn
    verifySchema history conn
    pure MigrateReport
      { mrAdopted = adopted
      , mrApplied = [n | (MigrateUp, n) <- steps]
      , mrRecorded = final
      }

-- | A database with tables but no @_migrations@ is either a legacy production
-- file or something we have never seen. Decide by structure: find the longest
-- prefix of the history whose from-empty result matches this file exactly, and
-- record that prefix as applied without executing it. An empty file matches the
-- empty prefix and simply gets the whole history run. Anything that matches no
-- prefix is refused; matching some tables is not matching a schema.
adoptExistingSchema :: [SchemaMigration] -> Sqlite.Connection -> IO [MigrationName]
adoptExistingSchema history conn = do
  actual <- schemaFingerprint conn
  candidates <- forM (prefixes history) $ \prefix -> do
    expected <- referenceFingerprint prefix
    pure (prefix, expected)
  case reverse [prefix | (prefix, expected) <- candidates, expected == actual] of
    [] -> do
      full <- referenceFingerprint history
      throwIO . SchemaUnrecognised $
        fingerprintDiff "current schema" actual "schema this history builds" full
    (longest : _) -> do
      let adopted = migrationNames longest
      forM_ adopted $ \name -> markUp name conn
      pure adopted
  where
    prefixes xs = [take n xs | n <- [0 .. length xs]]

runUp :: [SchemaMigration] -> MigrationName -> Sqlite.Connection -> IO ()
runUp history name conn = case filter ((== name) . smName) history of
  (m : _) -> mapM_ (Sqlite.execute_ conn) (smUp m)
  [] -> throwIO (SchemaDiverged [name] (migrationNames history))

-- | There are no down migrations. Reaching this means the plan asked to roll
-- back, which 'migrateDatabaseWith' refuses before executing anything; it is
-- here so the refusal is total rather than a comment.
refuseDown :: MigrationName -> Sqlite.Connection -> IO ()
refuseDown name _ = throwIO (SchemaDiverged [name] [])

-- | Three independent questions about a file: does its structure equal what the
-- history builds from empty, does SQLite consider its references satisfied, and
-- does SQLite consider the file itself sound.
verifySchema :: [SchemaMigration] -> Sqlite.Connection -> IO ()
verifySchema history conn = do
  actual <- schemaFingerprint conn
  expected <- referenceFingerprint history
  unless (actual == expected) $
    throwIO . SchemaStructureMismatch $
      fingerprintDiff "actual" actual "expected" expected
  violations <- foreignKeyViolations conn
  unless (null violations) $ throwIO (SchemaForeignKeyViolations violations)
  integrity <- integrityCheck conn
  unless (integrity == ["ok"]) $ throwIO (SchemaCorrupt integrity)

-- | Read-only startup gate. Refuses a file that is behind the history, ahead of
-- it, or shaped differently from what the history builds.
assertCurrent :: FilePath -> IO ()
assertCurrent path = do
  exists <- doesFileExist path
  unless exists $ throwIO (SchemaFileMissing path)
  withDatabase path $ \conn -> do
    recorded <- recordedMigrations conn
    let expected = migrationNames schemaMigrations
    unless (recorded == expected) $
      if recorded `isPrefixOf` expected
        then throwIO (SchemaPending (drop (length recorded) expected))
        else throwIO (SchemaDiverged recorded expected)
    verifySchema schemaMigrations conn

-- | The history a file claims, or none if it has never been migrated. Does not
-- create @_migrations@: a reader must not write.
recordedMigrations :: Sqlite.Connection -> IO [MigrationName]
recordedMigrations conn = do
  present <- Sqlite.query_ conn
    "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = '_migrations'"
  case present of
    [Sqlite.Only (n :: Int)] | n > 0 -> getMigrations conn
    _ -> pure []

-- | What the history builds from an empty database, as a fingerprint. Computed
-- rather than pinned, so the expectation cannot drift away from the migrations
-- that are actually in the list.
referenceFingerprint :: [SchemaMigration] -> IO Text
referenceFingerprint history =
  Sqlite.withConnection ":memory:" $ \conn -> do
    forM_ history $ \m -> mapM_ (Sqlite.execute_ conn) (smUp m)
    schemaFingerprint conn

-- | A deterministic description of everything SQLite knows about the shape of
-- this database: tables and their columns, their foreign keys, their indexes
-- including the ones a UNIQUE constraint creates, and any view or trigger.
--
-- Built from the pragmas rather than from the text in @sqlite_master@ on
-- purpose. Two files with identical structure can carry different DDL text --
-- persistent writes @CREATE TABLE IF NOT EXISTS@, the migrations here do not --
-- and a test oracle that fails on whitespace is not an oracle. The migration
-- bookkeeping table is excluded: it is history, not schema.
schemaFingerprint :: Sqlite.Connection -> IO Text
schemaFingerprint conn = do
  objects <- rows conn
    "SELECT type, name FROM sqlite_master \
    \WHERE name <> '_migrations' AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' \
    \ORDER BY type, name" ()
  let named kind = sort [nm | [SQLText ty, SQLText nm] <- objects, ty == kind]
  tables <- forM (named "table") $ \table -> do
    columns <- rows conn "SELECT cid, name, type, \"notnull\", dflt_value, pk FROM pragma_table_info(?)" (Sqlite.Only table)
    keys <- rows conn "SELECT id, seq, \"table\", \"from\", \"to\", on_update, on_delete, match FROM pragma_foreign_key_list(?)" (Sqlite.Only table)
    indexes <- rows conn "SELECT name, \"unique\", origin, partial FROM pragma_index_list(?) ORDER BY name" (Sqlite.Only table)
    indexed <- forM indexes $ \ix -> case ix of
      (SQLText name : _) -> do
        cols <- rows conn "SELECT seqno, cid, name FROM pragma_index_info(?) ORDER BY seqno" (Sqlite.Only name)
        pure ("  index " <> render ix : map (("    column " <>) . render) cols)
      _ -> pure ["  index " <> render ix]
    pure $
      ("table " <> table)
        : map (("  column " <>) . render) columns
        ++ map (("  foreign key " <>) . render) (sortOn render keys)
        ++ concat indexed
  let others =
        [ kind <> " " <> nm
        | kind <- ["trigger", "view"]
        , nm <- named kind
        ]
  pure . T.unlines $ concat tables ++ others
  where
    render = T.intercalate "|" . map renderCell

rows :: Sqlite.ToRow q => Sqlite.Connection -> Sqlite.Query -> q -> IO [[SQLData]]
rows conn q = Sqlite.query conn q

renderCell :: SQLData -> Text
renderCell cell = case cell of
  SQLInteger n -> T.pack (show n)
  SQLFloat d -> T.pack (show d)
  SQLText t -> t
  SQLBlob b -> T.pack (show b)
  SQLNull -> "NULL"

-- | The first line where two fingerprints stop agreeing, with a little context.
-- A 40-line diff of two schemas nobody can read is not an error message.
fingerprintDiff :: Text -> Text -> Text -> Text -> Text
fingerprintDiff leftLabel left rightLabel right =
  case [(i, a, b) | (i, a, b) <- zip3 [1 :: Int ..] ls rs, a /= b] of
    ((i, a, b) : _) ->
      "  first difference at line " <> T.pack (show i) <> ":\n"
        <> "    " <> leftLabel <> ": " <> a <> "\n"
        <> "    " <> rightLabel <> ": " <> b
    [] ->
      "  " <> leftLabel <> " has " <> T.pack (show (length ls)) <> " line(s), "
        <> rightLabel <> " has " <> T.pack (show (length rs)) <> "\n"
        <> "    extra: " <> T.intercalate "; " (drop (length rs) ls ++ drop (length ls) rs)
  where
    ls = T.lines left
    rs = T.lines right

-- | @PRAGMA foreign_key_check@, one line per violation, empty when clean.
foreignKeyViolations :: Sqlite.Connection -> IO [Text]
foreignKeyViolations conn = do
  violations <- Sqlite.query_ conn "PRAGMA foreign_key_check" :: IO [[SQLData]]
  pure (map (T.intercalate "|" . map renderCell) violations)

-- | @PRAGMA integrity_check@, which answers @["ok"]@ on a sound file.
integrityCheck :: Sqlite.Connection -> IO [Text]
integrityCheck conn = do
  result <- Sqlite.query_ conn "PRAGMA integrity_check" :: IO [[SQLData]]
  pure (map (T.intercalate "|" . map renderCell) result)
