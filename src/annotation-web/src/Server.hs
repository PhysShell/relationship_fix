{-# LANGUAGE DataKinds #-}
{-# LANGUAGE DerivingStrategies #-}
{-# LANGUAGE FlexibleContexts #-}
{-# LANGUAGE FlexibleInstances #-}
{-# LANGUAGE GADTs #-}
{-# LANGUAGE GeneralizedNewtypeDeriving #-}
{-# LANGUAGE MultiParamTypeClasses #-}
{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE QuasiQuotes #-}
{-# LANGUAGE StandaloneDeriving #-}
{-# LANGUAGE TemplateHaskell #-}
{-# LANGUAGE TupleSections #-}
{-# LANGUAGE TypeFamilies #-}
{-# LANGUAGE UndecidableInstances #-}
{-# LANGUAGE ViewPatterns #-}

module Server where

import Catalog (items)
import Control.Exception (throwIO)
import Control.Monad (forM, forM_, unless, when)
import Control.Monad.Logger (runNoLoggingT)
import Data.Int (Int64)
import qualified Data.Map.Strict as Map
import Data.Maybe (catMaybes, fromMaybe, isJust, isNothing)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Read as TR
import Data.Time (UTCTime, getCurrentTime)
import Database.Persist.Sql (ConnectionPool, SqlBackend, fromSqlKey, runSqlPool, showMigration, toSqlKey)
import Database.Persist.Sqlite (createSqlitePool, withSqlitePool)
import Domain
import qualified Feedback as F
import qualified Ontology as O
import Packet (PresentedItem (..), PresentedMessage (..), presentedTarget)
import Registry (Binding (..), IssuanceRecord (..), tokenSha)
import qualified Schema
import Yesod

share [mkPersist sqlSettings, mkMigrate "migrateAll"] [persistLowerCase|
SurveySession
    presentationLanguage Text
    startedAt UTCTime
    completedAt UTCTime Maybe
    deriving Show
-- | The instrument a session is being taken under.
--
-- A separate table rather than a column on SurveySession, and not for taste:
-- persistent-sqlite migrates an added column by rebuilding the table --
-- CREATE backup, INSERT, DROP survey_session, CREATE, INSERT back -- and
-- dropping a table that annotation rows reference fails the foreign key check
-- outright. On the live database that is a server that will not start.
-- Creating a new table has no such problem, and a session with no row here is
-- one that began before this table existed: historical hs-v1.
SessionInstrument
    surveySessionId SurveySessionId
    version Text
    UniqueSessionInstrument surveySessionId
    deriving Show
Annotation
    surveySessionId SurveySessionId
    itemId Text
    decision Text Maybe
    abstentionReason Text Maybe
    abstentionNote Text Maybe
    originalRevealed Bool
    UniqueSessionItem surveySessionId itemId
    deriving Show
AnnotationLabel
    annotationId AnnotationId
    labelId Text
    UniqueAnnotationLabel annotationId labelId
    deriving Show
Evidence
    annotationId AnnotationId
    labelId Text
    quote Text
    UniqueEvidence annotationId labelId
    deriving Show
ItemFeedback
    annotationId AnnotationId
    unnaturalExample Bool
    insufficientContext Bool
    wordingOrTranslation Bool
    other Bool
    note Text Maybe
    UniqueItemFeedback annotationId
    deriving Show
AuditEvent
    surveySessionId SurveySessionId
    itemId Text Maybe
    kind Text
    value Text Maybe
    occurredAt UTCTime
    deriving Show
-- | A pilot session is a survey session bound to one issuance record. What is
-- stored is what the person was issued -- package, annotator pseudonym and the
-- hashes of the presentation file, the instruction document and the ontology
-- -- so that the record on disk changing later is detectable and refused,
-- rather than silently re-binding a running session to different bytes. The
-- token is never stored; its sha256 is.
PilotBinding
    surveySessionId SurveySessionId
    tokenSha256 Text
    packageId Text
    annotatorId Text
    itemsSha256 Text
    checksumsSha256 Text
    presentationSha256 Text
    instructionsSha256 Text
    ontologySha256 Text
    recordFile Text
    UniquePilotBindingSession surveySessionId
    UniquePilotBindingToken tokenSha256
    deriving Show
|]

data App = App
  { appPool :: ConnectionPool
  , appSessionKeyPath :: FilePath
  , appSecureCookies :: Bool
  , appBindings :: Map.Map Text Binding
    -- ^ Proven issuance bindings, keyed by token sha256. Loaded once at start;
    -- a token that is not here does not exist.
  , appDogfoodEnabled :: Bool
    -- ^ The Catalog-backed debug surface at @/@. Off in production: a pilot
    -- annotator who lands on @/@ must not be able to start a dogfood session.
  }

mkYesod "App" [parseRoutes|
/ HomeR GET
/language LanguageR POST
/t/#Text TokenR GET POST
/instructions InstructionsR GET
/intro IntroR GET
/item/#Int ItemR GET
/item/#Int/decision DecisionR POST
/item/#Int/decision/edit EditDecisionR GET
/item/#Int/labels LabelsR POST
/item/#Int/evidence EvidenceR POST
/item/#Int/abstain AbstainR POST
/item/#Int/original OriginalR POST
/item/#Int/feedback FeedbackR POST
/done DoneR GET
/submission.json SubmissionR GET
|]

instance Yesod App where
  -- The app is served from the root of one host behind a TLS-terminating
  -- reverse proxy. Yesod's default guessApproot would build absolute URLs from
  -- the loopback request, which is plain HTTP, so form actions would come out
  -- as http://host/... on an https page and be blocked by form-action 'self'.
  approot = ApprootRelative

  makeSessionBackend app =
    let backend = fmap Just $ defaultClientSessionBackend (24 * 60) (appSessionKeyPath app)
     in if appSecureCookies app then sslOnlySessions backend else backend

  yesodMiddleware handler = do
    addHeader "Content-Security-Policy" "default-src 'self'; script-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; style-src 'self' 'unsafe-inline'"
    addHeader "X-Content-Type-Options" "nosniff"
    addHeader "Referrer-Policy" "no-referrer"
    defaultYesodMiddleware handler

  defaultLayout widget = do
    page <- widgetToPageContent $ do
      toWidget [lucius|
        :root { font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202124; background: #f6f7f8; }
        * { box-sizing: border-box; }
        body { margin: 0; }
        button, input, select, textarea { font: inherit; }
        .shell { width: min(760px, 100%); margin: 0 auto; padding: 24px 16px 64px; }
        .card { background: white; border: 1px solid #e1e4e8; border-radius: 18px; padding: clamp(20px, 5vw, 40px); box-shadow: 0 8px 30px rgb(0 0 0 / 0.04); }
        h1 { font-size: clamp(1.65rem, 5vw, 2.3rem); line-height: 1.15; margin: 0 0 24px; }
        h2 { margin-top: 32px; }
        h3 { margin-bottom: 8px; }
        p, li { line-height: 1.58; }
        .eyebrow { margin: 0 0 8px; font-size: .8rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #697077; }
        .stack { display: grid; gap: 16px; margin-top: 24px; }
        .primary, .secondary { border-radius: 12px; padding: 14px 18px; border: 1px solid #c9cdd2; background: white; cursor: pointer; text-decoration: none; color: inherit; }
        .primary { display: inline-block; background: #202124; color: white; border-color: #202124; text-align: center; font-weight: 700; }
        .secondary:hover { background: #f3f5f7; }
        .episode { display: grid; gap: 12px; margin: 20px 0 32px; }
        .source-note { color: #697077; margin: 0 0 8px; }
        .bubble { border-radius: 14px; padding: 14px 16px; line-height: 1.5; }
        .context { background: #f1f3f4; margin-right: 9%; }
        .target { background: #e9eefc; margin-left: 9%; }
        .original { margin-top: 12px; border-top: 1px solid #e1e4e8; padding-top: 12px; }
        .original summary { cursor: pointer; font-weight: 700; }
        form > div { margin-bottom: 14px; }
        form label { line-height: 1.45; }
        form input[type=text], form textarea, form select { width: 100%; border: 1px solid #c9cdd2; border-radius: 10px; padding: 12px; background: white; }
        form textarea { min-height: 96px; resize: vertical; }
        .field > label { display: block; font-weight: 650; margin-bottom: 8px; }
        .choices { display: grid; gap: 10px; }
        .choice { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px; align-items: start; padding: 12px; border: 1px solid #d7dade; border-radius: 12px; cursor: pointer; }
        .choice:hover { background: #f8f9fa; }
        .choice > input { margin: 3px 0 0; }
        .choice-text { overflow-wrap: anywhere; }
        .step-back { margin: 0 0 4px; }
        .step-back a { color: #3b5bdb; text-decoration: none; }
        .feedback-disclosure { margin-top: 28px; border-top: 1px solid #eceff1; padding-top: 16px; }
        .feedback-disclosure summary { cursor: pointer; color: #697077; font-size: .92rem; font-weight: 600; }
        .feedback-disclosure summary:hover { color: #202124; }
        .feedback-disclosure form { margin-top: 14px; }
        form input[type=checkbox], form input[type=radio] { margin-top: 4px; }
        .message-banner { padding: 12px 14px; border: 1px solid #b42318; border-radius: 10px; color: #8a1c13; background: #fff5f4; }
        .field-error { margin: 6px 0 0; color: #8a1c13; }
        .field-invalid > label { color: #8a1c13; }
        .category { border-top: 1px solid #eceff1; padding-top: 18px; margin-top: 18px; }
        .example-tag { font-weight: 700; }
        @media (max-width: 520px) {
          .shell { padding: 0; }
          .card { min-height: 100vh; border-radius: 0; border-left: 0; border-right: 0; }
          .context { margin-right: 4%; }
          .target { margin-left: 4%; }
        }
      |]
      widget
    withUrlRenderer [hamlet|
      $doctype 5
      <html>
        <head>
          <meta charset=utf-8>
          <meta name=viewport content="width=device-width, initial-scale=1">
          <title>#{pageTitle page}
          ^{pageHead page}
        <body>
          <main .shell>
            ^{pageBody page}
    |]

instance YesodPersist App where
  type YesodPersistBackend App = SqlBackend
  runDB action = do
    app <- getYesod
    runSqlPool action (appPool app)

instance RenderMessage App FormMessage where
  renderMessage _ _ = defaultFormMessage

-- | Which instrument a session is being taken under.
--
-- The version is a property of the session, not of the deployment: a
-- respondent who started before item feedback existed took hs-v1, and
-- must keep taking hs-v1 for the rest of that session however many times the
-- server is redeployed underneath them. Reading it off the running binary
-- instead would rewrite the provenance of an already-completed run, which is
-- the one thing a research instrument must never do to its own record.
data InstrumentVersion = InstrumentV1 | InstrumentV2 | InstrumentPilot
  deriving stock (Eq, Show)

instrumentVersionCode :: InstrumentVersion -> Text
instrumentVersionCode InstrumentV1 = "annotation-web-dogfood-hs-v1"
instrumentVersionCode InstrumentV2 = "annotation-web-dogfood-hs-v2"
-- | The token-bound pilot instrument: sealed presentation packet, exact texts,
-- canonical export. Its contract is the issuance record, not this binary.
instrumentVersionCode InstrumentPilot = "annotation-web-pilot-v1"

-- | The version new sessions are started under.
currentInstrument :: InstrumentVersion
currentInstrument = InstrumentV2

-- | Anything not recognisably hs-v2 -- no row at all from before this table
-- existed, the hs-v1 string itself, or a value from some future version this
-- binary has never heard of -- is hs-v1, and is never offered the newer steps.
instrumentFor :: SurveySessionId -> Handler InstrumentVersion
instrumentFor sid = do
  stored <- runDB $ getBy (UniqueSessionInstrument sid)
  pure $ case sessionInstrumentVersion . entityVal <$> stored of
    Just recorded | recorded == instrumentVersionCode InstrumentV2 -> InstrumentV2
                  | recorded == instrumentVersionCode InstrumentPilot -> InstrumentPilot
    _ -> InstrumentV1

-- | What a session shows: the Catalog-backed dogfood surface, or one sealed
-- pilot packet. Decided by the session's own binding row, never by the URL.
data Mode = Dogfood | Pilot Binding

sessionMode :: SurveySessionId -> Handler Mode
sessionMode sid = do
  stored <- runDB $ getBy (UniquePilotBindingSession sid)
  case stored of
    Nothing -> pure Dogfood
    Just (Entity _ pb) -> do
      app <- getYesod
      case Map.lookup (pilotBindingTokenSha256 pb) (appBindings app) of
        -- The record this session was bound to is not among the ones this
        -- server proved at start. Serving the session anyway would mean
        -- showing bytes nobody has vouched for; refusing is the only honest
        -- answer, and the message says what to fix.
        Nothing -> permissionDenied "this session's issuance record is not loaded on this server"
        Just binding
          | bindingUnchanged pb (bindRecord binding) -> pure (Pilot binding)
          | otherwise -> permissionDenied "this session's issuance record changed after the session started"

-- | The hashes the session was started under must still be the hashes the
-- loaded record carries. Anything else is a different packet, instruction or
-- ontology than the person was issued.
bindingUnchanged :: PilotBinding -> IssuanceRecord -> Bool
bindingUnchanged pb rec =
  pilotBindingPackageId pb == irPackageId rec
    && pilotBindingAnnotatorId pb == irAnnotatorId rec
    && pilotBindingItemsSha256 pb == irItemsSha rec
    && pilotBindingChecksumsSha256 pb == irChecksumsSha rec
    && pilotBindingPresentationSha256 pb == irPresentationSha rec
    && pilotBindingInstructionsSha256 pb == irInstructionsSha rec
    && pilotBindingOntologySha256 pb == irOntologySha rec

-- | One episode as shown, whichever surface it came from. The renderer only
-- ever sees this: exact texts in exact order with exactly one target.
data ShownMessage = ShownMessage
  { smAuthor :: Text
  , smText :: Text
  , smIsTarget :: Bool
  }

data Stimulus = Stimulus
  { stId :: Text
  , stShown :: [ShownMessage]
  , stTarget :: Text
  , stSourceLanguage :: Maybe Text
    -- ^ Dogfood only: the item's source language, shown as a note.
  , stOriginal :: Maybe [Message]
    -- ^ Dogfood only: the untranslated source, offered behind a reveal when the
    -- presentation is a translation. A pilot packet is never translated and
    -- never has one.
  }

stimuli :: Mode -> Language -> [Stimulus]
stimuli Dogfood lang = map (dogfoodStimulus lang) items
stimuli (Pilot binding) _ = map pilotStimulus (bindItems binding)

dogfoodStimulus :: Language -> Item -> Stimulus
dogfoodStimulus lang item =
  let presentation = presentationFor lang item
   in Stimulus
        { stId = itemId item
        , stShown =
            [ ShownMessage "A" (presentationContext presentation) False
            , ShownMessage "B" (presentationTarget presentation) True
            ]
        , stTarget = presentationTarget presentation
        , stSourceLanguage = Just (languageCode (itemSourceLanguage item))
        , stOriginal = if shouldOfferOriginal lang item then Just (itemSource item) else Nothing
        }

-- | Dumb on purpose: the packet row's messages, in the packet row's order,
-- with the packet row's target. No lookup anywhere else, no translation, no
-- reordering.
pilotStimulus :: PresentedItem -> Stimulus
pilotStimulus presented = Stimulus
  { stId = piId presented
  , stShown =
      [ ShownMessage (T.toUpper (pmAuthor m)) (pmText m) (pmId m == piTargetId presented)
      | m <- piMessages presented
      ]
  , stTarget = fromMaybe "" (presentedTarget presented)
  , stSourceLanguage = Nothing
  , stOriginal = Nothing
  }

type AppForm a = Html -> MForm Handler (FormResult a, Widget)

data Step = StepDecision | StepLabels | StepEvidence | StepAbstain
  deriving stock (Eq, Show)

-- | Option values carry the stable wire code instead of yesod-form's positional
-- index, so the rendered HTML matches the research contract and a re-rendered
-- form round-trips exactly the codes it was given.
wireOptions :: (a -> Text) -> (a -> Text) -> [a] -> OptionList a
wireOptions code display values = mkOptionList
  [ Option
      { optionDisplay = display value
      , optionInternalValue = value
      , optionExternalValue = code value
      }
  | value <- values
  ]

languageOptions :: OptionList Language
languageOptions = wireOptions languageCode display [RU, EN]
  where
    display RU = "Русский"
    display EN = "English"

decisionOptions :: Language -> OptionList Decision
decisionOptions lang = wireOptions decisionCode display [Assigned, NoneObserved, Abstained]
  where
    display Assigned = tr lang "assigned — наблюдается одна или несколько категорий" "assigned — one or more categories are observed"
    display NoneObserved = tr lang "none_observed — фрагмента достаточно; категории не наблюдаются" "none_observed — enough context; no category is observed"
    display Abstained = tr lang "abstained — недостающий контекст мешает решить" "abstained — missing context prevents a decision"

labelOptions :: Language -> OptionList BehaviorLabel
labelOptions lang = wireOptions labelCode display allBehaviorLabels
  where
    display label = labelCode label <> " — " <> labelName lang label

reasonOptions :: Language -> OptionList AbstentionReason
reasonOptions lang = wireOptions abstentionCode (abstentionName lang) allAbstentionReasons

feedbackOptions :: Language -> OptionList F.FeedbackFlag
feedbackOptions lang = wireOptions F.feedbackFlagCode (F.feedbackFlagName lang) F.allFeedbackFlags

-- | One option as one row: the control, then all of its text beside it.
--
-- yesod-form's own renderers do not give this. @checkboxesField'@ emits the
-- inputs and their labels as flat siblings inside a single span, with no
-- element per option at all, so on a narrow screen ten inline elements reflow
-- into each other and it stops being clear which box belongs to which
-- category. That cannot be fixed from a stylesheet, because there is nothing
-- to style. Putting the input inside the label also makes the whole row a tap
-- target rather than just the box.
choiceRow :: Text -> Text -> Text -> [(Text, Text)] -> Bool -> Bool -> Option a -> Widget
choiceRow inputType groupId name attrs isRequired isChosen option =
  let optionId = groupId <> "-" <> optionExternalValue option
   in [whamlet|
        <label .choice for=#{optionId}>
          <input ##{optionId} type=#{inputType} name=#{name} value=#{optionExternalValue option} *{attrs} :isRequired:required :isChosen:checked>
          <span .choice-text>#{optionDisplay option}
      |]

radioChoiceField :: Eq a => Handler (OptionList a) -> Field Handler a
radioChoiceField options = (radioField' options) { fieldView = view }
  where
    view groupId name attrs val isRequired = do
      choices <- olOptions <$> handlerToWidget options
      [whamlet|
        <span ##{groupId} .choices>
          $forall option <- choices
            ^{choiceRow "radio" groupId name attrs isRequired (chosen val option) option}
      |]
    chosen (Right value) option = optionInternalValue option == value
    chosen (Left _) _ = False

checkboxChoiceField :: Eq a => Handler (OptionList a) -> Field Handler [a]
checkboxChoiceField options = (checkboxesField' options) { fieldView = view }
  where
    view groupId name attrs val _isRequired = do
      choices <- olOptions <$> handlerToWidget options
      [whamlet|
        <span ##{groupId} .choices>
          $forall option <- choices
            ^{choiceRow "checkbox" groupId name attrs False (chosen val option) option}
      |]
    chosen (Right values) option = optionInternalValue option `elem` values
    chosen (Left _) _ = False

-- | One field, its label and the validation message that belongs to it.
--
-- yesod-form only fills 'fvErrors' for failures the field itself produced, so
-- cross-field rules pass their message in separately rather than surfacing as a
-- page-level banner detached from the input that caused them.
fieldRow :: Maybe Html -> FieldView App -> Widget
fieldRow crossFieldError view = [whamlet|
  <div .field :isJust fieldError:.field-invalid>
    <label for=#{fvId view}>#{fvLabel view}
    ^{fvInput view}
    $maybe err <- fieldError
      <p .field-error>#{err}
|]
  where
    fieldError = maybe crossFieldError Just (fvErrors view)

-- | Like yesod-form's @renderDivs@, but rendering each field through 'fieldRow'.
renderFields :: FormRender Handler a
renderFields aform fragment = do
  (result, viewsFront) <- aFormToForm aform
  let widget = [whamlet|
        #{fragment}
        $forall view <- viewsFront []
          ^{fieldRow Nothing view}
      |]
  pure (result, widget)

fieldSettings :: Text -> Text -> FieldSettings App
fieldSettings label name = FieldSettings
  { fsLabel = SomeMessage label
  , fsTooltip = Nothing
  , fsId = Just name
  , fsName = Just name
  , fsAttrs = []
  }

languageForm :: AppForm Language
languageForm = renderFields $ areq
  (radioChoiceField (pure languageOptions))
  (fieldSettings "Язык предъявления / Presentation language" "language")
  Nothing

-- | The current decision is offered back as the default so that revisiting the
-- step shows what was chosen rather than an empty form.
decisionForm :: Language -> Maybe Decision -> AppForm Decision
decisionForm lang current = renderFields $ areq
  (radioChoiceField (pure (decisionOptions lang)))
  (fieldSettings (tr lang "Решение" "Decision") "decision")
  current

-- | A single multi-valued field rather than five booleans: "at least one
-- category" is then a failure of that field, so the message lands under the
-- checkbox group instead of floating at the top of the page.
labelsForm :: Language -> AppForm [BehaviorLabel]
labelsForm lang = renderFields $ areqMsg
  (checkboxChoiceField (pure (labelOptions lang)))
  (fieldSettings (tr lang "Категории" "Categories") "labels")
  (tr lang "Выберите хотя бы одну категорию." "Select at least one category.")
  Nothing

-- | Quotes are checked against the target text exactly as it was shown, and
-- stored exactly as typed: no trimming, no re-quoting, no normalisation
-- (checkEvidenceText). A quote that is not a verbatim span is a rejected
-- submission, not a corrected one.
evidenceForm :: Language -> Text -> [BehaviorLabel] -> AppForm [(BehaviorLabel, Text)]
evidenceForm lang target labels = renderFields $ traverse quoteField labels
  where
    quoteField label = (label,) <$> areq
      (check exactSpan textField)
      (fieldSettings
        (labelCode label <> " — " <> tr lang "самая короткая точная цитата" "shortest exact quote")
        ("evidence_" <> labelCode label))
      Nothing
    exactSpan raw = case checkEvidenceText target raw of
      Right quote -> Right quote
      Left _ -> Left $ tr lang
          "Цитата должна быть точным непрерывным фрагментом размечаемого сообщения."
          "The quote must be an exact continuous span from the target message."

-- | Monadic rather than applicative: whether the note is required depends on
-- the reason submitted alongside it, which an applicative form cannot see.
abstainForm :: Language -> AppForm (AbstentionReason, Maybe Text)
abstainForm lang fragment = do
  (reasonResult, reasonView) <- mreq
    (selectField (pure (reasonOptions lang)))
    (fieldSettings (tr lang "Причина abstained" "Abstention reason") "reason")
    Nothing
  (noteResult, noteView) <- mopt textField
    (fieldSettings (tr lang "Короткий комментарий, если нужен" "Short note, if needed") "note")
    Nothing
  let note = case noteResult of
        FormSuccess raw -> raw >>= nonBlank
        _ -> Nothing
      mustExplain = case reasonResult of
        FormSuccess reason -> abstentionRequiresNote reason
        _ -> False
      missingNote = mustExplain && isNothing note
      message = tr lang
        "Для ambiguous_between_labels и other нужен короткий комментарий."
        "A short note is required for ambiguous_between_labels and other."
      noteError
        | missingNote = Just (toHtml message)
        | otherwise = Nothing
      result
        | missingNote = FormFailure [message]
        | otherwise = (,) <$> reasonResult <*> (note <$ noteResult)
      widget = [whamlet|
        #{fragment}
        ^{fieldRow Nothing reasonView}
        ^{fieldRow noteError noteView}
      |]
  pure (result, widget)

nonBlank :: Text -> Maybe Text
nonBlank raw
  | T.null stripped = Nothing
  | otherwise = Just stripped
  where
    stripped = T.strip raw

-- | Dogfood remarks about the item. Everything is optional: an empty
-- submission is a valid answer and simply moves on.
feedbackForm :: Language -> Maybe ItemFeedback -> AppForm ([F.FeedbackFlag], Maybe Text)
feedbackForm lang stored = renderFields $
  (,)
    <$> (fromMaybe [] <$> aopt
          (checkboxChoiceField (pure (feedbackOptions lang)))
          (fieldSettings (tr lang "Что не так с примером? (необязательно)" "What is wrong with the example? (optional)") "feedback_flags")
          (Just (Just (maybe [] feedbackFlagsOf stored))))
    <*> (fmap unTextarea <$> aopt textareaField
          (fieldSettings (tr lang "Комментарий (необязательно)" "Comment (optional)") "feedback_note")
          (Just (Textarea <$> (stored >>= itemFeedbackNote))))

feedbackFlagFields :: [(F.FeedbackFlag, ItemFeedback -> Bool)]
feedbackFlagFields =
  [ (F.UnnaturalExample, itemFeedbackUnnaturalExample)
  , (F.InsufficientContext, itemFeedbackInsufficientContext)
  , (F.WordingOrTranslation, itemFeedbackWordingOrTranslation)
  , (F.OtherFeedback, itemFeedbackOther)
  ]

feedbackFlagsOf :: ItemFeedback -> [F.FeedbackFlag]
feedbackFlagsOf row = [flag | (flag, present) <- feedbackFlagFields, present row]

csrfForm :: AppForm ()
csrfForm = renderFields $ pure ()

getHomeR :: Handler Html
getHomeR = do
  app <- getYesod
  if appDogfoodEnabled app
    then generateFormPost languageForm >>= uncurry renderHome
    else renderClosed

-- | What @/@ shows when the dogfood surface is off: nothing to start. Pilot
-- annotators arrive through their personal link and never need this page.
renderClosed :: Handler Html
renderClosed = defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>Relationship Fix
      <h1>Здесь нет открытого исследования / No open study here
      <p>Если вы участвуете в разметке, откройте личную ссылку, которую вам прислал фасилитатор. / If you are taking part in the annotation study, open the personal link the facilitator sent you.
  |]

renderHome :: Widget -> Enctype -> Handler Html
renderHome widget enctype = defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>Relationship Fix · Haskell/Yesod dogfood
      <h1>Язык предъявления / Presentation language
      <p>Выберите язык интерфейса и эпизодов. / Choose the interface and episode presentation language.
      <form method=post action=@{LanguageR} enctype=#{enctype} .stack>
        ^{widget}
        <button type=submit .primary>Продолжить / Continue
  |]

postLanguageR :: Handler Html
postLanguageR = do
  app <- getYesod
  unless (appDogfoodEnabled app) notFound
  ((result, widget), enctype) <- runFormPost languageForm
  case result of
    FormSuccess lang -> do
      now <- liftIO getCurrentTime
      sid <- runDB $ do
        created <- insert $ SurveySession (languageCode lang) now Nothing
        insert_ $ SessionInstrument created (instrumentVersionCode currentInstrument)
        pure created
      setSession "annotation_session_id" (T.pack $ show $ fromSqlKey sid)
      logEvent sid Nothing "language_selected" (Just $ languageCode lang)
      redirect IntroR
    _ -> renderHome widget enctype

-- | The personal link. The token is hashed and looked up among the bindings
-- this server proved at start; an unknown token is a 404 with nothing else
-- said.
--
-- GET never claims the token: a session that already exists (from an earlier
-- claim, on this or another device) is resumed, but a token nobody has
-- claimed yet only renders a landing page with a button. Link-preview bots,
-- antivirus scanners and corporate proxies all prefetch bare GETs; if GET
-- itself created the session, the first "real" open could belong to one of
-- those instead of the person the link was issued to, and nobody would be
-- able to tell from the server's own state. Only POST -- an explicit,
-- CSRF-protected "Начать" -- claims an unclaimed token.
getTokenR :: Text -> Handler Html
getTokenR token = do
  app <- getYesod
  let key = tokenSha token
  case Map.lookup key (appBindings app) of
    Nothing -> notFound
    Just binding -> do
      existing <- runDB $ getBy (UniquePilotBindingToken key)
      case existing of
        Just (Entity _ pb)
          | bindingUnchanged pb (bindRecord binding) -> resumeClaimed pb
          | otherwise -> permissionDenied "this session's issuance record changed after the session started"
        Nothing -> generateFormPost csrfForm >>= uncurry (renderClaim (bindUiLanguage binding))

-- | The only handler that may create a @PilotBinding@. Same token, same
-- lookup and the same "already claimed" branch as the GET above -- claiming
-- twice (a resent form, two tabs) resumes rather than double-inserts -- but
-- an unclaimed token only ever becomes a session here, behind a form
-- submission a prefetching bot cannot produce.
postTokenR :: Text -> Handler Html
postTokenR token = do
  app <- getYesod
  let key = tokenSha token
  case Map.lookup key (appBindings app) of
    Nothing -> notFound
    Just binding -> do
      let rec = bindRecord binding
      existing <- runDB $ getBy (UniquePilotBindingToken key)
      case existing of
        Just (Entity _ pb)
          | bindingUnchanged pb rec -> resumeClaimed pb
          | otherwise -> permissionDenied "this session's issuance record changed after the session started"
        Nothing -> do
          ((result, _), _) <- runFormPost csrfForm
          case result of
            FormSuccess () -> claimUnclaimed key rec (bindUiLanguage binding) >>= resumeClaimed
            _ -> invalidArgs ["invalid claim request"]

-- | Create the binding for a token this request's own check just found
-- unclaimed -- and survive a second request that got past the same check for
-- the same reason. The check above and this insert are two separate
-- round trips to the database, not one transaction, so two POSTs arriving
-- close enough both reach here having seen "unclaimed". @insertUnique@ is
-- what actually decides that only once: it performs the insert and hands
-- back the key, or -- if @UniquePilotBindingToken@ already has a row, because
-- the other request's insert already committed -- hands back @Nothing@
-- instead of letting the write fail. The loser's own @SurveySession@ /
-- @SessionInstrument@ rows are left in place, unreferenced by any
-- @PilotBinding@ and thus never surfaced anywhere: an orphan is a fine price
-- for "exactly one claim wins" not depending on which of two requests a
-- database file lock happened to let through first.
claimUnclaimed :: Text -> IssuanceRecord -> Language -> Handler PilotBinding
claimUnclaimed key rec lang = do
  now <- liftIO getCurrentTime
  outcome <- runDB $ do
    sid <- insert $ SurveySession (languageCode lang) now Nothing
    insert_ $ SessionInstrument sid (instrumentVersionCode InstrumentPilot)
    let candidate = PilotBinding sid key (irPackageId rec) (irAnnotatorId rec)
          (irItemsSha rec) (irChecksumsSha rec) (irPresentationSha rec)
          (irInstructionsSha rec) (irOntologySha rec) (T.pack (irRecordFile rec))
    won <- insertUnique candidate
    case won of
      Just _ -> pure (Left (sid, candidate))
      Nothing -> Right <$> getBy (UniquePilotBindingToken key)
  case outcome of
    Left (sid, pb) -> do
      logEvent sid Nothing "pilot_session_bound" (Just (irPackageId rec <> "/" <> irAnnotatorId rec))
      pure pb
    Right (Just (Entity _ pb)) -> pure pb
    Right Nothing -> error "unreachable: insertUnique found a conflict, so a row exists"

resumeClaimed :: PilotBinding -> Handler Html
resumeClaimed pb = do
  setSession "annotation_session_id" (T.pack $ show $ fromSqlKey (pilotBindingSurveySessionId pb))
  redirect IntroR

-- | Shown only for a token nobody has claimed yet: no session, no cookie, no
-- database row -- a GET that lands here twice, ten times, or never followed
-- by the POST leaves exactly nothing behind.
renderClaim :: Language -> Widget -> Enctype -> Handler Html
renderClaim lang widget enctype = defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>Relationship Fix
      <h1>#{tr lang "Личная ссылка" "Personal link"}
      <p>#{tr lang "Эта ссылка предназначена только вам. Нажмите «Начать», чтобы открыть разметку." "This link is meant for you alone. Press \"Start\" to open the annotation."}
      <form #claim-form method=post enctype=#{enctype} .stack>
        ^{widget}
        <button type=submit .primary>#{tr lang "Начать" "Start"}
  |]

-- | The instruction document the session is bound to, byte for byte, as the
-- record's hash proved it at start. Not rendered, not paraphrased.
getInstructionsR :: Handler TypedContent
getInstructionsR = do
  (sid, _) <- requireSurveySession
  mode <- sessionMode sid
  case mode of
    Dogfood -> notFound
    Pilot binding -> do
      addHeader "Content-Disposition" "inline; filename=pilot-instructions.md"
      pure $ TypedContent "text/plain; charset=utf-8" (toContent (bindInstructions binding))

getIntroR :: Handler Html
getIntroR = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  mode <- sessionMode sid
  case mode of
    Pilot binding -> renderPilotIntro lang binding
    Dogfood -> defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>Relationship Fix · no-JS annotation dogfood
      <h1>#{tr lang "Исследование разметки диалогов" "Dialogue annotation study"}
      <p>#{tr lang "Мы проверяем, насколько одинаково разные люди применяют одни и те же операциональные категории к фрагментам диалога. Здесь не оцениваются вы или ваши отношения." "We are testing how consistently different people apply the same operational categories to dialogue excerpts. We are not evaluating you or your relationship."}
      <p><strong>#{tr lang "Главное правило:" "Main rule:"}</strong> #{tr lang "размечайте только то, что наблюдаемо в предоставленном фрагменте. Не угадывайте мотив, характер или намерение человека." "annotate only what is observable in the provided excerpt. Do not infer a person's motive, character, or intention."}
      <h2>#{tr lang "Категории: определения и граничные примеры" "Categories: definitions and boundary examples"}
      $forall label <- allBehaviorLabels
        <section .category>
          <h3>#{labelCode label} — #{labelName lang label}
          <p>#{labelDefinition lang label}
          <ul>
            $forall example <- labelExamples lang label
              <li>
                <span .example-tag>#{fst example}:
                \ #{snd example}
      <h2>none_observed vs abstained
      <p><strong>none_observed</strong> — #{tr lang "фрагмента достаточно, и ни одна активная категория не наблюдается. Всю историю отношений знать не нужно." "the excerpt provides enough context, and none of the active categories is observed. You do not need the entire relationship history."}
      <p><strong>abstained</strong> — #{tr lang "недостающий контекст реально мешает решить, присутствует категория или нет. Не выбирайте abstained просто потому, что дополнительный контекст теоретически существует." "missing context genuinely prevents deciding whether a category is present. Do not choose abstained merely because additional context could theoretically exist."}
      <p><strong>Evidence quote:</strong> #{tr lang "самый короткий непрерывный точный фрагмент размечаемого сообщения, достаточный для выбранной категории." "the shortest continuous exact span from the target message sufficient for the selected category."}
      <p>
        <a href=@{ItemR 0} .primary>#{tr lang "Начать" "Start"}
  |]

-- | The pilot intro: the bound instruction document (linked byte-exact, with
-- its hash on the page so the person can match it against what the
-- facilitator said they would get) and the active labels of the pinned
-- ontology artifact, rendered from that artifact. Nothing from the dogfood
-- glossary appears here.
renderPilotIntro :: Language -> Binding -> Handler Html
renderPilotIntro lang binding = do
  let rec = bindRecord binding
      episodeCount = length (bindItems binding)
      ontologyLabels = bindOntology binding
      nameOf label = tr lang (O.olNameRu label) (O.olNameEn label)
  defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>Relationship Fix · #{irPackageId rec}
      <h1>#{tr lang "Разметка диалогов" "Dialogue annotation"}
      <p>#{tr lang "Вы участвуете под анонимным id" "You are taking part under the anonymous id"} <strong>#{irAnnotatorId rec}</strong>. #{tr lang "Эпизодов:" "Episodes:"} #{episodeCount}.
      <h2>#{tr lang "Инструкция" "Instructions"}
      <p>#{tr lang "Прочитайте инструкцию целиком до первого эпизода. Это ровно тот документ, который вам выдан; его отпечаток:" "Read the instructions in full before the first episode. This is exactly the document you were issued; its fingerprint:"}
      <p><code>sha256 #{irInstructionsSha rec}</code>
      <p>
        <a href=@{InstructionsR} .secondary>#{tr lang "Открыть инструкцию" "Open the instructions"}
      <h2>#{tr lang "Категории" "Categories"} · #{irOntologyVersion rec}
      <p>#{tr lang "Определения ниже взяты из закреплённой версии онтологии" "The definitions below are taken from the pinned ontology version"} (<code>sha256 #{T.take 12 (irOntologySha rec)}…</code>).
      $forall label <- ontologyLabels
        <section .category>
          <h3>#{O.olId label} — #{nameOf label}
          <p>#{O.olDefinition label}
          $if not (null (O.olInclusion label))
            <p><strong>#{tr lang "Включает:" "Includes:"}</strong>
            <ul>
              $forall criterion <- O.olInclusion label
                <li>#{criterion}
          $if not (null (O.olExclusion label))
            <p><strong>#{tr lang "Не включает:" "Excludes:"}</strong>
            <ul>
              $forall criterion <- O.olExclusion label
                <li>#{criterion}
          $if not (null (O.olExamples label))
            <ul>
              $forall example <- O.olExamples label
                <li>
                  <span .example-tag>#{O.oeVerdict example} (#{O.oeLanguage example}):
                  \ #{O.oeText example}
                  $if not (T.null (O.oeRationale example))
                    \ — #{O.oeRationale example}
      <h2>none_observed vs abstained
      <p><strong>none_observed</strong> — #{tr lang "фрагмента достаточно, и ни одна активная категория не наблюдается." "the excerpt provides enough context, and none of the active categories is observed."}
      <p><strong>abstained</strong> — #{tr lang "недостающий контекст реально мешает решить. Причина обязательна." "missing context genuinely prevents deciding. A reason is required."}
      <p><strong>Evidence quote:</strong> #{tr lang "точный непрерывный фрагмент размечаемого сообщения, скопированный как есть." "an exact continuous span of the target message, copied as is."}
      <p>
        <a href=@{ItemR 0} .primary>#{tr lang "Начать" "Start"}
  |]

-- | Everything a step needs about the item being annotated, read once per
-- request so that a re-render after a rejected POST shows the same state the
-- respondent was looking at when they submitted.
data ItemContext = ItemContext
  { ctxSessionId :: SurveySessionId
  , ctxLanguage :: Language
  , ctxIndex :: Int
  , ctxStimulus :: Stimulus
  , ctxCount :: Int
  , ctxAnnotationId :: AnnotationId
  , ctxAnnotation :: Annotation
  , ctxLabels :: [BehaviorLabel]
  , ctxEvidence :: [(BehaviorLabel, Text)]
  , ctxFeedback :: Maybe ItemFeedback
  , ctxInstrument :: InstrumentVersion
  }

itemContext :: Int -> Handler ItemContext
itemContext index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  mode <- sessionMode sid
  let episodes = stimuli mode lang
  stimulus <- stimulusAt episodes index
  Entity aid annotation <- ensureAnnotation sid (stId stimulus)
  labels <- loadLabels aid
  evidence <- loadEvidence aid
  feedback <- loadFeedback aid
  instrument <- instrumentFor sid
  pure ItemContext
    { ctxSessionId = sid
    , ctxLanguage = lang
    , ctxIndex = index
    , ctxStimulus = stimulus
    , ctxCount = length episodes
    , ctxAnnotationId = aid
    , ctxAnnotation = annotation
    , ctxLabels = labels
    , ctxEvidence = evidence
    , ctxFeedback = feedback
    , ctxInstrument = instrument
    }

-- | Which step the respondent is on, among the ones the annotation itself can
-- be incomplete on. Item feedback is not one of these: it is optional,
-- available inline alongside every step rather than gating any of them, and
-- never a condition on the annotation being correct.
currentStep :: ItemContext -> Step
currentStep ctx = stepFor (ctxAnnotation ctx) (ctxLabels ctx)

getItemR :: Int -> Handler Html
getItemR index = do
  ctx <- itemContext index
  if annotationComplete (ctxAnnotation ctx) (ctxLabels ctx) (ctxEvidence ctx)
    then advanceFrom (ctxCount ctx) index
    else do
      let lang = ctxLanguage ctx
      case currentStep ctx of
        StepDecision -> generateFormPost (decisionForm lang (storedDecision ctx)) >>= uncurry (renderStep ctx StepDecision)
        StepLabels -> generateFormPost (labelsForm lang) >>= uncurry (renderStep ctx StepLabels)
        StepEvidence -> generateFormPost (evidenceForm lang (stTarget (ctxStimulus ctx)) (ctxLabels ctx)) >>= uncurry (renderStep ctx StepEvidence)
        StepAbstain -> generateFormPost (abstainForm lang) >>= uncurry (renderStep ctx StepAbstain)

-- | Lets a respondent reconsider the decision of the item they are on without
-- using browser Back. Renders only; every write stays in 'postDecisionR'.
getEditDecisionR :: Int -> Handler Html
getEditDecisionR index = do
  ctx <- itemContext index
  generateFormPost (decisionForm (ctxLanguage ctx) (storedDecision ctx))
    >>= uncurry (renderStep ctx StepDecision)

stepRoute :: Step -> Int -> Route App
stepRoute StepDecision = DecisionR
stepRoute StepLabels = LabelsR
stepRoute StepEvidence = EvidenceR
stepRoute StepAbstain = AbstainR

stepTitle :: Language -> Step -> Text
stepTitle lang step = case step of
  StepDecision -> tr lang "Решение" "Decision"
  StepLabels -> tr lang "Категории" "Categories"
  StepEvidence -> tr lang "Цитаты-доказательства" "Evidence quotes"
  StepAbstain -> tr lang "Причина abstained" "Abstention reason"

-- | Renders one step of one item. A rejected POST hands its own form widget
-- back here, so the respondent keeps every value they submitted.
renderStep :: ItemContext -> Step -> Widget -> Enctype -> Handler Html
renderStep ctx step widget enctype = do
  (originalWidget, originalEnctype) <- generateFormPost csrfForm
  -- Generated on every render, alongside whatever step is showing, rather
  -- than only after the annotation is complete: a respondent may notice
  -- something wrong with the example before they have decided how to
  -- annotate it. hs-v1 sessions never had this UI at all and must not gain
  -- it retroactively underneath an already-running session.
  (feedbackWidget, feedbackEnctype) <- generateFormPost (feedbackForm (ctxLanguage ctx) (ctxFeedback ctx))
  let lang = ctxLanguage ctx
      stimulus = ctxStimulus ctx
      index = ctxIndex ctx
      annotation = ctxAnnotation ctx
      action = stepRoute step index
      -- Hamlet's interpolation grammar has no infix operators, so the test
      -- has to be a plain name by the time the template sees it.
      canEditDecision = step `elem` [StepLabels, StepEvidence, StepAbstain]
      showFeedback = ctxInstrument ctx /= InstrumentV1
      targetHeading = tr lang "Размечаемое сообщение" "Target message"
  defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>#{index + 1} / #{ctxCount ctx}
      <h1>#{tr lang "Пример" "Example"} #{index + 1}
      <div .episode>
        $maybe source <- stSourceLanguage stimulus
          <p .source-note>#{tr lang "Источник" "Source"}: <strong>#{source}</strong>
        $forall shown <- stShown stimulus
          $if smIsTarget shown
            <div .bubble .target><strong>#{targetHeading} · #{smAuthor shown}</strong><br>#{smText shown}
          $else
            <div .bubble .context><strong>#{smAuthor shown}</strong><br>#{smText shown}
        $maybe original <- stOriginal stimulus
          $if annotationOriginalRevealed annotation
            <details open .original>
              <summary>#{tr lang "Оригинал" "Original"}
              $forall sourceMessage <- original
                <p><strong>#{messageAuthor sourceMessage}</strong>: #{messageText sourceMessage}
          $else
            <form #reveal-form method=post action=@{OriginalR index} enctype=#{originalEnctype}>
              ^{originalWidget}
              <button type=submit .secondary>#{tr lang "Показать оригинал" "Show original"}
      $if canEditDecision
        <p .step-back>
          <a href=@{EditDecisionR index}>← #{tr lang "Изменить решение" "Change decision"}
      <h2>#{stepTitle lang step}
      <form #step-form method=post action=@{action} enctype=#{enctype} .stack>
        ^{widget}
        <button type=submit .primary>#{tr lang "Продолжить" "Continue"}
      $if showFeedback
        <details .feedback-disclosure>
          <summary>#{tr lang "Проблемы с вопросом?" "Problems with this question?"}
          <form #feedback-form method=post action=@{FeedbackR index} enctype=#{feedbackEnctype} .stack>
            ^{feedbackWidget}
            <button type=submit .secondary>#{tr lang "Отправить" "Submit"}
  |]

-- Every POST below follows the same rule: persist and redirect only once the
-- form is valid, otherwise re-render the same step in this request with the
-- submitted values and the field-level errors, writing nothing.

postDecisionR :: Int -> Handler Html
postDecisionR index = do
  ctx <- itemContext index
  ((result, widget), enctype) <- runFormPost (decisionForm (ctxLanguage ctx) (storedDecision ctx))
  case result of
    -- Confirming the decision already on record is not the same act as
    -- changing it. Re-selecting Assigned from the edit screen must not discard
    -- categories and quotes the respondent has already entered.
    FormSuccess decision
      | storedDecision ctx == Just decision -> do
          logEvent (ctxSessionId ctx) (Just $ stId (ctxStimulus ctx)) "decision_confirmed" (Just $ decisionCode decision)
          redirect (ItemR index)
      | otherwise -> do
          let aid = ctxAnnotationId ctx
          runDB $ do
            update aid
              [ AnnotationDecision =. Just (decisionCode decision)
              , AnnotationAbstentionReason =. Nothing
              , AnnotationAbstentionNote =. Nothing
              ]
            deleteWhere [AnnotationLabelAnnotationId ==. aid]
            deleteWhere [EvidenceAnnotationId ==. aid]
          logEvent (ctxSessionId ctx) (Just $ stId (ctxStimulus ctx)) "decision_submitted" (Just $ decisionCode decision)
          redirect (ItemR index)
    _ -> renderStep ctx StepDecision widget enctype

postLabelsR :: Int -> Handler Html
postLabelsR index = do
  ctx <- itemContext index
  requireDecision Assigned ctx
  ((result, widget), enctype) <- runFormPost (labelsForm (ctxLanguage ctx))
  case result of
    FormSuccess labels -> do
      let aid = ctxAnnotationId ctx
      runDB $ do
        deleteWhere [AnnotationLabelAnnotationId ==. aid]
        deleteWhere [EvidenceAnnotationId ==. aid]
        forM_ labels $ \label -> insert_ $ AnnotationLabel aid (labelCode label)
      logEvent (ctxSessionId ctx) (Just $ stId (ctxStimulus ctx)) "labels_submitted" (Just $ T.intercalate "," $ map labelCode labels)
      redirect (ItemR index)
    _ -> renderStep ctx StepLabels widget enctype

postEvidenceR :: Int -> Handler Html
postEvidenceR index = do
  ctx <- itemContext index
  requireDecision Assigned ctx
  let labels = ctxLabels ctx
  when (null labels) $ redirect (ItemR index)
  ((result, widget), enctype) <- runFormPost (evidenceForm (ctxLanguage ctx) (stTarget (ctxStimulus ctx)) labels)
  case result of
    FormSuccess pairs -> do
      let aid = ctxAnnotationId ctx
      runDB $ do
        deleteWhere [EvidenceAnnotationId ==. aid]
        forM_ pairs $ \(label, quote) -> insert_ $ Evidence aid (labelCode label) quote
      logEvent (ctxSessionId ctx) (Just $ stId (ctxStimulus ctx)) "evidence_submitted" (Just $ T.intercalate "," $ map (labelCode . fst) pairs)
      redirect (ItemR index)
    _ -> renderStep ctx StepEvidence widget enctype

postAbstainR :: Int -> Handler Html
postAbstainR index = do
  ctx <- itemContext index
  requireDecision Abstained ctx
  ((result, widget), enctype) <- runFormPost (abstainForm (ctxLanguage ctx))
  case result of
    FormSuccess (reason, note) -> do
      runDB $ update (ctxAnnotationId ctx)
        [ AnnotationAbstentionReason =. Just (abstentionCode reason)
        , AnnotationAbstentionNote =. note
        ]
      logEvent (ctxSessionId ctx) (Just $ stId (ctxStimulus ctx)) "abstention_submitted" (Just $ abstentionCode reason)
      redirect (ItemR index)
    _ -> renderStep ctx StepAbstain widget enctype

postFeedbackR :: Int -> Handler Html
postFeedbackR index = do
  ctx <- itemContext index
  -- This UI does not exist in hs-v1. Refusing rather than ignoring keeps a
  -- grandfathered session from being quietly turned into a hybrid of two
  -- instruments by a stale tab or a hand-made request.
  when (ctxInstrument ctx == InstrumentV1) notFound
  -- Independent of the annotation's own progress: a respondent may flag the
  -- example before, during or after deciding how to annotate it, and none of
  -- that is a condition on submitting feedback about it.
  ((result, _widget), _enctype) <- runFormPost (feedbackForm (ctxLanguage ctx) (ctxFeedback ctx))
  case result of
    FormSuccess (flags, rawNote) -> do
      let aid = ctxAnnotationId ctx
      runDB $ do
        deleteBy (UniqueItemFeedback aid)
        insert_ $ ItemFeedback aid
          (F.UnnaturalExample `elem` flags)
          (F.InsufficientContext `elem` flags)
          (F.WordingOrTranslation `elem` flags)
          (F.OtherFeedback `elem` flags)
          (rawNote >>= nonBlank)
      logEvent (ctxSessionId ctx) (Just $ stId (ctxStimulus ctx)) "feedback_submitted"
        (Just $ T.intercalate "," (map F.feedbackFlagCode flags))
      redirect (ItemR index)
    -- aopt fields on every part of this form make FormFailure practically
    -- unreachable; falling back to the item page (which will itself decide
    -- whether the annotation is complete) is simpler and safer here than
    -- trying to re-render a step from a widget that was never the step's own.
    _ -> redirect (ItemR index)

postOriginalR :: Int -> Handler Html
postOriginalR index = do
  ctx <- itemContext index
  ((result, _), _) <- runFormPost csrfForm
  case result of
    FormSuccess ()
      | isJust (stOriginal (ctxStimulus ctx)) -> do
          runDB $ update (ctxAnnotationId ctx) [AnnotationOriginalRevealed =. True]
          logEvent (ctxSessionId ctx) (Just $ stId (ctxStimulus ctx)) "original_revealed" Nothing
          redirect (ItemR index)
    _ -> invalidArgs ["invalid original reveal request"]

getDoneR :: Handler Html
getDoneR = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  mode <- sessionMode sid
  incomplete <- firstIncomplete sid (stimuli mode lang)
  case incomplete of
    Just index -> redirect (ItemR index)
    Nothing -> do
      now <- liftIO getCurrentTime
      unless (isJust $ surveySessionCompletedAt session) $ do
        runDB $ update sid [SurveySessionCompletedAt =. Just now]
        logEvent sid Nothing "session_completed" Nothing
      case mode of
        -- The collector keeps the answers; the facilitator exports them with
        -- annotation-web-export. There is nothing for the annotator to
        -- download and nothing more to do.
        Pilot _ -> defaultLayout [whamlet|
          <section .card>
            <p .eyebrow>Relationship Fix
            <h1>#{tr lang "Готово" "Done"}
            <p>#{tr lang "Спасибо. Все ответы сохранены под вашим анонимным id. Больше ничего делать не нужно; после сдачи ответы не редактируются." "Thank you. All answers are stored under your anonymous id. There is nothing more to do; answers are not edited after submission."}
        |]
        Dogfood -> defaultLayout [whamlet|
          <section .card>
            <p .eyebrow>Relationship Fix · Haskell/Yesod dogfood
            <h1>#{tr lang "Готово" "Done"}
            <p>#{tr lang "Ответы сохранены в SQLite на сервере. Финальный JSON содержит source/presentation provenance и факт раскрытия оригинала." "Answers are stored in SQLite on the server. The final JSON includes source/presentation provenance and whether the original was revealed."}
            <p>
              <a href=@{SubmissionR} .primary>#{tr lang "Скачать submission.json" "Download submission.json"}
        |]

getSubmissionR :: Handler Value
getSubmissionR = do
  (sid, session0) <- requireSurveySession
  mode <- sessionMode sid
  case mode of
    -- A pilot session has no browser download: canonical export is the
    -- facilitator's, offline, against the DB and the issuance record.
    Pilot _ -> notFound
    Dogfood -> pure ()
  instrument <- instrumentFor sid
  session1 <- runDB $ getJust sid
  lang1 <- sessionLanguage session1
  incomplete <- firstIncomplete sid (stimuli Dogfood lang1)
  when (isJust incomplete) $ permissionDenied "submission is incomplete"
  now <- liftIO getCurrentTime
  unless (isJust $ surveySessionCompletedAt session0) $ runDB $ update sid [SurveySessionCompletedAt =. Just now]
  session <- runDB $ getJust sid
  lang <- sessionLanguage session
  annotationValues <- forM items $ \item -> do
    Entity aid annotation <- ensureAnnotation sid (itemId item)
    labels <- loadLabels aid
    evidence <- loadEvidence aid
    feedback <- loadFeedback aid
    let presentation = presentationFor lang item
        evidenceFor label = lookup label evidence
    pure $ object $
      [ "item_id" .= itemId item
      , "source_language" .= languageCode (itemSourceLanguage item)
      , "presentation_language" .= languageCode lang
      , "displayed_translation_provenance" .= presentationProvenance presentation
      , "decision" .= annotationDecision annotation
      , "labels" .= [object ["label" .= labelCode label, "evidence" .= evidenceFor label] | label <- labels]
      , "abstention_reason" .= annotationAbstentionReason annotation
      , "abstention_note" .= annotationAbstentionNote annotation
      , "original_revealed" .= annotationOriginalRevealed annotation
      ]
        -- A separate axis from labels[]: what the respondent thinks of the
        -- item, not what they observed inside it. An hs-v1 submission does not
        -- carry the key at all, because that contract did not have it.
        <> case instrument of
             InstrumentV1 -> []
             InstrumentV2 -> ["feedback" .= feedbackValue feedback]
             -- unreachable: pilot sessions are refused above; listed so the
             -- match stays total when the next version is added
             InstrumentPilot -> ["feedback" .= feedbackValue feedback]
  addHeader "Content-Disposition" "attachment; filename=relationship-fix-submission.json"
  returnJson $ object
    [ "instrument_version" .= instrumentVersionCode instrument
    , "presentation_version" .= ("presentation-v1" :: Text)
    , "ontology_version" .= ("behavior-v0.2-candidate" :: Text)
    , "presentation_language" .= languageCode lang
    , "started_at" .= surveySessionStartedAt session
    , "completed_at" .= surveySessionCompletedAt session
    , "annotations" .= annotationValues
    ]

feedbackValue :: Maybe ItemFeedback -> Value
feedbackValue Nothing = Null
feedbackValue (Just row) = object
  [ "flags" .= map F.feedbackFlagCode (feedbackFlagsOf row)
  , "note" .= itemFeedbackNote row
  ]

requireSurveySession :: Handler (SurveySessionId, SurveySession)
requireSurveySession = do
  raw <- lookupSession "annotation_session_id"
  case raw >>= parseSessionKey of
    Nothing -> redirect HomeR
    Just sid -> do
      stored <- runDB $ get sid
      case stored of
        Nothing -> deleteSession "annotation_session_id" >> redirect HomeR
        Just session -> pure (sid, session)

parseSessionKey :: Text -> Maybe SurveySessionId
parseSessionKey raw = case TR.decimal raw of
  Right (n, rest) | T.null rest -> Just $ toSqlKey (n :: Int64)
  _ -> Nothing

sessionLanguage :: SurveySession -> Handler Language
sessionLanguage session = maybe (permissionDenied "invalid session language") pure $ parseLanguage $ surveySessionPresentationLanguage session

stimulusAt :: [Stimulus] -> Int -> Handler Stimulus
stimulusAt episodes index
  | index < 0 = notFound
  | index >= length episodes = redirect DoneR
  | otherwise = pure $ episodes !! index

ensureAnnotation :: SurveySessionId -> Text -> Handler (Entity Annotation)
ensureAnnotation sid itemID = runDB $ do
  existing <- getBy $ UniqueSessionItem sid itemID
  case existing of
    Just entity -> pure entity
    Nothing -> do
      let annotation = Annotation sid itemID Nothing Nothing Nothing False
      aid <- insert annotation
      pure $ Entity aid annotation

loadLabels :: AnnotationId -> Handler [BehaviorLabel]
loadLabels aid = do
  rows <- runDB $ selectList [AnnotationLabelAnnotationId ==. aid] [Asc AnnotationLabelId]
  pure $ catMaybes [parseBehaviorLabel $ annotationLabelLabelId value | Entity _ value <- rows]

loadFeedback :: AnnotationId -> Handler (Maybe ItemFeedback)
loadFeedback aid = fmap entityVal <$> runDB (getBy (UniqueItemFeedback aid))

storedDecision :: ItemContext -> Maybe Decision
storedDecision ctx = annotationDecision (ctxAnnotation ctx) >>= parseDecision

loadEvidence :: AnnotationId -> Handler [(BehaviorLabel, Text)]
loadEvidence aid = do
  rows <- runDB $ selectList [EvidenceAnnotationId ==. aid] [Asc EvidenceId]
  pure $ catMaybes [(, evidenceQuote value) <$> parseBehaviorLabel (evidenceLabelId value) | Entity _ value <- rows]

stepFor :: Annotation -> [BehaviorLabel] -> Step
stepFor annotation labels = case annotationDecision annotation >>= parseDecision of
  Nothing -> StepDecision
  Just NoneObserved -> StepDecision
  Just Abstained -> StepAbstain
  Just Assigned | null labels -> StepLabels
  Just Assigned -> StepEvidence

annotationComplete :: Annotation -> [BehaviorLabel] -> [(BehaviorLabel, Text)] -> Bool
annotationComplete annotation labels evidence = case annotationDecision annotation >>= parseDecision of
  Nothing -> False
  Just NoneObserved -> True
  Just Abstained -> isJust (annotationAbstentionReason annotation >>= parseAbstentionReason)
  Just Assigned -> not (null labels) && all (`elem` map fst evidence) labels

firstIncomplete :: SurveySessionId -> [Stimulus] -> Handler (Maybe Int)
firstIncomplete sid = go 0
  where
    go _ [] = pure Nothing
    go index (stimulus : rest) = do
      Entity aid annotation <- ensureAnnotation sid (stId stimulus)
      labels <- loadLabels aid
      evidence <- loadEvidence aid
      if annotationComplete annotation labels evidence then go (index + 1) rest else pure $ Just index

-- | A step guard, not a validation rule: reaching the labels step without an
-- assigned decision is a stale URL, so send the respondent back to the item.
requireDecision :: Decision -> ItemContext -> Handler ()
requireDecision expected ctx =
  unless ((annotationDecision (ctxAnnotation ctx) >>= parseDecision) == Just expected) $
    redirect (ItemR (ctxIndex ctx))

advanceFrom :: Int -> Int -> Handler a
advanceFrom total index
  | index + 1 < total = redirect (ItemR $ index + 1)
  | otherwise = redirect DoneR

logEvent :: SurveySessionId -> Maybe Text -> Text -> Maybe Text -> Handler ()
logEvent sid itemID kind value = do
  now <- liftIO getCurrentTime
  runDB $ insert_ $ AuditEvent sid itemID kind value now

-- | Opens the pool against a database that is already at the current schema,
-- and refuses to return a foundation otherwise. Kept here rather than in the
-- executable so tests can drive the real app.
--
-- Nothing on this path writes schema. That used to be a @runMigrationQuiet@
-- call, which on the production file meant "the server decided, while starting,
-- to rebuild a table that other rows reference". Schema is annotation-web-migrate's
-- job now; the server only checks, and a database it does not recognise is a
-- refusal to start rather than a repair attempt.
makeFoundation :: FilePath -> FilePath -> Bool -> IO App
makeFoundation dbPath sessionKeyPath secureCookies =
  makeFoundationWith FoundationConfig
    { fcDbPath = dbPath
    , fcSessionKeyPath = sessionKeyPath
    , fcSecureCookies = secureCookies
    , fcBindings = Map.empty
    , fcDogfoodEnabled = True
    }

data FoundationConfig = FoundationConfig
  { fcDbPath :: FilePath
  , fcSessionKeyPath :: FilePath
  , fcSecureCookies :: Bool
  , fcBindings :: Map.Map Text Binding
  , fcDogfoodEnabled :: Bool
  }

makeFoundationWith :: FoundationConfig -> IO App
makeFoundationWith cfg = do
  let dbPath = fcDbPath cfg
  Schema.assertCurrent dbPath
  pool <- runNoLoggingT $ createSqlitePool (T.pack dbPath) 4
  -- Migrant says the history is complete and the structure matches what that
  -- history builds. Persistent is asked the same question independently, from
  -- the entity model rather than from the migration list: anything it would
  -- still change is a schema the application cannot actually use.
  pending <- pendingEntityChanges pool
  unless (null pending) $ throwIO (Schema.SchemaPersistentDisagrees pending)
  pure App
    { appPool = pool
    , appSessionKeyPath = fcSessionKeyPath cfg
    , appSecureCookies = fcSecureCookies cfg
    , appBindings = fcBindings cfg
    , appDogfoodEnabled = fcDogfoodEnabled cfg
    }

-- | The statements persistent would run to bring this database in line with the
-- entity model, without running them. Empty on a database the migration history
-- built correctly.
pendingEntityChanges :: ConnectionPool -> IO [Text]
pendingEntityChanges = runSqlPool (showMigration migrateAll)

-- | The same question asked of a file rather than a pool, so a test can put
-- persistent on the stand without standing up the whole application.
pendingEntityChangesAt :: FilePath -> IO [Text]
pendingEntityChangesAt dbPath =
  runNoLoggingT $ withSqlitePool (T.pack dbPath) 1 (liftIO . pendingEntityChanges)
