{-# LANGUAGE OverloadedStrings #-}

-- | The facilitator's collection path: canonical export of one completed pilot
-- session, offline, against the database and the sealed package the server
-- was proving at the time.
--
--   annotation-web-export <package-id> <annotator-id> <out-dir>
--
-- Writes @<annotator-id>.jsonl@ (one rf.pilot-response.v1 line per presented
-- item, packet order) and @<annotator-id>.export.json@ (the package identity
-- and the hash of the response file). Refuses to overwrite either.
module Main (main) where

import Control.Exception (try)
import Control.Monad (unless, when)
import Control.Monad.Logger (runNoLoggingT)
import qualified Data.Aeson.Encode.Pretty as Pretty
import qualified Data.ByteString as BS
import qualified Data.ByteString.Lazy as BL
import Data.Maybe (fromMaybe)
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import Database.Persist.Sqlite (createSqlitePool)
import Export
import Packet (sha256Hex)
import Registry
import Schema (SchemaFault, assertCurrent, renderSchemaFault)
import System.Directory (createDirectoryIfMissing, doesFileExist)
import System.Environment (getArgs, lookupEnv)
import System.Exit (exitFailure)
import System.FilePath ((</>))
import System.IO (hPutStrLn, stderr)

main :: IO ()
main = do
  args <- getArgs
  case args of
    [packageId, annotatorId, outDir] -> run (T.pack packageId) (T.pack annotatorId) outDir
    _ -> do
      hPutStrLn stderr "usage: annotation-web-export <package-id> <annotator-id> <out-dir>"
      hPutStrLn stderr "  RF_DB_PATH, RF_REPO_ROOT, RF_PACKAGE_REGISTRY select the database and the sealed package"
      exitFailure

run :: T.Text -> T.Text -> FilePath -> IO ()
run packageId annotatorId outDir = do
  dbPath <- fromMaybe "annotation.db" <$> lookupEnv "RF_DB_PATH"
  root <- fromMaybe "." <$> lookupEnv "RF_REPO_ROOT"
  registry <- fromMaybe (root </> "data/pilot/package-registry.json") <$> lookupEnv "RF_PACKAGE_REGISTRY"
  loaded <- loadPilotConfig root registry
  cfg <- case loaded of
    Left faults -> complain (T.unlines (map renderRegistryFault faults))
    Right ok -> pure ok
  unless (pcPackageId cfg == packageId) $
    complain ("loaded package is " <> pcPackageId cfg <> ", not " <> packageId)
  schema <- try (assertCurrent dbPath)
  case schema of
    Left fault -> complain (renderSchemaFault (fault :: SchemaFault))
    Right () -> pure ()
  pool <- runNoLoggingT $ createSqlitePool (T.pack dbPath) 1
  result <- exportPilot pool cfg annotatorId
  export <- either (complain . renderExportFault) pure result
  let responses = responsesJsonl (peResponses export)
      recordBytes = BL.toStrict (Pretty.encodePretty' (Pretty.defConfig { Pretty.confIndent = Pretty.Spaces 2 }) (exportRecordValue export responses)) <> "\n"
      responsesPath = outDir </> (T.unpack annotatorId <> ".jsonl")
      recordPath = outDir </> (T.unpack annotatorId <> ".export.json")
  createDirectoryIfMissing True outDir
  existing <- mapM doesFileExist [responsesPath, recordPath]
  when (or existing) $ complain ("refusing to overwrite " <> T.pack responsesPath <> " / " <> T.pack recordPath)
  BS.writeFile responsesPath responses
  BS.writeFile recordPath recordBytes
  TIO.putStrLn ("responses: " <> T.pack responsesPath <> " sha256 " <> sha256Hex responses)
  TIO.putStrLn ("record:    " <> T.pack recordPath)
  unless (null (peResponses export)) $
    TIO.putStrLn ("items: " <> T.pack (show (length (peResponses export))))

complain :: T.Text -> IO a
complain message = do
  hPutStrLn stderr ("annotation-web-export: " <> T.unpack message)
  exitFailure
