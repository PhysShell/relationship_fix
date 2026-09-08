{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Catalog (items)
import Control.Monad (forM_)
import Control.Monad.IO.Class (liftIO)
import qualified Data.Aeson as A
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KeyMap
import Data.Foldable (toList)
import Data.Maybe (fromMaybe)
import Data.IORef (IORef, atomicModifyIORef', newIORef)
import qualified Data.List as List
import Data.Text (Text)
import qualified Data.Text as T
import Database.Persist.Sql (Entity (..), Filter, SelectOpt (Asc), SqlPersistT, count, deleteWhere, entityVal, runSqlPool, selectList, (==.))
import Domain
import qualified Feedback as F
import qualified MigrationSpec
import qualified PilotSpec
import Network.Wai.Test (simpleBody)
import Schema (migrateDatabase)
import Server
import System.FilePath ((</>))
import System.IO.Temp (withSystemTempDirectory)
import Test.Hspec
import Yesod.Test

main :: IO ()
main = withSystemTempDirectory "annotation-web-test" $ \dir -> do
  counter <- newIORef (0 :: Int)
  fixture <- PilotSpec.makeFixture (dir </> "pilot-fixture")
  real <- PilotSpec.makeRealFixture (dir </> "real-fixture")
  hspec $ do
    domainSpec
    MigrationSpec.spec
    PilotSpec.loaderSpec fixture
    yesodSpecWithSiteGenerator (freshSite dir counter) $ do
      formSpec
      markupSpec
      decisionSpec
      feedbackSpec
      instrumentSpec
    yesodSpecWithSiteGenerator (PilotSpec.pilotSite (PilotSpec.fxConfig fixture) (PilotSpec.fxLastDb fixture) dir counter)
      (PilotSpec.webSpec fixture)
    case real of
      Nothing -> yesodSpecWithSiteGenerator (freshSite dir counter) (PilotSpec.realPackageSpec Nothing)
      Just r -> yesodSpecWithSiteGenerator (PilotSpec.pilotSite (PilotSpec.rfConfig r) (PilotSpec.rfLastDb r) dir counter)
        (PilotSpec.realPackageSpec (Just r))

-- | Each spec item gets its own database, so row counts mean what they say.
freshSite :: FilePath -> IORef Int -> IO App
freshSite dir counter = do
  n <- atomicModifyIORef' counter (\i -> (i + 1, i))
  let db = dir </> ("test-" <> show n <> ".db")
  -- The two halves in the order deployment runs them: schema first, and only
  -- then a server that expects to find it already there.
  _ <- migrateDatabase db
  makeFoundation db (dir </> "session-key.aes") False

-- | Catalog lookup by stable item id. Tests must not depend on list order.
itemById :: Text -> Item
itemById wanted = case filter ((== wanted) . itemId) items of
  (item : _) -> item
  [] -> error $ "catalog is missing item " <> T.unpack wanted

domainSpec :: Spec
domainSpec = do
  describe "dogfood catalog" $ do
    it "has unique item ids" $ do
      let ids = map itemId items
      length ids `shouldBe` length (List.nub ids)

    it "contains both RU and EN presentations for every item" $
      mapM_ (\item -> do
        presentationContext (presentationFor RU item) `shouldNotBe` ""
        presentationTarget (presentationFor RU item) `shouldNotBe` ""
        presentationContext (presentationFor EN item) `shouldNotBe` ""
        presentationTarget (presentationFor EN item) `shouldNotBe` ""
      ) items

  describe "original reveal semantics" $ do
    let russianItem = itemById "dg-10"
    it "does not offer original when presentation language equals source" $
      shouldOfferOriginal RU russianItem `shouldBe` False
    it "offers original when a translation is displayed" $
      shouldOfferOriginal EN russianItem `shouldBe` True

  describe "evidence validation" $ do
    let item = itemById "dg-10"
    it "accepts an exact continuous span" $
      validEvidence RU item "ты его не выключила" `shouldBe` True
    it "rejects a paraphrase" $
      validEvidence RU item "не выключила вентилятор" `shouldBe` False
    it "rejects empty evidence" $
      validEvidence RU item "   " `shouldBe` False
    it "tells a blank answer apart from a wrong one" $ do
      checkEvidence RU item "   " `shouldBe` Left EvidenceBlank
      checkEvidence RU item "не выключила вентилятор" `shouldBe` Left EvidenceNotASpan
      checkEvidence RU item "ты его не выключила" `shouldBe` Right "ты его не выключила"
    it "takes the quote exactly as typed: no trimming, no fixing" $ do
      -- a trailing space is not in the target ("выключила." follows), so the
      -- quote is wrong, not almost right
      checkEvidence RU item " ты его не выключила " `shouldBe` Left EvidenceNotASpan
      checkEvidence RU item " ты его не выключила" `shouldBe` Right " ты его не выключила"

  describe "wire codes" $ do
    it "round-trips all labels" $
      map (parseBehaviorLabel . labelCode) allBehaviorLabels `shouldBe` map Just allBehaviorLabels
    it "round-trips all abstention reasons" $
      map (parseAbstentionReason . abstentionCode) allAbstentionReasons `shouldBe` map Just allAbstentionReasons

  describe "abstention notes" $
    it "requires a note exactly for the reasons that are unusable without one" $
      filter abstentionRequiresNote allAbstentionReasons `shouldBe` [AmbiguousBetweenLabels, OtherReason]

-- | Row counts across every table an annotation submission can touch.
type RowCounts = (Int, Int, Int, Int, Int)

rowCounts :: YesodExample App RowCounts
rowCounts = do
  site <- getTestYesod
  liftIO $ flip runSqlPool (appPool site) $
    (,,,,)
      <$> count ([] :: [Filter Annotation])
      <*> count ([] :: [Filter AnnotationLabel])
      <*> count ([] :: [Filter Evidence])
      <*> count ([] :: [Filter ItemFeedback])
      <*> count ([] :: [Filter AuditEvent])

runDb :: SqlPersistT IO a -> YesodExample App a
runDb action = do
  site <- getTestYesod
  liftIO $ runSqlPool action (appPool site)

annotationsFor :: Text -> YesodExample App [Annotation]
annotationsFor iid = map entityVal <$> runDb (selectList [AnnotationItemId ==. iid] [])

-- | Everything that hangs off one item's annotation, for the invariants about
-- what a decision change is and is not allowed to discard.
labelsFor :: Text -> YesodExample App [Text]
labelsFor iid = runDb $ do
  anns <- selectList [AnnotationItemId ==. iid] []
  case anns of
    [] -> pure []
    (Entity aid _ : _) ->
      map (annotationLabelLabelId . entityVal)
        <$> selectList [AnnotationLabelAnnotationId ==. aid] [Asc AnnotationLabelId]

evidenceFor :: Text -> YesodExample App [Text]
evidenceFor iid = runDb $ do
  anns <- selectList [AnnotationItemId ==. iid] []
  case anns of
    [] -> pure []
    (Entity aid _ : _) ->
      map (evidenceQuote . entityVal) <$> selectList [EvidenceAnnotationId ==. aid] [Asc EvidenceId]

feedbackFor :: Text -> YesodExample App [ItemFeedback]
feedbackFor iid = runDb $ do
  anns <- selectList [AnnotationItemId ==. iid] []
  case anns of
    [] -> pure []
    (Entity aid _ : _) ->
      map entityVal <$> selectList [ItemFeedbackAnnotationId ==. aid] []

jsonField :: Text -> A.Value -> Maybe A.Value
jsonField name (A.Object o) = KeyMap.lookup (Key.fromText name) o
jsonField _ _ = Nothing

-- | The submission object for one item, so that feedback can be checked to be
-- a field of its own rather than something smuggled into labels.
submissionObject :: YesodExample App A.Value
submissionObject = do
  get SubmissionR
  statusIs 200
  body <- withResponse (pure . simpleBody)
  pure (fromMaybe A.Null (A.decode body))

annotationOf :: Text -> A.Value -> Maybe A.Value
annotationOf iid submission = case jsonField "annotations" submission of
  Just (A.Array xs) -> case filter ((== Just (A.String iid)) . jsonField "item_id") (toList xs) of
    (a : _) -> Just a
    [] -> Nothing
  _ -> Nothing

submissionAnnotation :: Text -> YesodExample App A.Value
submissionAnnotation iid = fromMaybe A.Null . annotationOf iid <$> submissionObject

-- | Turns the session this test is holding into one that predates the
-- item-feedback step, exactly as the live database holds it: the column simply
-- has no value, because it did not exist when the row was written.
grandfatherSession :: YesodExample App ()
grandfatherSession = runDb $ deleteWhere ([] :: [Filter SessionInstrument])

auditKindsFor :: Text -> YesodExample App [Text]
auditKindsFor iid = do
  site <- getTestYesod
  rows <- liftIO $ runSqlPool (selectList [AuditEventItemId ==. Just iid] []) (appPool site)
  pure (map (auditEventKind . entityVal) rows)

startSession :: Text -> YesodExample App ()
startSession language = do
  get HomeR
  statusIs 200
  request $ do
    setMethod "POST"
    setUrl LanguageR
    addToken
    addPostParam "language" language
  followTo "/intro"

submitStep :: Route App -> [(Text, Text)] -> YesodExample App ()
submitStep route params = request $ do
  setMethod "POST"
  setUrl route
  addToken_ "#step-form"
  mapM_ (uncurry addPostParam) params

-- | Item feedback is its own form on the item page, separate from whichever
-- step's form is showing -- a different CSRF token source, and a submission
-- that never advances the item on its own.
submitFeedback :: Int -> [(Text, Text)] -> YesodExample App ()
submitFeedback index params = request $ do
  setMethod "POST"
  setUrl (FeedbackR index)
  addToken_ "#feedback-form"
  mapM_ (uncurry addPostParam) params

followTo :: Text -> YesodExample App ()
followTo expected = do
  statusIs 303
  redirected <- followRedirect
  case redirected of
    Left err -> liftIO $ expectationFailure (T.unpack err)
    Right url -> assertEq "redirect target" expected url

-- | Walks item 0 as far as the evidence step with the given labels selected.
reachEvidenceStep :: [Text] -> YesodExample App ()
reachEvidenceStep labels = do
  get (ItemR 0)
  statusIs 200
  submitStep (DecisionR 0) [("decision", "assigned")]
  followTo "/item/0"
  submitStep (LabelsR 0) [("labels", label) | label <- labels]
  followTo "/item/0"

formSpec :: YesodSpec App
formSpec = ydescribe "rejected submissions" $ do
  yit "re-renders the evidence step with the quote and the reason it was rejected" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    rowsBefore <- rowCounts
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "не выключила вентилятор")]
    statusIs 200
    bodyContains "не выключила вентилятор"
    bodyContains "точным непрерывным фрагментом"
    htmlCount ".field-error" 1
    rowsAfter <- rowCounts
    assertEq "an invalid submission writes nothing" rowsBefore rowsAfter

  yit "keeps every other quote when one of them is rejected" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM", "B.PRESSURE_FOR_CHANGE"]
    rowsBefore <- rowCounts
    submitStep (EvidenceR 0)
      [ ("evidence_B.BLAME_CRITICISM", "ты его не выключила")
      , ("evidence_B.PRESSURE_FOR_CHANGE", "этого нет в сообщении")
      ]
    statusIs 200
    bodyContains "ты его не выключила"
    bodyContains "этого нет в сообщении"
    htmlCount ".field-error" 1
    rowsAfter <- rowCounts
    assertEq "no partial evidence is written" rowsBefore rowsAfter

  yit "keeps the item on the labels step when no category is selected" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    rowsBefore <- rowCounts
    submitStep (LabelsR 0) []
    statusIs 200
    bodyContains "Выберите хотя бы одну категорию."
    htmlCount ".field-error" 1
    stored <- annotationsFor "dg-10"
    assertEq "the decision survives" [Just "assigned"] (map annotationDecision stored)
    rowsAfter <- rowCounts
    assertEq "an invalid submission writes nothing" rowsBefore rowsAfter

  yit "keeps both evidence fields on screen when the step is rejected" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM", "B.PRESSURE_FOR_CHANGE"]
    submitStep (EvidenceR 0)
      [ ("evidence_B.BLAME_CRITICISM", "нет такого текста")
      , ("evidence_B.PRESSURE_FOR_CHANGE", "и такого тоже нет")
      ]
    statusIs 200
    htmlCount "input[name=evidence_B.BLAME_CRITICISM]" 1
    htmlCount "input[name=evidence_B.PRESSURE_FOR_CHANGE]" 1
    htmlCount ".field-error" 2

  yit "keeps the abstention step and the recorded decision when no reason is chosen" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "abstained")]
    followTo "/item/0"
    rowsBefore <- rowCounts
    submitStep (AbstainR 0) []
    statusIs 200
    htmlCount ".field-error" 1
    stored <- annotationsFor "dg-10"
    assertEq "the decision stays abstained" [Just "abstained"] (map annotationDecision stored)
    assertEq "no reason is stored" [Nothing] (map annotationAbstentionReason stored)
    rowsAfter <- rowCounts
    assertEq "an invalid submission writes nothing" rowsBefore rowsAfter

  yit "reports the missing note next to it and keeps the chosen reason" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "abstained")]
    followTo "/item/0"
    rowsBefore <- rowCounts
    submitStep (AbstainR 0) [("reason", "ambiguous_between_labels"), ("note", "   ")]
    statusIs 200
    bodyContains "нужен короткий комментарий"
    htmlCount ".field-error" 1
    htmlAnyContain "option[selected]" "Неоднозначно между категориями"
    rowsAfter <- rowCounts
    assertEq "an invalid submission writes nothing" rowsBefore rowsAfter

  yit "keeps a revealed original visible when the submission is rejected" $ do
    startSession "en"
    get (ItemR 0)
    statusIs 200
    bodyContains "the fan was running all night"
    bodyContains "Show original"
    request $ do
      setMethod "POST"
      setUrl (OriginalR 0)
      addToken_ "#reveal-form"
    followTo "/item/0"
    bodyContains "вентилятор всю ночь работал"
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    submitStep (LabelsR 0) [("labels", "B.BLAME_CRITICISM")]
    followTo "/item/0"
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "not in the target message")]
    statusIs 200
    bodyContains "not in the target message"
    bodyContains "вентилятор всю ночь работал"
    bodyContains "the fan was running all night"

  yit "persists a valid decision exactly once and moves to the next item" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "none_observed")]
    followTo "/item/0"
    stored <- annotationsFor "dg-10"
    assertEq "exactly one annotation row" 1 (length stored)
    assertEq "the decision is stored" [Just "none_observed"] (map annotationDecision stored)
    kinds <- auditKindsFor "dg-10"
    assertEq "exactly one audit event" ["decision_submitted"] kinds
    -- The item is already complete; visiting it again advances on its own,
    -- with no feedback step in between.
    followTo "/item/1"

