{-# LANGUAGE OverloadedStrings #-}

-- | The sealed presentation packet, read exactly as the research tooling wrote
-- it and nothing else.
--
-- The server's whole knowledge of a pilot package is: one presentation file
-- per annotator (opaque ids, the annotator's own order, rf.pilot-item.v1 rows
-- with nothing but stimulus in them) and the package's CHECKSUMS.sha256, which
-- is the seal. It never opens items.jsonl, presentation-map/ or the manifest:
-- canonical ids and authoring metadata are not the server's to have, so the
-- cheapest way to guarantee they never reach a browser is for the process to
-- never hold them.
--
-- A presentation row that carries an @authoring@ block or any schema other than
-- v1 is refused. That row would be a facilitator file handed to the renderer by
-- mistake, and the renderer's job is to show what it was given, so it must not
-- be given that.
module Packet
  ( PresentedMessage (..)
  , PresentedItem (..)
  , PacketFault (..)
  , renderPacketFault
  , parsePresentation
  , presentedTarget
  , Checksums
  , parseChecksums
  , checksumFor
  , sha256Hex
  , sha256Text
  , sha256File
  ) where

import Control.Monad (forM, unless, when)
import qualified Data.Aeson as A
import qualified Data.Aeson.KeyMap as KeyMap
import Data.Aeson.Types (Parser, parseEither, (.:))
import qualified Data.ByteString as BS
import qualified Data.ByteString.Lazy as BL
import Data.Digest.Pure.SHA (sha256, showDigest)
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import Data.Vector (toList)

data PresentedMessage = PresentedMessage
  { pmId :: Text
  , pmAuthor :: Text
  , pmText :: Text
  }
  deriving stock (Eq, Show)

-- | One row of a presentation file, in the order the file has it.
data PresentedItem = PresentedItem
  { piId :: Text
  , piLanguage :: Text
  , piMessages :: [PresentedMessage]
  , piTargetId :: Text
  }
  deriving stock (Eq, Show)

data PacketFault
  = PacketBadRow Int Text
  | PacketNotStimulus Int
    -- ^ The row carries @authoring@ or a non-v1 schema: not a presentation row.
  | PacketEmpty
  | PacketDuplicateId Text
  | PacketTargetMissing Text
  deriving stock (Eq, Show)

renderPacketFault :: PacketFault -> Text
renderPacketFault fault = case fault of
  PacketBadRow n detail -> "presentation row " <> T.pack (show n) <> ": " <> detail
  PacketNotStimulus n ->
    "presentation row " <> T.pack (show n)
      <> " is not a plain rf.pilot-item.v1 stimulus (authoring metadata or another schema) — refusing to render a facilitator file"
  PacketEmpty -> "presentation file has no items"
  PacketDuplicateId i -> "presentation file repeats item id " <> i
  PacketTargetMissing i -> "presentation item " <> i <> ": target_message_id is not one of its messages"

-- | Parse a presentation JSONL file. Rows keep file order; that order is the
-- annotator's order and is never changed by the server.
parsePresentation :: BS.ByteString -> Either PacketFault [PresentedItem]
parsePresentation raw = do
  let rows = filter (not . BS.null) (BS.split 10 raw)
  items <- forM (zip [1 :: Int ..] rows) $ \(n, line) -> do
    value <- either (Left . PacketBadRow n . T.pack) Right (A.eitherDecodeStrict line)
    object <- case value of
      A.Object o -> Right o
      _ -> Left (PacketBadRow n "not a JSON object")
    when (KeyMap.member "authoring" object) $ Left (PacketNotStimulus n)
    case KeyMap.lookup "schema_version" object of
      Just (A.String "rf.pilot-item.v1") -> pure ()
      _ -> Left (PacketNotStimulus n)
    either (Left . PacketBadRow n . T.pack) Right (parseEither itemParser object)
  when (null items) $ Left PacketEmpty
  let ids = map piId items
  case [i | i <- ids, length (filter (== i) ids) > 1] of
    (dup : _) -> Left (PacketDuplicateId dup)
    [] -> pure ()
  _ <- forM items $ \item ->
    unless (piTargetId item `elem` map pmId (piMessages item)) $ Left (PacketTargetMissing (piId item))
  pure items
  where
    itemParser :: A.Object -> Parser PresentedItem
    itemParser o = do
      iid <- o .: "item_id"
      language <- o .: "language"
      target <- o .: "target_message_id"
      messagesValue <- o .: "messages"
      messages <- case messagesValue of
        A.Array xs -> mapM messageParser (toList xs)
        _ -> fail "messages is not an array"
      when (null messages) $ fail "messages is empty"
      pure PresentedItem { piId = iid, piLanguage = language, piMessages = messages, piTargetId = target }
    messageParser :: A.Value -> Parser PresentedMessage
    messageParser (A.Object m) =
      PresentedMessage <$> m .: "message_id" <*> m .: "author" <*> m .: "text"
    messageParser _ = fail "message is not an object"

-- | The text of the target message, exactly as presented.
presentedTarget :: PresentedItem -> Maybe Text
presentedTarget item =
  case [pmText m | m <- piMessages item, pmId m == piTargetId item] of
    (t : _) -> Just t
    [] -> Nothing

-- | A parsed CHECKSUMS.sha256: relative path → hex digest.
type Checksums = Map.Map Text Text

-- | @sha256sum@ format, as @metrics.materialize seal@ writes it: hex, two
-- spaces, path. Anything else on a line is refused rather than skipped.
parseChecksums :: Text -> Either Text Checksums
parseChecksums content = do
  entries <- forM (filter (not . T.null . T.strip) (T.lines content)) $ \line ->
    case T.breakOn "  " line of
      (digest, rest)
        | T.length digest == 64 && T.all isHex digest && not (T.null rest) ->
            Right (T.strip (T.drop 2 rest), T.toLower digest)
      _ -> Left ("unreadable CHECKSUMS line: " <> line)
  pure (Map.fromList entries)
  where
    isHex c = c `elem` ("0123456789abcdefABCDEF" :: String)

checksumFor :: Text -> Checksums -> Maybe Text
checksumFor = Map.lookup

sha256Hex :: BS.ByteString -> Text
sha256Hex = T.pack . showDigest . sha256 . BL.fromStrict

sha256Text :: Text -> Text
sha256Text = sha256Hex . TE.encodeUtf8

sha256File :: FilePath -> IO Text
sha256File path = sha256Hex <$> BS.readFile path
