{-# LANGUAGE OverloadedStrings #-}

-- | The only path that is allowed to write schema, and the read-only questions
-- a deployment needs to ask about a database file.
--
-- The server no longer migrates anything: it opens a database, checks that the
-- database is at the end of the schema history, and refuses to serve if it is
-- not. This executable is the other half of that split. It applies the explicit
-- migrations, verifies the result and exits; deployment runs it, the server
-- does not.
--
-- The read-only modes exist so the activation script can inspect a database
-- without a sqlite3 binary on the host, and without the shell reimplementing
-- anything this program already knows.
module Main (main) where

import Control.Exception (try)
import Data.Maybe (fromMaybe)
import qualified Database.SQLite.Simple as Sqlite
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import Database.Migrant.MigrationName (unpackMigrationName)
import Schema
  ( MigrateReport (..)
  , SchemaFault (..)
  , assertCurrent
  , dataFingerprint
  , foreignKeyViolations
  , integrityCheck
  , migrateDatabase
  , renderSchemaFault
  , withDatabase
  )
import System.Directory (doesFileExist)
import System.Environment (getArgs, getProgName, lookupEnv)
import System.Exit (exitFailure, exitWith, ExitCode (..))
import System.IO (hPutStrLn, stderr)

main :: IO ()
main = do
  dbPath <- fromMaybe "annotation.db" <$> lookupEnv "RF_DB_PATH"
  args <- getArgs
  case args of
    [] -> runMigrate dbPath
    ["migrate"] -> runMigrate dbPath
    ["verify"] -> runVerify dbPath
    ["integrity"] -> runIntegrity dbPath
    ["data-fingerprint"] -> runDataFingerprint dbPath
    _ -> usage

usage :: IO ()
usage = do
  self <- getProgName
  mapM_ (hPutStrLn stderr)
    [ "usage: " <> self <> " [migrate|verify|integrity|data-fingerprint]"
    , ""
    , "  migrate           apply the schema history to RF_DB_PATH (default)"
    , "  verify            exit 0 only if RF_DB_PATH is at the end of the history"
    , "  integrity         exit 0 only if RF_DB_PATH is a sound SQLite file;"
    , "                    says nothing about schema version, so it is usable on a"
    , "                    database from an older release"
    , "  data-fingerprint  print a digest of the stored rows, for deciding whether"
    , "                    restoring a backup would destroy anything"
    , ""
    , "RF_DB_PATH selects the database for every mode."
    ]
  exitWith (ExitFailure 2)

-- | Everything this program can fail at is reported as one readable line, not
-- as an uncaught exception with a GHC backtrace: an operator reading
-- `journalctl` after a failed deploy is the audience, and a deploy script
-- deciding whether to roll back is the other one.
--
-- Both layers are needed. A schema this program understands and rejects throws
-- 'SchemaFault'; a file too damaged to read at all throws from SQLite itself,
-- from inside a pragma, and that is precisely the case where a legible message
-- matters most.
guarded :: IO a -> IO a
guarded = reportingDatabaseErrors . reportingFaults

reportingFaults :: IO a -> IO a
reportingFaults action = do
  outcome <- try action
  case outcome of
    Right value -> pure value
    Left fault -> complain (renderSchemaFault (fault :: SchemaFault))

reportingDatabaseErrors :: IO a -> IO a
reportingDatabaseErrors action = do
  outcome <- try action
  case outcome of
    Right value -> pure value
    Left err ->
      complain ("this file could not be read as a database: " <> T.pack (show (err :: Sqlite.SQLError)))

complain :: T.Text -> IO a
complain message = do
  self <- getProgName
  hPutStrLn stderr (self <> ": " <> T.unpack message)
  exitFailure

runMigrate :: FilePath -> IO ()
runMigrate dbPath = guarded $ do
  report <- migrateDatabase dbPath
  TIO.putStrLn ("database: " <> T.pack dbPath)
  emit "adopted as already applied" (mrAdopted report)
  emit "applied" (mrApplied report)
  emit "schema history" (mrRecorded report)
  where
    emit label names = TIO.putStrLn (label <> ": " <> render names)
    render [] = "(none)"
    render ns = T.intercalate ", " (map unpackMigrationName ns)

runVerify :: FilePath -> IO ()
runVerify dbPath = guarded $ do
  assertCurrent dbPath
  TIO.putStrLn "schema: current"

-- | Deliberately has no opinion about schema version. This runs against the
-- database as the *previous* release left it, before any migration, where
-- "is this file sound" is a fair question and "is this file current" is not.
runIntegrity :: FilePath -> IO ()
runIntegrity dbPath = guarded $ do
  present <- doesFileExist dbPath
  if not present
    then complain ("no database at " <> T.pack dbPath)
    else withDatabase dbPath $ \conn -> do
      integrity <- integrityCheck conn
      violations <- foreignKeyViolations conn
      TIO.putStrLn ("integrity_check: " <> T.intercalate "; " integrity)
      TIO.putStrLn ("foreign_key_check: " <> if null violations
        then "clean"
        else T.pack (show (length violations)) <> " violation(s)")
      if integrity == ["ok"] && null violations
        then pure ()
        else exitFailure

runDataFingerprint :: FilePath -> IO ()
runDataFingerprint dbPath = guarded $ withDatabase dbPath $ \conn ->
  dataFingerprint conn >>= TIO.putStrLn