-- | What the respondent's thumb actually meets. The generic yesod-form
-- renderer emitted inputs and labels as flat siblings, which on a narrow
-- screen reflowed into each other; these assert the structure that replaced it.
markupSpec :: YesodSpec App
markupSpec = ydescribe "option rows" $ do
  yit "gives every category its own row, with its label bound to its input" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    -- Scoped to the step's own form: the page also carries the feedback
    -- disclosure's checkbox row, which uses the same row markup and would
    -- otherwise be counted here too.
    htmlCount "#step-form label.choice" 5
    htmlCount "input[name=labels]" 5
    forM_ (map labelCode allBehaviorLabels) $ \code ->
      bodyContains . T.unpack $
        "<label class=\"choice\" for=\"labels-" <> code
          <> "\"><input id=\"labels-" <> code
          <> "\" type=\"checkbox\" name=\"labels\" value=\"" <> code <> "\""
    htmlAnyContain "span.choice-text" "обвинение / критика"

  yit "gives the decision radios the same structure" $ do
    startSession "ru"
    get (ItemR 0)
    htmlCount "#step-form label.choice" 3
    htmlCount "input[name=decision]" 3
    bodyContains "<label class=\"choice\" for=\"decision-assigned\"><input id=\"decision-assigned\""

  yit "no longer ships stylesheet rules that match no markup" $ do
    get HomeR
    statusIs 200
    bodyNotContains "form ul {"
    bodyNotContains "form li label {"

