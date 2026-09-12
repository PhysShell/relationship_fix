{-# LANGUAGE OverloadedStrings #-}

-- | Serves HTTP against a schema somebody else already put in place.
--
-- This process does not write schema. If the database is not at the version the
-- application expects it says so and exits, because a server that reshapes a
-- production table while starting is how you lose a production table.
--
-- It also does not serve what it cannot prove. With RF_PILOT_ENABLED set, the
-- one issuable package the registry names is re-proven against its seal at
-- start; any disagreement and the process exits with the list rather than
-- serving a package nobody vouched for.
module Main (main) where

import Control.Exception (try)
import Data.Maybe (fromMaybe)
import qualified Data.Text as T
import Network.Wai.Handler.Warp (defaultSettings, runSettings, setHost, setPort)
import Registry (PilotConfig (..), loadPilotConfig, renderRegistryFault)
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
  pilotEnabled <- flag <$> lookupEnv "RF_PILOT_ENABLED"
  port <- maybe 8080 (fromMaybe 8080 . readMaybe) <$> lookupEnv "PORT"
  root <- fromMaybe "." <$> lookupEnv "RF_REPO_ROOT"
  registry <- fromMaybe (root </> "data/pilot/package-registry.json") <$> lookupEnv "RF_PACKAGE_REGISTRY"
  pilotConfig <-
    if not pilotEnabled
      then pure Nothing
      else do
        loaded <- loadPilotConfig root registry
        case loaded of
          Left faults -> do
            hPutStrLn stderr "annotation-web: refusing to start — pilot package could not be proven:"
            mapM_ (hPutStrLn stderr . ("  - " <>) . T.unpack . renderRegistryFault) faults
            exitFailure
          Right cfg -> do
            hPutStrLn stderr $ "annotation-web: pilot package " <> T.unpack (pcPackageId cfg)
              <> " proven, " <> show (length (pcSlots cfg)) <> " slot(s)"
            pure (Just cfg)
  started <- try $ makeFoundationWith FoundationConfig
    { fcDbPath = dbPath
    , fcSessionKeyPath = sessionKeyPath
    , fcSecureCookies = secureCookies
    , fcPilotConfig = pilotConfig
    , fcDogfoodEnabled = dogfood
    }
  case started of
    Left fault -> do
      hPutStrLn stderr ("annotation-web: " <> T.unpack (renderSchemaFault (fault :: SchemaFault)))
      exitFailure
    Right foundation -> do
      -- toWaiApp's own default middleware stack includes an unconditional
      -- Apache-format request logger that writes the full request path to
      -- this process's stdout, which systemd captures into the journal.
      -- Simple pilot mode no longer puts a bearer token in the path, but
      -- there is still no reason to hand every request path to the journal
      -- unasked. toWaiAppPlain carries no middleware at all; reapplying
      -- defaultMiddlewaresNoLogging (yesod-core's own name for "everything
      -- toWaiApp adds, minus the logger") keeps gzip/autohead/method-and-
      -- accept-override and drops only the logger.
      wai <- defaultMiddlewaresNoLogging <$> toWaiAppPlain foundation
      runSettings (setPort port $ setHost "127.0.0.1" defaultSettings) wai
  where
    flag = maybe False (`elem` ["1", "true", "yes"])
