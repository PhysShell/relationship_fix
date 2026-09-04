{-# LANGUAGE ForeignFunctionInterface #-}

-- | Canonical ABI transport for the Relationship Fix validator component.
--
-- This module is deliberately stupid. It decodes what the Component Model
-- canonical ABI hands it, calls the rules that already exist in "Domain", and
-- encodes the answer back. It contains no protocol rule of its own: no notion
-- of what an exact span is, of when an original may be revealed, or of what a
-- label means. If a rule ever appears here, the experiment has failed its own
-- acceptance criterion, because the rules must stay single-source in Haskell
-- domain modules that know nothing about WebAssembly.
module Abi where

import Catalog (items)
import qualified Data.ByteString.Unsafe as BSU
import Data.Int (Int32)
import qualified Data.List as List
import Data.Text (Text)
import qualified Data.Text.Encoding as TE
import Data.Word (Word8)
import Domain
import Foreign.Ptr (Ptr, castPtr)

-- | @validate-evidence: func(language, item-id: string, quote: string) -> bool@
--
-- Flattened by the canonical ABI to (enum discriminant, ptr, len, ptr, len)
-- returning a single i32. The export is renamed to its canonical WIT name
-- after linking; see build.sh for why that step has to exist at all.
foreign export ccall "validate_evidence" validateEvidence
  :: Int32 -> Ptr Word8 -> Int32 -> Ptr Word8 -> Int32 -> IO Int32

validateEvidence :: Int32 -> Ptr Word8 -> Int32 -> Ptr Word8 -> Int32 -> IO Int32
validateEvidence rawLanguage itemPtr itemLen quotePtr quoteLen = do
  itemid <- peekText itemPtr itemLen
  quote <- peekText quotePtr quoteLen
  pure $ case (decodeLanguage rawLanguage, List.find ((== itemid) . itemId) items) of
    (Just lang, Just item) -> encodeBool (validEvidence lang item quote)
    _ -> encodeBool False

-- | WIT enum cases are ordered, and this component's @language@ enum lists its
-- cases in the same order as the 'Language' constructors, so the discriminant
-- is the constructor index. 'Bounded' keeps the two from drifting apart.
decodeLanguage :: Int32 -> Maybe Language
decodeLanguage discriminant
  | discriminant < 0 = Nothing
  | fromIntegral discriminant > fromEnum (maxBound :: Language) = Nothing
  | otherwise = Just (toEnum (fromIntegral discriminant))

peekText :: Ptr Word8 -> Int32 -> IO Text
peekText ptr len = TE.decodeUtf8 <$> BSU.unsafePackCStringLen (castPtr ptr, fromIntegral len)

encodeBool :: Bool -> Int32
encodeBool True = 1
encodeBool False = 0