decisionSpec :: YesodSpec App
decisionSpec = ydescribe "reconsidering a decision" $ do
  yit "offers a way back to the decision from the later steps" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    htmlCount "p.step-back a" 1
    bodyContains "/item/0/decision/edit"
    bodyContains "Изменить решение"

  yit "reopens the step with the decision already on record selected" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    get (EditDecisionR 0)
    statusIs 200
    htmlCount "input[name=decision][checked]" 1
    bodyContains "value=\"assigned\" required checked"

  yit "A. assigned to none_observed drops what it made stale" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    get (EditDecisionR 0)
    submitStep (DecisionR 0) [("decision", "none_observed")]
    followTo "/item/0"
    labels <- labelsFor "dg-10"
    assertEq "categories cleared" [] labels
    quotes <- evidenceFor "dg-10"
    assertEq "quotes cleared" [] quotes
    stored <- annotationsFor "dg-10"
    assertEq "decision changed" [Just "none_observed"] (map annotationDecision stored)
    -- The item is complete now and would auto-advance on a plain GET, but
    -- explicitly reopening it for editing still shows feedback as available.
    get (EditDecisionR 0)
    bodyContains "Проблемы с вопросом?"

  yit "B. assigned to abstained drops categories and quotes" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "ты его не выключила")]
    followTo "/item/0"
    get (EditDecisionR 0)
    submitStep (DecisionR 0) [("decision", "abstained")]
    followTo "/item/0"
    labels <- labelsFor "dg-10"
    assertEq "categories cleared" [] labels
    quotes <- evidenceFor "dg-10"
    assertEq "quotes cleared" [] quotes
    bodyContains "Причина abstained"

  yit "C. abstained to assigned clears the abstention" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "abstained")]
    followTo "/item/0"
    submitStep (AbstainR 0) [("reason", "ambiguous_between_labels"), ("note", "на границе repair и avoidance")]
    followTo "/item/0"
    get (EditDecisionR 0)
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    stored <- annotationsFor "dg-10"
    assertEq "reason cleared" [Nothing] (map annotationAbstentionReason stored)
    assertEq "note cleared" [Nothing] (map annotationAbstentionNote stored)
    bodyContains "Категории"

  yit "D. confirming the same decision keeps the work already done" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "ты его не выключила")]
    followTo "/item/0"
    get (EditDecisionR 0)
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    labels <- labelsFor "dg-10"
    assertEq "categories survive" ["B.BLAME_CRITICISM"] labels
    quotes <- evidenceFor "dg-10"
    assertEq "quotes survive" ["ты его не выключила"] quotes

  yit "E. an invalid edit submission re-renders and writes nothing" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    get (EditDecisionR 0)
    rowsBefore <- rowCounts
    submitStep (DecisionR 0) []
    statusIs 200
    htmlCount ".field-error" 1
    labels <- labelsFor "dg-10"
    assertEq "categories untouched" ["B.BLAME_CRITICISM"] labels
    rowsAfter <- rowCounts
    assertEq "an invalid submission writes nothing" rowsBefore rowsAfter

