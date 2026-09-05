{-# LANGUAGE ForeignFunctionInterface #-}

-- | Canonical ABI transport for the Relationship Fix validator component.
--
-- This module is deliberately stupid. It decodes what the Component Model
-- canonical ABI hands it, calls the rules that already exist in "Domain", and
-- encodes the answer back. It contains no protocol rule of its own: it does
-- not know what an exact span is, when an original may be revealed, or what a
-- label means. The one distinction the interface draws -- a blank answer
-- against a wrong one -- is 'checkEvidence' in "Domain", not a test written
-- here. If a rule ever appears in this file, the experiment has failed its own
-- acceptance criterion.
--
-- What it does contain is the memory layout that @result\<accepted-evidence,
-- validation-error\>@ has in linear memory, computed by hand:
--
-- >  offset  size  meaning
-- >       0     1  result discriminant   0 = ok, 1 = err
-- >       4    16  payload
-- >
-- >  ok(accepted-evidence)          err(validation-error)
-- >   +4  displayed-target ptr       +4  error discriminant
-- >   +8  displayed-target len       +8  unknown-item ptr
-- >  +12  quote ptr                 +12  unknown-item len
-- >  +16  quote len
--
-- A record of two strings is 16 bytes at alignment 4; the error variant is a
-- one-byte discriminant padded to 4 plus an 8-byte string, so 12; the result
-- variant is a one-byte discriminant padded to 4 plus the larger of the two,
-- so 20. Five flattened i32 results exceed the one the ABI will return in a
-- register, so the whole thing travels through a pointer and is freed
-- afterwards by the post-return in cabi_realloc.c.
module Abi where

import Catalog (items)
import Control.Exception (evaluate)
import qualified Data.ByteString as BS
import Data.Int (Int32)
import qualified Data.List as List
import Data.Text (Text)
import qualified Data.Text.Encoding as TE
import Data.Word (Word8)
import Domain
import Foreign.Marshal.Utils (copyBytes, fillBytes)
import Foreign.Ptr (Ptr, castPtr, nullPtr, ptrToWordPtr)
import Foreign.Storable (pokeByteOff)

foreign import ccall unsafe "cabi_realloc" cabiRealloc
  :: Ptr Word8 -> Int32 -> Int32 -> Int32 -> IO (Ptr Word8)

foreign import ccall unsafe "free" cabiFree :: Ptr Word8 -> IO ()

-- | Size of @result\<accepted-evidence, validation-error\>@ in linear memory.
resultSize :: Int
resultSize = 20

foreign export ccall "validate_evidence" validateEvidence
  :: Int32 -> Ptr Word8 -> Int32 -> Ptr Word8 -> Int32 -> IO Int32

validateEvidence :: Int32 -> Ptr Word8 -> Int32 -> Ptr Word8 -> Int32 -> IO Int32
validateEvidence rawLanguage itemPtr itemLen quotePtr quoteLen = do
  itemid <- peekString itemPtr itemLen
  quote <- peekString quotePtr quoteLen
  -- The host lowered these two strings into our memory using our own
  -- allocator, and has no way to release them afterwards. They are ours now.
  releaseString itemPtr itemLen
  releaseString quotePtr quoteLen

  result <- allocate resultSize
  fillBytes result 0 resultSize
  case (decodeLanguage rawLanguage, List.find ((== itemid) . itemId) items) of
    (Just lang, Just item) -> case checkEvidence lang item quote of
      Right accepted -> do
        pokeByteOff result 0 (0 :: Word8)
        pokeString result 4 (presentationTarget (presentationFor lang item))
        pokeString result 12 accepted
      Left EvidenceBlank -> pokeError result 1 Nothing
      Left EvidenceNotASpan -> pokeError result 2 Nothing
    -- An out-of-range language discriminant cannot arrive through a
    -- well-formed component call; the lift validates the enum. Reaching here
    -- means the pair (language, item) names nothing we hold.
    _ -> pokeError result 0 (Just itemid)
  pure (pointerToI32 result)

-- | @err(case)@, with the payload of @unknown-item@ when there is one.
pokeError :: Ptr Word8 -> Word8 -> Maybe Text -> IO ()
pokeError base caseIndex payload = do
  pokeByteOff base 0 (1 :: Word8)
  pokeByteOff base 4 caseIndex
  case payload of
    Just value -> pokeString base 8 value
    Nothing -> pure ()

-- | WIT enum cases are ordered, and this component's @language@ enum lists its
-- cases in the same order as the 'Language' constructors, so the discriminant
-- is the constructor index. 'Bounded' keeps the two from drifting apart.
decodeLanguage :: Int32 -> Maybe Language
decodeLanguage discriminant
  | discriminant < 0 = Nothing
  | fromIntegral discriminant > fromEnum (maxBound :: Language) = Nothing
  | otherwise = Just (toEnum (fromIntegral discriminant))

allocate :: Int -> IO (Ptr Word8)
allocate size = cabiRealloc nullPtr 0 4 (fromIntegral size)

pointerToI32 :: Ptr a -> Int32
pointerToI32 = fromIntegral . ptrToWordPtr

-- | Copies, and forces the decode before returning.
--
-- The obvious version -- @decodeUtf8 \<$\> unsafePackCStringLen@ -- shares the
-- host's buffer and defers the decode into a thunk. Freeing the parameter
-- afterwards then leaves the decode reading memory that has been handed back
-- to the allocator, and because that memory is merely recycled rather than
-- unmapped, the failure is silent: every string arrived with the right length
-- and nothing but zero bytes in it. Laziness and manual ownership do not mix
-- by accident.
peekString :: Ptr Word8 -> Int32 -> IO Text
peekString ptr len = do
  bytes <- BS.packCStringLen (castPtr ptr, fromIntegral len)
  evaluate (TE.decodeUtf8 bytes)

-- | A zero-length string need not have been allocated at all, so only release
-- what the host can actually have asked our allocator for.
releaseString :: Ptr Word8 -> Int32 -> IO ()
releaseString ptr len
  | len > 0 = cabiFree ptr
  | otherwise = pure ()

-- | Writes a fresh UTF-8 buffer and its @(ptr, len)@ pair at @offset@. The
-- buffer is owned by the caller of the export until post-return frees it.
pokeString :: Ptr Word8 -> Int -> Text -> IO ()
pokeString base offset value = do
  let bytes = TE.encodeUtf8 value
      len = BS.length bytes
  buffer <- allocate (max len 1)
  BS.useAsCStringLen bytes $ \(source, size) ->
    copyBytes buffer (castPtr source) size
  pokeByteOff base offset (pointerToI32 buffer)
  pokeByteOff base (offset + 4) (fromIntegral len :: Int32)
