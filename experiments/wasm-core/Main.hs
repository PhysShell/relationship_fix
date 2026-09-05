{-# LANGUAGE OverloadedStrings #-}

-- | The Relationship Fix protocol core as a WASI command.
--
-- This is a laboratory build, not part of the deployed instrument. It compiles
-- the very same @Domain@ and @Catalog@ modules the Yesod application uses --
-- no fork and no second copy of the rules -- to @wasm32-wasi@, so the wire
-- contract and the evidence rule can be executed without a Linux userspace,
-- without HTTP, without SQLite and without a filesystem.
--
-- The point of the exercise is the trust boundary. A native process is born
-- holding the filesystem, the network and the clock, and we spend systemd
-- directives taking those away again. A WASI command starts holding nothing
-- and is handed capabilities one at a time. The @read@ subcommand exists only
-- to make that difference visible from the outside.
module Main (main) where

import Catalog (items)
import Control.Exception (IOException, try)
import qualified Data.List as List
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import Domain
import GHC.IO.Encoding (setFileSystemEncoding, setLocaleEncoding, utf8)
import System.Environment (getArgs, getProgName)
import System.Exit (exitFailure, exitWith, ExitCode (ExitFailure))
import System.IO (hSetEncoding, stderr, stdout)

main :: IO ()
main = do
  -- The instrument is bilingual, so its output encoding must not depend on
  -- whichever locale the operator happens to have. A host with no LANG set at
  -- all -- a CI runner, a systemd unit, a WASI guest -- otherwise crashes on
  -- the first Cyrillic character. Handles fix their encoding when they are
  -- created, so setting the locale alone is not enough.
  setLocaleEncoding utf8
  setFileSystemEncoding utf8
  hSetEncoding stdout utf8
  hSetEncoding stderr utf8
  args <- getArgs
  case args of
    ["contract"] -> printContract
    ["selftest"] -> selftest
    ["validate", lang, itemid, quote] ->
      validateOne (T.pack lang) (T.pack itemid) (T.pack quote)
    ["read", path] -> readUnderGrant path
    _ -> usage

usage :: IO ()
usage = do
  name <- getProgName
  mapM_ putStrLn
    [ "usage:"
    , "  " <> name <> " contract                          print the wire contract"
    , "  " <> name <> " selftest                          run the protocol invariants"
    , "  " <> name <> " validate LANG ITEM QUOTE          check an evidence span"
    , "  " <> name <> " read PATH                         show what WASI grants"
    ]
  exitWith (ExitFailure 2)

-- | The research contract, printed by the artifact that enforces it.
printContract :: IO ()
printContract = do
  TIO.putStrLn "decisions:"
  mapM_ (TIO.putStrLn . indent . decisionCode) [Assigned, NoneObserved, Abstained]
  TIO.putStrLn "labels:"
  mapM_ (TIO.putStrLn . indent . labelCode) allBehaviorLabels
  TIO.putStrLn "abstention_reasons:"
  mapM_ (TIO.putStrLn . reasonLine) allAbstentionReasons
  TIO.putStrLn "items:"
  mapM_ (TIO.putStrLn . itemLine) items
  where
    indent = ("  " <>)
    reasonLine reason = indent $
      T.justifyLeft 26 ' ' (abstentionCode reason)
        <> if abstentionRequiresNote reason then "note:required" else "note:optional"
    itemLine item = indent $
      T.justifyLeft 10 ' ' (itemId item) <> "source:" <> languageCode (itemSourceLanguage item)

-- | Is this quote an exact continuous span of what the annotator was shown?
validateOne :: Text -> Text -> Text -> IO ()
validateOne rawLang itemid quote =
  case (parseLanguage rawLang, List.find ((== itemid) . itemId) items) of
    (Nothing, _) -> fail' $ "unknown presentation language: " <> rawLang
    (_, Nothing) -> fail' $ "unknown item: " <> itemid
    (Just lang, Just item) -> do
      let target = presentationTarget (presentationFor lang item)
      TIO.putStrLn $ "target:   " <> target
      TIO.putStrLn $ "quote:    " <> quote
      if validEvidence lang item quote
        then TIO.putStrLn "verdict:  accepted"
        else do
          TIO.putStrLn "verdict:  rejected (not an exact continuous span of the target message)"
          exitFailure
  where
    fail' message = TIO.putStrLn message >> exitFailure

-- | The same invariants the native hspec suite asserts, re-run on wasm32-wasi.
selftest :: IO ()
selftest = do
  results <- mapM report checks
  if and results then TIO.putStrLn "selftest: all invariants hold" else exitFailure
  where
    report (name, held) = do
      TIO.putStrLn $ (if held then "PASS  " else "FAIL  ") <> name
      pure held

    dg04 = List.find ((== "dg-04") . itemId) items

    checks :: [(Text, Bool)]
    checks =
      [ ("item ids are unique", let ids = map itemId items in length ids == length (List.nub ids))
      , ("every item has an RU and an EN presentation", all bothPresentations items)
      , ("an RU presentation of an RU source offers no original", maybe False (not . shouldOfferOriginal RU) dg04)
      , ("an EN presentation of an RU source offers the original", maybe False (shouldOfferOriginal EN) dg04)
      , ("an exact span is accepted", maybe False (\i -> validEvidence RU i "оставил окно открытым") dg04)
      , ("a paraphrase is rejected", maybe False (\i -> not (validEvidence RU i "забыл закрыть окно")) dg04)
      , ("blank evidence is rejected", maybe False (\i -> not (validEvidence RU i "   ")) dg04)
      , ("label codes round-trip", map (parseBehaviorLabel . labelCode) allBehaviorLabels == map Just allBehaviorLabels)
      , ("abstention codes round-trip", map (parseAbstentionReason . abstentionCode) allAbstentionReasons == map Just allAbstentionReasons)
      , ("exactly two reasons require a note", filter abstentionRequiresNote allAbstentionReasons == [AmbiguousBetweenLabels, OtherReason])
      ]

    bothPresentations item = all nonEmpty
      [ presentationContext (presentationFor RU item)
      , presentationTarget (presentationFor RU item)
      , presentationContext (presentationFor EN item)
      , presentationTarget (presentationFor EN item)
      ]
    nonEmpty = not . T.null

-- | Denial by default, made visible.
--
-- Under @wasmtime run core.wasm read /etc/hostname@ this fails: the guest was
-- given no directory. Under @wasmtime run --dir /etc core.wasm read /etc/hostname@
-- the same binary succeeds. Nothing about the module changed; the host handed
-- it one more capability.
readUnderGrant :: FilePath -> IO ()
readUnderGrant path = do
  outcome <- try (readFile path) :: IO (Either IOException String)
  case outcome of
    Left err -> do
      putStrLn $ "denied:  " <> show err
      exitFailure
    Right contents ->
      putStrLn $ "granted: " <> show (length contents) <> " bytes from " <> path
