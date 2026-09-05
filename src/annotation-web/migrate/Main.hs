{-# LANGUAGE OverloadedStrings #-}

-- | The only path that is allowed to write schema.
--
-- The server no longer migrates anything: it opens a database, checks that the
-- database is at the end of the schema history, and refuses to serve if it is
-- not. This executable is the other half of that split. It applies the explicit
-- migrations, verifies the result and exits; deployment runs it, the server
-- does not.
module Main (main) where

import Control.Exception (try)
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import Database.Migrant.MigrationName (unpackMigrationName)
import Schema
  ( MigrateReport (..)
  , SchemaFault
  , migrateDatabase
  , renderSchemaFault
  )
import System.Environment (lookupEnv)
import System.Exit (exitFailure)
import System.IO (hPutStrLn, stderr)
import Data.Maybe (fromMaybe)

main :: IO ()
main = do
  dbPath <- fromMaybe "annotation.db" <$> lookupEnv "RF_DB_PATH"
  result <- try (migrateDatabase dbPath)
  case result of
    Left fault -> do
      hPutStrLn stderr ("annotation-web-migrate: " <> T.unpack (renderSchemaFault (fault :: SchemaFault)))
      exitFailure
    Right report -> do
      TIO.putStrLn ("database: " <> T.pack dbPath)
      report `reportLine` ("adopted as already applied", mrAdopted)
      report `reportLine` ("applied", mrApplied)
      report `reportLine` ("schema history", mrRecorded)
  where
    reportLine report (label, field) =
      TIO.putStrLn (label <> ": " <> names (field report))
    names [] = "(none)"
    names ns = T.intercalate ", " (map unpackMigrationName ns)