feedbackSpec :: YesodSpec App
feedbackSpec = ydescribe "optional item feedback" $ do
  yit "is present but collapsed on the decision page, before any decision is made" $ do
    startSession "ru"
    get (ItemR 0)
    statusIs 200
    bodyContains "Проблемы с вопросом?"
    -- No `open` attribute: collapsed by default, native <details> semantics,
    -- no JavaScript involved in showing or hiding it.
    bodyContains "<details class=\"feedback-disclosure\">"
    bodyContains "<summary>"

  yit "uses a real button and a real form, not a clickable div" $ do
    startSession "ru"
    get (ItemR 0)
    htmlCount "#feedback-form" 1
    bodyContains "action=\"/item/0/feedback\""
    htmlCount "#feedback-form button[type=submit]" 1

  yit "none_observed advances straight to the next item, with no separate feedback screen" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "none_observed")]
    -- The decision handler's own redirect target is unchanged (this same
    -- item); the item advances on the *next* GET, once it is complete.
    followTo "/item/0"
    followTo "/item/1"

  yit "assigned advances straight to the next item after the quotes" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "ты его не выключила")]
    followTo "/item/0"
    followTo "/item/1"

  yit "abstained advances straight to the next item after the reason" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "abstained")]
    followTo "/item/0"
    submitStep (AbstainR 0) [("reason", "insufficient_context")]
    followTo "/item/0"
    followTo "/item/1"

  yit "never opening the disclosure stores no feedback at all" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "none_observed")]
    followTo "/item/0"
    followTo "/item/1"
    rows <- feedbackFor "dg-10"
    assertEq "no feedback row exists" 0 (length rows)

  yit "opening the disclosure and submitting nothing is a valid, empty answer" $ do
    startSession "ru"
    get (ItemR 0)
    submitFeedback 0 []
    followTo "/item/0"
    rows <- feedbackFor "dg-10"
    assertEq "one feedback row" 1 (length rows)
    assertEq "no flags" [] (concatMap flagCodes rows)
    assertEq "no note" [Nothing] (map itemFeedbackNote rows)

  yit "submitting feedback does not by itself advance the item" $ do
    startSession "ru"
    get (ItemR 0)
    submitFeedback 0 [("feedback_flags", "unnatural_example")]
    -- Feedback is optional and separate: giving it is not the act that
    -- completes the item, so the respondent lands back on the same item and
    -- can still make (or has yet to make) the actual decision.
    followTo "/item/0"
    statusIs 200
    stored <- annotationsFor "dg-10"
    assertEq "no decision was recorded by submitting feedback" [Nothing] (map annotationDecision stored)

  yit "one flag persists" $ do
    startSession "ru"
    completeItemWithFeedback 0 [("feedback_flags", "unnatural_example")]
    rows <- feedbackFor "dg-10"
    assertEq "the flag is stored" ["unnatural_example"] (concatMap flagCodes rows)

  yit "several flags persist" $ do
    startSession "ru"
    completeItemWithFeedback 0
      [ ("feedback_flags", "unnatural_example")
      , ("feedback_flags", "insufficient_context")
      ]
    rows <- feedbackFor "dg-10"
    assertEq "both flags are stored"
      ["unnatural_example", "insufficient_context"] (concatMap flagCodes rows)

  yit "a free note persists without any flag" $ do
    startSession "ru"
    completeItemWithFeedback 0 [("feedback_note", "  так люди как будто не разговаривают  ")]
    rows <- feedbackFor "dg-10"
    assertEq "no flags" [] (concatMap flagCodes rows)
    assertEq "the note is stored, trimmed"
      [Just "так люди как будто не разговаривают"] (map itemFeedbackNote rows)

  yit "feedback given after finishing leaves the decision and the categories alone" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM"]
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "ты его не выключила")]
    -- The item is complete now, and a plain GET would auto-advance, but
    -- reopening it for editing still renders the feedback form (with a fresh
    -- CSRF token) -- feedback is addressed by item index, not by "the page
    -- currently open in the browser".
    get (EditDecisionR 0)
    submitFeedback 0 [("feedback_flags", "unnatural_example")]
    stored <- annotationsFor "dg-10"
    assertEq "decision unchanged" [Just "assigned"] (map annotationDecision stored)
    labels <- labelsFor "dg-10"
    assertEq "categories unchanged" ["B.BLAME_CRITICISM"] labels
    quotes <- evidenceFor "dg-10"
    assertEq "quotes unchanged" ["ты его не выключила"] quotes
    rows <- feedbackFor "dg-10"
    assertEq "and the feedback was recorded" ["unnatural_example"] (concatMap flagCodes rows)

  yit "reports feedback as its own field of the submission, never as a label" $ do
    startSession "ru"
    completeItemWithFeedback 0
      [ ("feedback_flags", "unnatural_example")
      , ("feedback_note", "звучит неестественно")
      ]
    forM_ [1 .. 5] $ \index -> completeItemWithFeedback index []
    annotation <- submissionAnnotation "dg-10"
    assertEq "labels stay empty" (Just (A.Array mempty)) (jsonField "labels" annotation)
    assertEq "flags are their own list"
      (Just (A.Array (pure (A.String "unnatural_example"))))
      (jsonField "feedback" annotation >>= jsonField "flags")
    assertEq "the note is its own field"
      (Just (A.String "звучит неестественно"))
      (jsonField "feedback" annotation >>= jsonField "note")

  yit "reports no feedback content as an empty structure, not as an answer" $ do
    startSession "ru"
    forM_ [0 .. 5] $ \index -> completeItemWithFeedback index []
    annotation <- submissionAnnotation "dg-05"
    assertEq "flags empty" (Just (A.Array mempty)) (jsonField "feedback" annotation >>= jsonField "flags")
    assertEq "note absent" (Just A.Null) (jsonField "feedback" annotation >>= jsonField "note")

