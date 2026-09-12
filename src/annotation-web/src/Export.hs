{-# LANGUAGE OverloadedStrings #-}

-- | Canonical export of one pilot session: the facilitator's collection path.
--
-- Nothing here is shown to the annotator. The export reads the bound session
-- from the database, walks the packet in the packet's own order, refuses a
-- session that is not complete, and writes one @rf.pilot-response.v1@ line per
-- presented item -- the format @metrics.agreement@ consumes -- plus an export
-- record that repeats the package identity and hashes so the file can be
-- tied back to exactly which sealed package produced it.
--
-- Feedback semantics are the instruction's: the channel was offered on every
-- item of a pilot session, so every line carries @feedback@; an item where the
-- disclosure was never opened, or opened and left empty, exports as
-- @{"flags": [], "note": ""}@. Whether that is meaningful is the report's
-- question (any flag, or a non-blank note), not the collector's.
module Export
  ( PilotExport (..)
  , ExportFault (..)
  , renderExportFault
  , exportPilot
  , responsesJsonl
  , exportRecordValue
  ) where

import Control.Monad (forM)
import qualified Data.Aeson as A
import Data.Aeson ((.=), object)
import qualified Data.ByteString as BS
import qualified Data.ByteString.Lazy as BL
import Data.Maybe (catMaybes, fromMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import Data.Time (UTCTime)
import Database.Persist.Sql (ConnectionPool, Entity (..), SelectOpt (Asc), SqlPersistT, get, getBy, runSqlPool, selectList, (==.))
import Domain
import qualified Feedback as F
import Packet (PresentedItem (..), sha256Hex)
import Registry (PilotConfig (..), PilotSlot (..))
import Server

data PilotExport = PilotExport
  { pePackageId :: Text
  , peAnnotatorId :: Text
  , peStartedAt :: UTCTime
  , peCompletedAt :: Maybe UTCTime
  , peResponses :: [A.Value]
    -- ^ One per presented item, in packet order.
  }

data ExportFault
  = ExportNoSession Text Text
    -- ^ package, annotator: nobody has claimed this slot yet.
  | ExportIncomplete [Text]
    -- ^ Opaque ids of items without a complete annotation.
  deriving stock (Eq, Show)

renderExportFault :: ExportFault -> Text
renderExportFault fault = case fault of
  ExportNoSession pkg annotator -> "no session for " <> pkg <> "/" <> annotator <> " — the slot has not been claimed"
  ExportIncomplete missing -> "session incomplete: " <> T.pack (show (length missing)) <> " item(s) without a complete annotation (" <> T.intercalate ", " (take 5 missing) <> (if length missing > 5 then ", …" else "") <> ")"

exportPilot :: ConnectionPool -> PilotConfig -> Text -> IO (Either ExportFault PilotExport)
exportPilot pool cfg annotatorId = runSqlPool (exportPilotDb cfg annotatorId) pool

exportPilotDb :: PilotConfig -> Text -> SqlPersistT IO (Either ExportFault PilotExport)
exportPilotDb cfg annotatorId = case [s | s <- pcSlots cfg, psAnnotatorId s == annotatorId] of
  [] -> pure (Left (ExportNoSession (pcPackageId cfg) annotatorId))
  (slot : _) -> do
    stored <- getBy (UniquePilotBindingAnnotator annotatorId)
    case stored of
      Nothing -> pure (Left (ExportNoSession (pcPackageId cfg) annotatorId))
      Just (Entity _ pb) -> do
        let sid = pilotBindingSurveySessionId pb
        session <- get sid
        rows <- forM (psItems slot) $ \item -> do
          ann <- getBy (UniqueSessionItem sid (piId item))
          case ann of
            Nothing -> pure (Left (piId item))
            Just (Entity aid annotation) -> do
              labelRows <- selectList [AnnotationLabelAnnotationId ==. aid] [Asc AnnotationLabelId]
              evidenceRows <- selectList [EvidenceAnnotationId ==. aid] [Asc EvidenceId]
              feedbackRow <- getBy (UniqueItemFeedback aid)
              let labels = catMaybes [parseBehaviorLabel (annotationLabelLabelId v) | Entity _ v <- labelRows]
                  evidence = catMaybes [(\l -> (l, evidenceQuote v)) <$> parseBehaviorLabel (evidenceLabelId v) | Entity _ v <- evidenceRows]
                  feedback = entityVal <$> feedbackRow
              if annotationComplete annotation labels evidence
                then pure (Right (responseValue annotatorId item annotation labels evidence feedback))
                else pure (Left (piId item))
        let missing = [i | Left i <- rows]
        case (session, missing) of
          (Nothing, _) -> pure (Left (ExportNoSession (pcPackageId cfg) annotatorId))
          (_, _ : _) -> pure (Left (ExportIncomplete missing))
          (Just s, []) -> pure $ Right PilotExport
            { pePackageId = pcPackageId cfg
            , peAnnotatorId = annotatorId
            , peStartedAt = surveySessionStartedAt s
            , peCompletedAt = surveySessionCompletedAt s
            , peResponses = [v | Right v <- rows]
            }

-- | One @rf.pilot-response.v1@ line. Field presence follows the instruction's
-- appendix: labels and quotes only when assigned, the reason (and note) only
-- when abstained, feedback always.
responseValue :: Text -> PresentedItem -> Annotation -> [BehaviorLabel] -> [(BehaviorLabel, Text)] -> Maybe ItemFeedback -> A.Value
responseValue annotator item annotation labels evidence feedback = object $
  [ "schema_version" .= ("rf.pilot-response.v1" :: Text)
  , "item_id" .= piId item
  , "annotator_id" .= annotator
  , "decision" .= fromMaybe "" (annotationDecision annotation)
  ]
    <> decisionFields
    <> [ "feedback" .= object
           [ "flags" .= map F.feedbackFlagCode (maybe [] feedbackFlagsOf feedback)
           , "note" .= fromMaybe "" (feedback >>= itemFeedbackNote)
           ]
       ]
  where
    decisionFields = case annotationDecision annotation >>= parseDecision of
      Just Assigned ->
        [ "labels" .= map labelCode labels
        , "quotes" .= [object ["label" .= labelCode l, "quote" .= q] | (l, q) <- evidence]
        ]
      Just Abstained ->
        ["abstention_reason" .= fromMaybe "" (annotationAbstentionReason annotation)]
          <> maybe [] (\note -> ["note" .= note]) (annotationAbstentionNote annotation)
      _ -> []

-- | The response layer as bytes: one JSON object per line, packet order.
responsesJsonl :: [A.Value] -> BS.ByteString
responsesJsonl values = BL.toStrict (BL.concat [A.encode v <> "\n" | v <- values])

-- | The export record: what was exported, from which package, and the hash of
-- the response file so the two can be tied together later.
exportRecordValue :: PilotExport -> BS.ByteString -> A.Value
exportRecordValue export responses =
  object
    [ "schema_version" .= ("rf.pilot-export.v1" :: Text)
    , "package_id" .= pePackageId export
    , "annotator_id" .= peAnnotatorId export
    , "started_at" .= peStartedAt export
    , "completed_at" .= peCompletedAt export
    , "n_items" .= length (peResponses export)
    , "responses_sha256" .= sha256Hex responses
    , "instrument_version" .= instrumentVersionCode InstrumentPilot
    ]
