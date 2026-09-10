{-# LANGUAGE OverloadedStrings #-}

-- | Serves HTTP against a schema somebody else already put in place.
--
-- This process does not write schema. If the database is not at the version the
-- application expects it says so and exits, because a server that reshapes a
-- production table while starting is how you lose a production table.
--
-- It also does not serve what it cannot prove. Every issuance record in
-- RF_ISSUANCE_DIR is re-derived against the package registry and the sealed
-- files at start; one disagreement and the process exits with the list.
module Main (main) where

import Control.Exception (try)
import Data.Maybe (fromMaybe)
import qualified Data.Map.Strict as Map
import qualified Data.Text as T
import Network.Wai.Handler.Warp (defaultSettings, runSettings, setHost, setPort)
import Registry (BindingConfig (..), loadBindings, renderBindingFault)
import Schema (SchemaFault, renderSchemaFault)
import Server (FoundationConfig (..), makeFoundationWith)
import System.Environment (lookupEnv)
import System.Exit (exitFailure)
import System.FilePath ((</>))
import System.IO (hPutStrLn, stderr)
import Text.Read (readMaybe)
import Yesod (defaultMiddlewaresNoLogging, toWaiAppPlain)

main :: IO ()
main = do
  dbPath <- fromMaybe "annotation.db" <$> lookupEnv "RF_DB_PATH"
  sessionKeyPath <- fromMaybe "client-session-key.aes" <$> lookupEnv "RF_SESSION_KEY_PATH"
  secureCookies <- flag <$> lookupEnv "RF_SECURE_COOKIES"
  dogfood <- flag <$> lookupEnv "RF_DOGFOOD_ENABLED"
  port <- maybe 8080 (fromMaybe 8080 . readMaybe) <$> lookupEnv "PORT"
  root <- fromMaybe "." <$> lookupEnv "RF_REPO_ROOT"
  registry <- fromMaybe (root </> "data/pilot/package-registry.json") <$> lookupEnv "RF_PACKAGE_REGISTRY"
  issuanceDir <- lookupEnv "RF_ISSUANCE_DIR"
  bindings <- case issuanceDir of
    -- No issuance directory: nothing is issued. The dogfood surface, if
    -- enabled, is all this server offers.
    Nothing -> pure Map.empty
    Just dir -> do
      loaded <- loadBindings BindingConfig { bcRepoRoot = root, bcRegistryFile = registry, bcIssuanceDir = dir }
      case loaded of
        Left faults -> do
          hPutStrLn stderr "annotation-web: refusing to start — issuance bindings could not be proven:"
          mapM_ (hPutStrLn stderr . ("  - " <>) . T.unpack . renderBindingFault) faults
          exitFailure
        Right ok -> do
          hPutStrLn stderr ("annotation-web: " <> show (Map.size ok) <> " issuance binding(s) proven")
          pure ok
  started <- try $ makeFoundationWith FoundationConfig
    { fcDbPath = dbPath
    , fcSessionKeyPath = sessionKeyPath
    , fcSecureCookies = secureCookies
    , fcBindings = bindings
    , fcDogfoodEnabled = dogfood
    }
  case started of
    Left fault -> do
      hPutStrLn stderr ("annotation-web: " <> T.unpack (renderSchemaFault (fault :: SchemaFault)))
      exitFailure
    Right foundation -> do
      -- toWaiApp's own default middleware stack includes an unconditional
      -- Apache-format request logger that writes the full request path --
      -- query string and all -- to this process's stdout, which systemd
      -- captures into the journal. /t/<token> IS the request path here, so
      -- that logger would put every bearer token issued into the journal in
      -- cleartext on the very first request, bot or human. toWaiAppPlain
      -- carries no middleware at all; reapplying defaultMiddlewaresNoLogging
      -- (yesod-core's own name for "everything toWaiApp adds, minus the
      -- logger") keeps gzip/autohead/method-and-accept-override and drops
      -- only the logger.
      wai <- defaultMiddlewaresNoLogging <$> toWaiAppPlain foundation
      runSettings (setPort port $ setHost "127.0.0.1" defaultSettings) wai
  where
    flag = maybe False (`elem` ["1", "true", "yes"])
