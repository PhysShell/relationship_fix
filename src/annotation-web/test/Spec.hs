{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Catalog (items)
import Control.Monad.IO.Class (liftIO)
import Data.IORef (IORef, atomicModifyIORef', newIORef)
import qualified Data.List as List
import Data.Text (Text)
import qualified Data.Text as T
import Database.Persist.Sql (Filter, count, entityVal, runSqlPool, selectList, (==.))
import Domain
import Server
import System.FilePath ((</>))
import System.IO.Temp (withSystemTempDirectory)
import Test.Hspec
import Yesod.Test

main :: IO ()
main = withSystemTempDirectory "annotation-web-test" $ \dir -> do
  counter <- newIORef (0 :: Int)
  hspec $ do
    domainSpec
    yesodSpecWithSiteGenerator (freshSite dir counter) formSpec

-- | Each spec item gets its own database, so row counts mean what they say.
freshSite :: FilePath -> IORef Int -> IO App
freshSite dir counter = do
  n <- atomicModifyIORef' counter (\i -> (i + 1, i))
  makeFoundation (dir </> ("test-" <> show n <> ".db")) (dir </> "session-key.aes") False

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
    let russianItem = itemById "dg-04"
    it "does not offer original when presentation language equals source" $
      shouldOfferOriginal RU russianItem `shouldBe` False
    it "offers original when a translation is displayed" $
      shouldOfferOriginal EN russianItem `shouldBe` True

  describe "evidence validation" $ do
    let item = itemById "dg-04"
    it "accepts an exact continuous span" $
      validEvidence RU item "оставил окно открытым" `shouldBe` True
    it "rejects a paraphrase" $
      validEvidence RU item "забыл закрыть окно" `shouldBe` False
    it "rejects empty evidence" $
      validEvidence RU item "   " `shouldBe` False

  describe "wire codes" $ do
    it "round-trips all labels" $
      map (parseBehaviorLabel . labelCode) allBehaviorLabels `shouldBe` map Just allBehaviorLabels
    it "round-trips all abstention reasons" $
      map (parseAbstentionReason . abstentionCode) allAbstentionReasons `shouldBe` map Just allAbstentionReasons

  describe "abstention notes" $
    it "requires a note exactly for the reasons that are unusable without one" $
      filter abstentionRequiresNote allAbstentionReasons `shouldBe` [AmbiguousBetweenLabels, OtherReason]

-- | Row counts across every table an annotation submission can touch.
type RowCounts = (Int, Int, Int, Int)

rowCounts :: YesodExample App RowCounts
rowCounts = do
  site <- getTestYesod
  liftIO $ flip runSqlPool (appPool site) $
    (,,,)
      <$> count ([] :: [Filter Annotation])
      <*> count ([] :: [Filter AnnotationLabel])
      <*> count ([] :: [Filter Evidence])
      <*> count ([] :: [Filter AuditEvent])

annotationsFor :: Text -> YesodExample App [Annotation]
annotationsFor iid = do
  site <- getTestYesod
  rows <- liftIO $ runSqlPool (selectList [AnnotationItemId ==. iid] []) (appPool site)
  pure (map entityVal rows)

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
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "забыл закрыть окно")]
    statusIs 200
    bodyContains "забыл закрыть окно"
    bodyContains "точным непрерывным фрагментом"
    htmlCount ".field-error" 1
    rowsAfter <- rowCounts
    assertEq "an invalid submission writes nothing" rowsBefore rowsAfter

  yit "keeps every other quote when one of them is rejected" $ do
    startSession "ru"
    reachEvidenceStep ["B.BLAME_CRITICISM", "B.PRESSURE_FOR_CHANGE"]
    rowsBefore <- rowCounts
    submitStep (EvidenceR 0)
      [ ("evidence_B.BLAME_CRITICISM", "оставил окно открытым")
      , ("evidence_B.PRESSURE_FOR_CHANGE", "этого нет в сообщении")
      ]
    statusIs 200
    bodyContains "оставил окно открытым"
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
    stored <- annotationsFor "dg-04"
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
    stored <- annotationsFor "dg-04"
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
    bodyContains "You left the window open yesterday"
    bodyContains "Show original"
    request $ do
      setMethod "POST"
      setUrl (OriginalR 0)
      addToken_ "#reveal-form"
    followTo "/item/0"
    bodyContains "Ты вчера оставил окно открытым"
    submitStep (DecisionR 0) [("decision", "assigned")]
    followTo "/item/0"
    submitStep (LabelsR 0) [("labels", "B.BLAME_CRITICISM")]
    followTo "/item/0"
    submitStep (EvidenceR 0) [("evidence_B.BLAME_CRITICISM", "not in the target message")]
    statusIs 200
    bodyContains "not in the target message"
    bodyContains "Ты вчера оставил окно открытым"
    bodyContains "You left the window open yesterday"

  yit "persists a valid decision exactly once and moves to the next item" $ do
    startSession "ru"
    get (ItemR 0)
    submitStep (DecisionR 0) [("decision", "none_observed")]
    followTo "/item/1"
    stored <- annotationsFor "dg-04"
    assertEq "exactly one annotation row" 1 (length stored)
    assertEq "the decision is stored" [Just "none_observed"] (map annotationDecision stored)
    kinds <- auditKindsFor "dg-04"
    assertEq "exactly one audit event" ["decision_submitted"] kinds