flagCodes :: ItemFeedback -> [Text]
flagCodes row = map F.feedbackFlagCode $ concat
  [ [F.UnnaturalExample | itemFeedbackUnnaturalExample row]
  , [F.InsufficientContext | itemFeedbackInsufficientContext row]
  , [F.WordingOrTranslation | itemFeedbackWordingOrTranslation row]
  , [F.OtherFeedback | itemFeedbackOther row]
  ]

-- | Feedback (given inline, before finishing), then none_observed, which now
-- advances straight to the next item on its own -- feedback is never a
-- condition on that.
completeItemWithFeedback :: Int -> [(Text, Text)] -> YesodExample App ()
completeItemWithFeedback index feedback = do
  get (ItemR index)
  submitFeedback index feedback
  followTo (T.pack ("/item/" <> show index))
  submitStep (DecisionR index) [("decision", "none_observed")]
  -- The decision handler's own redirect still targets this same item; the
  -- item only actually advances on the *next* GET, once it notices the
  -- annotation is complete.
  followTo (T.pack ("/item/" <> show index))
  followTo (if index + 1 < length items then T.pack ("/item/" <> show (index + 1)) else "/done")

-- | The instrument a session is taken under is a property of that session.
--
-- A live hs-v1 session exists. Redeploying must not walk it into a step that
-- did not exist when it started, and must not export it under a version its
-- respondent never saw.
instrumentSpec :: YesodSpec App
instrumentSpec = ydescribe "instrument version is bound to the session" $ do
  yit "records the version on the session rather than reading it off the binary" $ do
    startSession "ru"
    versions <- runDb (map (sessionInstrumentVersion . entityVal) <$> selectList ([] :: [Filter SessionInstrument]) [])
    assertEq "a new session is hs-v2" ["annotation-web-dogfood-hs-v2"] versions

  yit "never shows the feedback disclosure to a session that predates it" $ do
    startSession "ru"
    grandfatherSession
    get (ItemR 0)
    bodyNotContains "Проблемы с вопросом?"
    submitStep (DecisionR 0) [("decision", "none_observed")]
    followTo "/item/0"
    followTo "/item/1"
    rows <- feedbackFor "dg-10"
    assertEq "and stores no feedback for it" 0 (length rows)

  yit "refuses feedback submission outright under the older instrument" $ do
    startSession "ru"
    get (ItemR 0)
    bodyContains "Проблемы с вопросом?"
    grandfatherSession
    rowsBefore <- rowCounts
    submitFeedback 0 [("feedback_flags", "unnatural_example")]
    statusIs 404
    rowsAfter <- rowCounts
    assertEq "a refused submission writes nothing" rowsBefore rowsAfter

  yit "exports a grandfathered session under hs-v1, without the newer field" $ do
    startSession "ru"
    grandfatherSession
    forM_ [0 .. 5] $ \index -> do
      get (ItemR index)
      submitStep (DecisionR index) [("decision", "none_observed")]
      followTo (T.pack ("/item/" <> show index))
      followTo (if index + 1 < length items then T.pack ("/item/" <> show (index + 1)) else "/done")
    submission <- submissionObject
    assertEq "reported as the version actually taken"
      (Just (A.String "annotation-web-dogfood-hs-v1")) (jsonField "instrument_version" submission)
    assertEq "ontology version is not touched by any of this"
      (Just (A.String "behavior-v0.2-candidate")) (jsonField "ontology_version" submission)
    let annotation = fromMaybe A.Null (annotationOf "dg-10" submission)
    assertEq "the hs-v2 field is absent, not merely empty" Nothing (jsonField "feedback" annotation)
    assertEq "the annotation itself is unchanged"
      (Just (A.String "none_observed")) (jsonField "decision" annotation)

  yit "exports a session started now under hs-v2, with the field" $ do
    startSession "ru"
    forM_ [0 .. 5] $ \index -> completeItemWithFeedback index []
    submission <- submissionObject
    assertEq "reported as hs-v2"
      (Just (A.String "annotation-web-dogfood-hs-v2")) (jsonField "instrument_version" submission)
    let annotation = fromMaybe A.Null (annotationOf "dg-10" submission)
    assertEq "and carries the feedback field"
      (Just (A.Array mempty)) (jsonField "feedback" annotation >>= jsonField "flags")
