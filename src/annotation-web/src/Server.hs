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
import Control.Monad (forM, forM_, unless, void, when)
import Control.Monad.Logger (runNoLoggingT)
import Data.Int (Int64)
import Data.Maybe (catMaybes, isJust, isNothing)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Read as TR
import Data.Time (UTCTime, getCurrentTime)
import Database.Persist.Sql (ConnectionPool, SqlBackend, fromSqlKey, runMigrationQuiet, runSqlPool, toSqlKey)
import Database.Persist.Sqlite (createSqlitePool)
import Domain
import Yesod

share [mkPersist sqlSettings, mkMigrate "migrateAll"] [persistLowerCase|
SurveySession
    presentationLanguage Text
    startedAt UTCTime
    completedAt UTCTime Maybe
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
AuditEvent
    surveySessionId SurveySessionId
    itemId Text Maybe
    kind Text
    value Text Maybe
    occurredAt UTCTime
    deriving Show
|]

data App = App
  { appPool :: ConnectionPool
  , appSessionKeyPath :: FilePath
  , appSecureCookies :: Bool
  }

mkYesod "App" [parseRoutes|
/ HomeR GET
/language LanguageR POST
/intro IntroR GET
/item/#Int ItemR GET
/item/#Int/decision DecisionR POST
/item/#Int/labels LabelsR POST
/item/#Int/evidence EvidenceR POST
/item/#Int/abstain AbstainR POST
/item/#Int/original OriginalR POST
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
        form ul { list-style: none; padding: 0; margin: 8px 0 0; display: grid; gap: 10px; }
        form li label { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border: 1px solid #d7dade; border-radius: 12px; }
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
  (radioField' (pure languageOptions))
  (fieldSettings "Язык предъявления / Presentation language" "language")
  Nothing

decisionForm :: Language -> AppForm Decision
decisionForm lang = renderFields $ areq
  (radioField' (pure (decisionOptions lang)))
  (fieldSettings (tr lang "Решение" "Decision") "decision")
  Nothing

-- | A single multi-valued field rather than five booleans: "at least one
-- category" is then a failure of that field, so the message lands under the
-- checkbox group instead of floating at the top of the page.
labelsForm :: Language -> AppForm [BehaviorLabel]
labelsForm lang = renderFields $ areqMsg
  (checkboxesField' (pure (labelOptions lang)))
  (fieldSettings (tr lang "Категории" "Categories") "labels")
  (tr lang "Выберите хотя бы одну категорию." "Select at least one category.")
  Nothing

evidenceForm :: Language -> Item -> [BehaviorLabel] -> AppForm [(BehaviorLabel, Text)]
evidenceForm lang item labels = renderFields $ traverse quoteField labels
  where
    quoteField label = (label,) <$> areq
      (check exactSpan textField)
      (fieldSettings
        (labelCode label <> " — " <> tr lang "самая короткая точная цитата" "shortest exact quote")
        ("evidence_" <> labelCode label))
      Nothing
    exactSpan raw
      | validEvidence lang item raw = Right (T.strip raw)
      | otherwise = Left $ tr lang
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

csrfForm :: AppForm ()
csrfForm = renderFields $ pure ()

getHomeR :: Handler Html
getHomeR = generateFormPost languageForm >>= uncurry renderHome

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
  ((result, widget), enctype) <- runFormPost languageForm
  case result of
    FormSuccess lang -> do
      now <- liftIO getCurrentTime
      sid <- runDB $ insert $ SurveySession (languageCode lang) now Nothing
      setSession "annotation_session_id" (T.pack $ show $ fromSqlKey sid)
      logEvent sid Nothing "language_selected" (Just $ languageCode lang)
      redirect IntroR
    _ -> renderHome widget enctype

getIntroR :: Handler Html
getIntroR = do
  (_, session) <- requireSurveySession
  lang <- sessionLanguage session
  defaultLayout [whamlet|
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

-- | Everything a step needs about the item being annotated, read once per
-- request so that a re-render after a rejected POST shows the same state the
-- respondent was looking at when they submitted.
data ItemContext = ItemContext
  { ctxSessionId :: SurveySessionId
  , ctxLanguage :: Language
  , ctxIndex :: Int
  , ctxItem :: Item
  , ctxAnnotationId :: AnnotationId
  , ctxAnnotation :: Annotation
  , ctxLabels :: [BehaviorLabel]
  , ctxEvidence :: [(BehaviorLabel, Text)]
  }

itemContext :: Int -> Handler ItemContext
itemContext index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  item <- itemAt index
  Entity aid annotation <- ensureAnnotation sid (itemId item)
  labels <- loadLabels aid
  evidence <- loadEvidence aid
  pure ItemContext
    { ctxSessionId = sid
    , ctxLanguage = lang
    , ctxIndex = index
    , ctxItem = item
    , ctxAnnotationId = aid
    , ctxAnnotation = annotation
    , ctxLabels = labels
    , ctxEvidence = evidence
    }

getItemR :: Int -> Handler Html
getItemR index = do
  ctx <- itemContext index
  if annotationComplete (ctxAnnotation ctx) (ctxLabels ctx) (ctxEvidence ctx)
    then advanceFrom index
    else do
      let lang = ctxLanguage ctx
      case stepFor (ctxAnnotation ctx) (ctxLabels ctx) of
        StepDecision -> generateFormPost (decisionForm lang) >>= uncurry (renderStep ctx StepDecision)
        StepLabels -> generateFormPost (labelsForm lang) >>= uncurry (renderStep ctx StepLabels)
        StepEvidence -> generateFormPost (evidenceForm lang (ctxItem ctx) (ctxLabels ctx)) >>= uncurry (renderStep ctx StepEvidence)
        StepAbstain -> generateFormPost (abstainForm lang) >>= uncurry (renderStep ctx StepAbstain)

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
  let lang = ctxLanguage ctx
      item = ctxItem ctx
      index = ctxIndex ctx
      annotation = ctxAnnotation ctx
      presentation = presentationFor lang item
      action = stepRoute step index
  defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>#{index + 1} / #{length items}
      <h1>#{tr lang "Пример" "Example"} #{index + 1}
      <div .episode>
        <p .source-note>#{tr lang "Источник" "Source"}: <strong>#{languageCode $ itemSourceLanguage item}</strong>
        <div .bubble .context><strong>A</strong><br>#{presentationContext presentation}
        <div .bubble .target><strong>#{tr lang "Размечаемое сообщение" "Target message"} · B</strong><br>#{presentationTarget presentation}
        $if shouldOfferOriginal lang item
          $if annotationOriginalRevealed annotation
            <details open .original>
              <summary>#{tr lang "Оригинал" "Original"}
              $forall sourceMessage <- itemSource item
                <p><strong>#{messageAuthor sourceMessage}</strong>: #{messageText sourceMessage}
          $else
            <form #reveal-form method=post action=@{OriginalR index} enctype=#{originalEnctype}>
              ^{originalWidget}
              <button type=submit .secondary>#{tr lang "Показать оригинал" "Show original"}
      <h2>#{stepTitle lang step}
      <form #step-form method=post action=@{action} enctype=#{enctype} .stack>
        ^{widget}
        <button type=submit .primary>#{tr lang "Продолжить" "Continue"}
  |]

-- Every POST below follows the same rule: persist and redirect only once the
-- form is valid, otherwise re-render the same step in this request with the
-- submitted values and the field-level errors, writing nothing.

postDecisionR :: Int -> Handler Html
postDecisionR index = do
  ctx <- itemContext index
  ((result, widget), enctype) <- runFormPost (decisionForm (ctxLanguage ctx))
  case result of
    FormSuccess decision -> do
      let aid = ctxAnnotationId ctx
      runDB $ do
        update aid
          [ AnnotationDecision =. Just (decisionCode decision)
          , AnnotationAbstentionReason =. Nothing
          , AnnotationAbstentionNote =. Nothing
          ]
        deleteWhere [AnnotationLabelAnnotationId ==. aid]
        deleteWhere [EvidenceAnnotationId ==. aid]
      logEvent (ctxSessionId ctx) (Just $ itemId (ctxItem ctx)) "decision_submitted" (Just $ decisionCode decision)
      if decision == NoneObserved then advanceFrom index else redirect (ItemR index)
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
      logEvent (ctxSessionId ctx) (Just $ itemId (ctxItem ctx)) "labels_submitted" (Just $ T.intercalate "," $ map labelCode labels)
      redirect (ItemR index)
    _ -> renderStep ctx StepLabels widget enctype

postEvidenceR :: Int -> Handler Html
postEvidenceR index = do
  ctx <- itemContext index
  requireDecision Assigned ctx
  let labels = ctxLabels ctx
  when (null labels) $ redirect (ItemR index)
  ((result, widget), enctype) <- runFormPost (evidenceForm (ctxLanguage ctx) (ctxItem ctx) labels)
  case result of
    FormSuccess pairs -> do
      let aid = ctxAnnotationId ctx
      runDB $ do
        deleteWhere [EvidenceAnnotationId ==. aid]
        forM_ pairs $ \(label, quote) -> insert_ $ Evidence aid (labelCode label) quote
      logEvent (ctxSessionId ctx) (Just $ itemId (ctxItem ctx)) "evidence_submitted" (Just $ T.intercalate "," $ map (labelCode . fst) pairs)
      advanceFrom index
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
      logEvent (ctxSessionId ctx) (Just $ itemId (ctxItem ctx)) "abstention_submitted" (Just $ abstentionCode reason)
      advanceFrom index
    _ -> renderStep ctx StepAbstain widget enctype

postOriginalR :: Int -> Handler Html
postOriginalR index = do
  ctx <- itemContext index
  ((result, _), _) <- runFormPost csrfForm
  case result of
    FormSuccess ()
      | shouldOfferOriginal (ctxLanguage ctx) (ctxItem ctx) -> do
          runDB $ update (ctxAnnotationId ctx) [AnnotationOriginalRevealed =. True]
          logEvent (ctxSessionId ctx) (Just $ itemId (ctxItem ctx)) "original_revealed" Nothing
          redirect (ItemR index)
    _ -> invalidArgs ["invalid original reveal request"]

getDoneR :: Handler Html
getDoneR = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  incomplete <- firstIncomplete sid
  case incomplete of
    Just index -> redirect (ItemR index)
    Nothing -> do
      now <- liftIO getCurrentTime
      unless (isJust $ surveySessionCompletedAt session) $ do
        runDB $ update sid [SurveySessionCompletedAt =. Just now]
        logEvent sid Nothing "session_completed" Nothing
      defaultLayout [whamlet|
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
  incomplete <- firstIncomplete sid
  when (isJust incomplete) $ permissionDenied "submission is incomplete"
  now <- liftIO getCurrentTime
  unless (isJust $ surveySessionCompletedAt session0) $ runDB $ update sid [SurveySessionCompletedAt =. Just now]
  session <- runDB $ getJust sid
  lang <- sessionLanguage session
  annotationValues <- forM items $ \item -> do
    Entity aid annotation <- ensureAnnotation sid (itemId item)
    labels <- loadLabels aid
    evidence <- loadEvidence aid
    let presentation = presentationFor lang item
        evidenceFor label = lookup label evidence
    pure $ object
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
  addHeader "Content-Disposition" "attachment; filename=relationship-fix-submission.json"
  returnJson $ object
    [ "instrument_version" .= ("annotation-web-dogfood-hs-v1" :: Text)
    , "presentation_version" .= ("presentation-v1" :: Text)
    , "ontology_version" .= ("behavior-v0.2-candidate" :: Text)
    , "presentation_language" .= languageCode lang
    , "started_at" .= surveySessionStartedAt session
    , "completed_at" .= surveySessionCompletedAt session
    , "annotations" .= annotationValues
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

itemAt :: Int -> Handler Item
itemAt index
  | index < 0 = notFound
  | index >= length items = redirect DoneR
  | otherwise = pure $ items !! index

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

firstIncomplete :: SurveySessionId -> Handler (Maybe Int)
firstIncomplete sid = go 0 items
  where
    go _ [] = pure Nothing
    go index (item : rest) = do
      Entity aid annotation <- ensureAnnotation sid (itemId item)
      labels <- loadLabels aid
      evidence <- loadEvidence aid
      if annotationComplete annotation labels evidence then go (index + 1) rest else pure $ Just index

-- | A step guard, not a validation rule: reaching the labels step without an
-- assigned decision is a stale URL, so send the respondent back to the item.
requireDecision :: Decision -> ItemContext -> Handler ()
requireDecision expected ctx =
  unless ((annotationDecision (ctxAnnotation ctx) >>= parseDecision) == Just expected) $
    redirect (ItemR (ctxIndex ctx))

advanceFrom :: Int -> Handler a
advanceFrom index
  | index + 1 < length items = redirect (ItemR $ index + 1)
  | otherwise = redirect DoneR

logEvent :: SurveySessionId -> Maybe Text -> Text -> Maybe Text -> Handler ()
logEvent sid itemID kind value = do
  now <- liftIO getCurrentTime
  runDB $ insert_ $ AuditEvent sid itemID kind value now

-- | Opens the pool, brings the schema up to date and returns the foundation.
-- Kept here rather than in the executable so tests can drive the real app.
makeFoundation :: FilePath -> FilePath -> Bool -> IO App
makeFoundation dbPath sessionKeyPath secureCookies = do
  pool <- runNoLoggingT $ createSqlitePool (T.pack dbPath) 4
  void $ runSqlPool (runMigrationQuiet migrateAll) pool
  pure App
    { appPool = pool
    , appSessionKeyPath = sessionKeyPath
    , appSecureCookies = secureCookies
    }
