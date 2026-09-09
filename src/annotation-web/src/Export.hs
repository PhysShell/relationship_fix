{-# LANGUAGE OverloadedStrings #-}

-- | Canonical export of one pilot session: the facilitator's collection path.
--
-- Nothing here is shown to the annotator. The export reads the bound session
-- from the database, walks the packet in the packet's own order, refuses a
-- session that is not complete, and writes one @rf.pilot-response.v1@ line per
-- presented item -- the format @metrics.agreement@ consumes -- plus an export
-- record that repeats the binding (package, hashes, pseudonym) so the file can
-- be tied back to exactly what the person was shown.
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
import Registry (Binding (..), IssuanceRecord (..))
import Server

data PilotExport = PilotExport
  { peRecord :: IssuanceRecord
  , peTokenSha :: Text
  , peStartedAt :: UTCTime
  , peCompletedAt :: Maybe UTCTime
  , peResponses :: [A.Value]
    -- ^ One per presented item, in packet order.
  }

data ExportFault
  = ExportNoSession Text Text
    -- ^ package, annotator: nobody has opened this token yet.
  | ExportBindingChanged Text
  | ExportIncomplete [Text]
    -- ^ Opaque ids of items without a complete annotation.
  deriving stock (Eq, Show)

renderExportFault :: ExportFault -> Text
renderExportFault fault = case fault of
  ExportNoSession pkg annotator -> "no session for " <> pkg <> "/" <> annotator <> " — the token has not been opened"
  ExportBindingChanged annotator -> "session for " <> annotator <> " was bound to different hashes than the loaded record — refusing to export"
  ExportIncomplete missing -> "session incomplete: " <> T.pack (show (length missing)) <> " item(s) without a complete annotation (" <> T.intercalate ", " (take 5 missing) <> (if length missing > 5 then ", …" else "") <> ")"

exportPilot :: ConnectionPool -> Binding -> IO (Either ExportFault PilotExport)
exportPilot pool binding = runSqlPool (exportPilotDb binding) pool

exportPilotDb :: Binding -> SqlPersistT IO (Either ExportFault PilotExport)
exportPilotDb binding = do
  let rec = bindRecord binding
      key = irTokenSha rec
  stored <- getBy (UniquePilotBindingToken key)
  case stored of
    Nothing -> pure (Left (ExportNoSession (irPackageId rec) (irAnnotatorId rec)))
    Just (Entity _ pb)
      | not (bindingUnchanged pb rec) -> pure (Left (ExportBindingChanged (irAnnotatorId rec)))
      | otherwise -> do
          let sid = pilotBindingSurveySessionId pb
          session <- get sid
          rows <- forM (bindItems binding) $ \item -> do
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
                  then pure (Right (responseValue (irAnnotatorId rec) item annotation labels evidence feedback))
                  else pure (Left (piId item))
          let missing = [i | Left i <- rows]
          case (session, missing) of
            (Nothing, _) -> pure (Left (ExportNoSession (irPackageId rec) (irAnnotatorId rec)))
            (_, _ : _) -> pure (Left (ExportIncomplete missing))
            (Just s, []) -> pure $ Right PilotExport
              { peRecord = rec
              , peTokenSha = key
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

-- | The export record: what was exported, from which binding, and the hash of
-- the response file so the two can be tied together in the issuance ledger.
exportRecordValue :: PilotExport -> BS.ByteString -> A.Value
exportRecordValue export responses =
  let rec = peRecord export
   in object
        [ "schema_version" .= ("rf.pilot-export.v1" :: Text)
        , "package_id" .= irPackageId rec
        , "annotator_id" .= irAnnotatorId rec
        , "token_sha256" .= peTokenSha export
        , "record_file" .= irRecordFile rec
        , "items_sha256" .= irItemsSha rec
        , "checksums_sha256" .= irChecksumsSha rec
        , "presentation_sha256" .= irPresentationSha rec
        , "instructions_sha256" .= irInstructionsSha rec
        , "ontology_sha256" .= irOntologySha rec
        , "ontology_version" .= irOntologyVersion rec
        , "started_at" .= peStartedAt export
        , "completed_at" .= peCompletedAt export
        , "n_items" .= length (peResponses export)
        , "responses_sha256" .= sha256Hex responses
        , "instrument_version" .= instrumentVersionCode InstrumentPilot
        ]
