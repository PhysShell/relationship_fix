{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Data.Maybe (fromMaybe)
import Network.Wai.Handler.Warp (defaultSettings, runSettings, setHost, setPort)
import Server (makeFoundation)
import System.Environment (lookupEnv)
import Text.Read (readMaybe)
import Yesod (toWaiApp)

main :: IO ()
main = do
  dbPath <- fromMaybe "annotation.db" <$> lookupEnv "RF_DB_PATH"
  sessionKeyPath <- fromMaybe "client-session-key.aes" <$> lookupEnv "RF_SESSION_KEY_PATH"
  secureCookies <- maybe False (`elem` ["1", "true", "yes"]) <$> lookupEnv "RF_SECURE_COOKIES"
  port <- maybe 8080 (fromMaybe 8080 . readMaybe) <$> lookupEnv "PORT"
  foundation <- makeFoundation dbPath sessionKeyPath secureCookies
  wai <- toWaiApp foundation
  runSettings (setPort port $ setHost "127.0.0.1" defaultSettings) wai
