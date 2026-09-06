{-# LANGUAGE OverloadedStrings #-}

-- | Serves HTTP against a schema somebody else already put in place.
--
-- This process does not write schema. If the database is not at the version the
-- application expects it says so and exits, because a server that reshapes a
-- production table while starting is how you lose a production table.
module Main (main) where

import Control.Exception (try)
import Data.Maybe (fromMaybe)
import qualified Data.Text as T
import Network.Wai.Handler.Warp (defaultSettings, runSettings, setHost, setPort)
import Schema (SchemaFault, renderSchemaFault)
import Server (makeFoundation)
import System.Environment (lookupEnv)
import System.Exit (exitFailure)
import System.IO (hPutStrLn, stderr)
import Text.Read (readMaybe)
import Yesod (toWaiApp)

main :: IO ()
main = do
  dbPath <- fromMaybe "annotation.db" <$> lookupEnv "RF_DB_PATH"
  sessionKeyPath <- fromMaybe "client-session-key.aes" <$> lookupEnv "RF_SESSION_KEY_PATH"
  secureCookies <- maybe False (`elem` ["1", "true", "yes"]) <$> lookupEnv "RF_SECURE_COOKIES"
  port <- maybe 8080 (fromMaybe 8080 . readMaybe) <$> lookupEnv "PORT"
  started <- try (makeFoundation dbPath sessionKeyPath secureCookies)
  case started of
    Left fault -> do
      hPutStrLn stderr ("annotation-web: " <> T.unpack (renderSchemaFault (fault :: SchemaFault)))
      exitFailure
    Right foundation -> do
      wai <- toWaiApp foundation
      runSettings (setPort port $ setHost "127.0.0.1" defaultSettings) wai
