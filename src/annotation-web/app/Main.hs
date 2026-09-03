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

module Main (main) where

import Catalog (items)
import Control.Monad (forM, forM_, unless, when)
import Control.Monad.IO.Class (liftIO)
import Control.Monad.Logger (runStdoutLoggingT)
import Data.Aeson (object, (.=))
import Data.Int (Int64)
import Data.Maybe (catMaybes, fromMaybe, isJust)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Read as TR
import Data.Time (UTCTime, getCurrentTime)
import Database.Persist
import Database.Persist.Sql (ConnectionPool, fromSqlKey, runSqlPool, toSqlKey)
import Database.Persist.Sqlite (createSqlitePool)
import Database.Persist.TH
import Domain
import Network.Wai.Handler.Warp (defaultSettings, runSettings, setHost, setPort)
import System.Environment (lookupEnv)
import Text.Read (readMaybe)
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
Event
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
        :root {
          font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          color: #202124;
          background: #f6f7f8;
          font-synthesis: none;
        }
        * { box-sizing: border-box; }
        body { margin: 0; }
        button, input, select, textarea { font: inherit; }
        .shell { width: min(760px, 100%); margin: 0 auto; padding: 24px 16px 64px; }
        .card {
          background: white;
          border: 1px solid #e1e4e8;
          border-radius: 18px;
          padding: clamp(20px, 5vw, 40px);
          box-shadow: 0 8px 30px rgb(0 0 0 / 0.04);
        }
        h1 { font-size: clamp(1.65rem, 5vw, 2.3rem); line-height: 1.15; margin: 0 0 24px; }
        h2 { margin-top: 32px; }
        h3 { margin-bottom: 8px; }
        p, li { line-height: 1.58; }
        .eyebrow { margin: 0 0 8px; font-size: .8rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #697077; }
        .stack { display: grid; gap: 16px; margin-top: 28px; }
        .primary, .secondary, .language-choice {
          border-radius: 12px;
          padding: 14px 18px;
          border: 1px solid #c9cdd2;
          background: white;
          text-align: left;
          cursor: pointer;
          text-decoration: none;
          color: inherit;
        }
        .primary { background: #202124; color: white; border-color: #202124; text-align: center; font-weight: 700; }
        .secondary:hover, .language-choice:hover { background: #f3f5f7; }
        .episode { display: grid; gap: 12px; margin: 20px 0 32px; }
        .source-note { color: #697077; margin: 0 0 8px; }
        .bubble { border-radius: 14px; padding: 14px 16px; line-height: 1.5; }
        .context { background: #f1f3f4; margin-right: 9%; }
        .target { background: #e9eefc; margin-left: 9%; }
        .original { margin-top: 12px; border-top: 1px solid #e1e4e8; padding-top: 12px; }
        .original summary { cursor: pointer; font-weight: 700; }
        .message { padding: 8px 0; }
        .form-field { margin-bottom: 14px; }
        .form-field label { display: block; font-weight: 650; margin-bottom: 6px; }
        .form-field input[type=text], .form-field textarea, .form-field select {
          width: 100%; border: 1px solid #c9cdd2; border-radius: 10px; padding: 12px; background: white;
        }
        .form-field ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
        .form-field li label { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border: 1px solid #d7dade; border-radius: 12px; font-weight: 500; }
        .form-field input[type=checkbox], .form-field input[type=radio] { margin-top: 4px; }
        .error, .message-banner { padding: 12px 14px; border: 1px solid #b42318; border-radius: 10px; color: #8a1c13; background: #fff5f4; }
        .category { border-top: 1px solid #eceff1; padding-top: 18px; margin-top: 18px; }
        .example-tag { font-weight: 700; }
        .muted { color: #697077; }
        .download { display: inline-block; }
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

instance RenderMessage App FormMessage where
  renderMessage _ _ = defaultFormMessage

type AppForm a = Html -> MForm Handler (FormResult a, Widget)

data LabelSelection = LabelSelection Bool Bool Bool Bool Bool

data Step = StepDecision | StepLabels | StepEvidence | StepAbstain

runDB :: SqlPersistT IO a -> Handler a
runDB action = do
  app <- getYesod
  liftIO $ runSqlPool action (appPool app)

fieldSettings :: Text -> Text -> FieldSettings App
fieldSettings label name = FieldSettings
  { fsLabel = SomeMessage label
  , fsTooltip = Nothing
  , fsId = Just name
  , fsName = Just name
  , fsAttrs = [("class", "control")]
  }

languageForm :: AppForm Text
languageForm = renderDivs $ areq
  (radioFieldList [("Русский", "ru"), ("English", "en")])
  (fieldSettings "Язык предъявления / Presentation language" "language")
  Nothing

decisionForm :: Language -> AppForm Text
decisionForm lang = renderDivs $ areq
  (radioFieldList
    [ (tr lang "assigned — наблюдается одна или несколько категорий" "assigned — one or more categories are observed", decisionCode Assigned)
    , (tr lang "none_observed — фрагмента достаточно; категории не наблюдаются" "none_observed — enough context; no category is observed", decisionCode NoneObserved)
    , (tr lang "abstained — недостающий контекст мешает решить" "abstained — missing context prevents a decision", decisionCode Abstained)
    ])
  (fieldSettings (tr lang "Решение" "Decision") "decision")
  Nothing

labelSelectionForm :: Language -> AppForm LabelSelection
labelSelectionForm lang = renderDivs $
  LabelSelection
    <$> checkbox BlameCriticism
    <*> checkbox PressureForChange
    <*> checkbox Validation
    <*> checkbox RepairAttempt
    <*> checkbox AvoidanceTopicShift
  where
    checkbox label = areq checkBoxField
      (fieldSettings (labelCode label <> " — " <> labelName lang label) (labelCode label))
      (Just False)

evidenceForm :: Language -> [BehaviorLabel] -> AppForm [(BehaviorLabel, Text)]
evidenceForm lang labels = renderDivs $ traverse one labels
  where
    one label = (label,) <$> areq textField
      (fieldSettings (labelCode label <> " — " <> tr lang "самая короткая точная цитата" "shortest exact quote") ("evidence_" <> labelCode label))
      Nothing

abstainForm :: Language -> AppForm (Text, Maybe Textarea)
abstainForm lang = renderDivs $
  (,)
    <$> areq
      (selectFieldList [(abstentionName lang r, abstentionCode r) | r <- allAbstentionReasons])
      (fieldSettings (tr lang "Причина abstained" "Abstention reason") "reason")
      Nothing
    <*> aopt textareaField
      (fieldSettings (tr lang "Комментарий, если нужен" "Note, if needed") "note")
      Nothing

csrfForm :: AppForm ()
csrfForm = renderDivs $ pure ()

selectedLabels :: LabelSelection -> [BehaviorLabel]
selectedLabels (LabelSelection a b c d e) = catMaybes
  [ if a then Just BlameCriticism else Nothing
  , if b then Just PressureForChange else Nothing
  , if c then Just Validation else Nothing
  , if d then Just RepairAttempt else Nothing
  , if e then Just AvoidanceTopicShift else Nothing
  ]

getHomeR :: Handler Html
getHomeR = renderHome Nothing

renderHome :: Maybe Text -> Handler Html
renderHome mError = do
  (widget, enctype) <- generateFormPost languageForm
  defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>Relationship Fix · Haskell/Yesod dogfood
      <h1>Язык предъявления / Presentation language
      <p>Выберите язык интерфейса и эпизодов. / Choose the interface and episode presentation language.
      $maybe err <- mError
        <p .error>#{err}
      <form method=post action=@{LanguageR} enctype=#{enctype} .stack>
        ^{widget}
        <button type=submit .primary>Продолжить / Continue
  |]

postLanguageR :: Handler Html
postLanguageR = do
  ((result, _), _) <- runFormPost languageForm
  case result of
    FormSuccess code
      | Just lang <- parseLanguage code -> do
          now <- liftIO getCurrentTime
          sid <- runDB $ insert $ SurveySession (languageCode lang) now Nothing
          setSession "annotation_session_id" (T.pack $ show $ fromSqlKey sid)
          logEvent sid Nothing "language_selected" (Just $ languageCode lang)
          redirect IntroR
    _ -> renderHome (Just "Некорректный выбор языка / Invalid language selection")

getIntroR :: Handler Html
getIntroR = do
  (_, session) <- requireSurveySession
  lang <- sessionLanguage session
  defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>Relationship Fix · no-JS annotation dogfood
      <h1>#{tr lang "Исследование разметки диалогов" "Dialogue annotation study"}
      <p>#{tr lang
        "Мы проверяем, насколько одинаково разные люди применяют одни и те же операциональные категории к фрагментам диалога. Здесь не оцениваются вы или ваши отношения."
        "We are testing how consistently different people apply the same operational categories to dialogue excerpts. We are not evaluating you or your relationship."}
      <p>
        <strong>#{tr lang "Главное правило:" "Main rule:"}
        #{tr lang
          " размечайте только то, что наблюдаемо в предоставленном фрагменте. Не угадывайте мотив, характер или намерение человека."
          " annotate only what is observable in the provided excerpt. Do not infer a person's motive, character, or intention."}
      <h2>#{tr lang "Категории: определения и граничные примеры" "Categories: definitions and boundary examples"}
      $forall label <- allBehaviorLabels
        <section .category>
          <h3>#{labelCode label} — #{labelName lang label}
          <p>#{labelDefinition lang label}
          <ul>
            $forall example <- labelExamples lang label
              <li><span .example-tag>#{fst example}:</span> #{snd example}
      <h2>none_observed vs abstained
      <p><strong>none_observed</strong> — #{tr lang "фрагмента достаточно, и ни одна активная категория не наблюдается. Всю историю отношений знать не нужно." "the excerpt provides enough context, and none of the active categories is observed. You do not need the entire relationship history."}
      <p><strong>abstained</strong> — #{tr lang "недостающий контекст реально мешает решить, присутствует категория или нет. Не выбирайте abstained просто потому, что дополнительный контекст теоретически существует." "missing context genuinely prevents deciding whether a category is present. Do not choose abstained merely because additional context could theoretically exist."}
      <p><strong>#{tr lang "Evidence quote:" "Evidence quote:"}</strong> #{tr lang "самый короткий непрерывный точный фрагмент размечаемого сообщения, достаточный для выбранной категории." "the shortest continuous exact span from the target message sufficient for the selected category."}
      <p><a href=@{ItemR 0} .primary .download>#{tr lang "Начать" "Start"}
  |]

getItemR :: Int -> Handler Html
getItemR index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  item <- itemAt index
  entity@(Entity aid annotation) <- ensureAnnotation sid (itemId item)
  labels <- loadLabels aid
  evidence <- loadEvidence aid
  if annotationComplete annotation labels evidence
    then advanceFrom index
    else do
      message <- getMessage
      (originalWidget, originalEnctype) <- generateFormPost csrfForm
      case stepFor annotation labels of
        StepDecision -> do
          (formWidget, enctype) <- generateFormPost (decisionForm lang)
          renderItemPage lang item index entity labels message originalWidget originalEnctype
            (tr lang "Решение" "Decision") formWidget enctype (DecisionR index)
        StepLabels -> do
          (formWidget, enctype) <- generateFormPost (labelSelectionForm lang)
          renderItemPage lang item index entity labels message originalWidget originalEnctype
            (tr lang "Категории" "Categories") formWidget enctype (LabelsR index)
        StepEvidence -> do
          (formWidget, enctype) <- generateFormPost (evidenceForm lang labels)
          renderItemPage lang item index entity labels message originalWidget originalEnctype
            (tr lang "Цитаты-доказательства" "Evidence quotes") formWidget enctype (EvidenceR index)
        StepAbstain -> do
          (formWidget, enctype) <- generateFormPost (abstainForm lang)
          renderItemPage lang item index entity labels message originalWidget originalEnctype
            (tr lang "Причина abstained" "Abstention reason") formWidget enctype (AbstainR index)

renderItemPage
  :: Language
  -> Item
  -> Int
  -> Entity Annotation
  -> [BehaviorLabel]
  -> Maybe Html
  -> Widget
  -> Enctype
  -> Text
  -> Widget
  -> Enctype
  -> Route App
  -> Handler Html
renderItemPage lang item index (Entity _ annotation) _ message originalWidget originalEnctype formTitle formWidget enctype action = do
  let presentation = presentationFor lang item
      total = length items
  defaultLayout [whamlet|
    <section .card>
      <p .eyebrow>#{index + 1} / #{total}
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
                <div .message><strong>#{messageAuthor sourceMessage}</strong>: #{messageText sourceMessage}
          $else
            <form method=post action=@{OriginalR index} enctype=#{originalEnctype}>
              ^{originalWidget}
              <button type=submit .secondary>#{tr lang "Показать оригинал" "Show original"}
      $maybe msg <- message
        <div .message-banner>^{msg}
      <h2>#{formTitle}
      <form method=post action=@{action} enctype=#{enctype} .stack>
        ^{formWidget}
        <button type=submit .primary>#{tr lang "Продолжить" "Continue"}
  |]

postDecisionR :: Int -> Handler Html
postDecisionR index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  item <- itemAt index
  Entity aid _ <- ensureAnnotation sid (itemId item)
  ((result, _), _) <- runFormPost (decisionForm lang)
  case result >>= parseDecision of
    FormSuccess decision -> do
      runDB $ do
        update aid
          [ AnnotationDecision =. Just (decisionCode decision)
          , AnnotationAbstentionReason =. Nothing
          , AnnotationAbstentionNote =. Nothing
          ]
        deleteWhere [AnnotationLabelAnnotationId ==. aid]
        deleteWhere [EvidenceAnnotationId ==. aid]
      logEvent sid (Just $ itemId item) "decision_submitted" (Just $ decisionCode decision)
      if decision == NoneObserved then advanceFrom index else redirect (ItemR index)
    _ -> do
      setLocalizedMessage lang "Выберите один вариант решения." "Choose one decision."
      redirect (ItemR index)

postLabelsR :: Int -> Handler Html
postLabelsR index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  item <- itemAt index
  Entity aid annotation <- ensureAnnotation sid (itemId item)
  requireDecision Assigned annotation index
  ((result, _), _) <- runFormPost (labelSelectionForm lang)
  case result of
    FormSuccess selection -> do
      let labels = selectedLabels selection
      if null labels
        then do
          setLocalizedMessage lang "Выберите хотя бы одну категорию." "Select at least one category."
          redirect (ItemR index)
        else do
          runDB $ do
            deleteWhere [AnnotationLabelAnnotationId ==. aid]
            deleteWhere [EvidenceAnnotationId ==. aid]
            forM_ labels $ \label -> insert_ $ AnnotationLabel aid (labelCode label)
          logEvent sid (Just $ itemId item) "labels_submitted" (Just $ T.intercalate "," $ map labelCode labels)
          redirect (ItemR index)
    _ -> do
      setLocalizedMessage lang "Некорректный набор категорий." "Invalid category selection."
      redirect (ItemR index)

postEvidenceR :: Int -> Handler Html
postEvidenceR index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  item <- itemAt index
  Entity aid annotation <- ensureAnnotation sid (itemId item)
  requireDecision Assigned annotation index
  labels <- loadLabels aid
  when (null labels) $ redirect (ItemR index)
  ((result, _), _) <- runFormPost (evidenceForm lang labels)
  case result of
    FormSuccess pairs -> do
      let normalized = [(label, T.strip quote) | (label, quote) <- pairs]
      if all (validEvidence lang item . snd) normalized
        then do
          runDB $ do
            deleteWhere [EvidenceAnnotationId ==. aid]
            forM_ normalized $ \(label, quote) -> insert_ $ Evidence aid (labelCode label) quote
          logEvent sid (Just $ itemId item) "evidence_submitted" (Just $ T.intercalate "," $ map (labelCode . fst) normalized)
          advanceFrom index
        else do
          setLocalizedMessage lang
            "Каждая цитата должна быть точным непрерывным фрагментом размечаемого сообщения."
            "Every evidence quote must be an exact continuous span from the target message."
          redirect (ItemR index)
    _ -> do
      setLocalizedMessage lang "Заполните evidence для каждой выбранной категории." "Provide evidence for every selected category."
      redirect (ItemR index)

postAbstainR :: Int -> Handler Html
postAbstainR index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  item <- itemAt index
  Entity aid annotation <- ensureAnnotation sid (itemId item)
  requireDecision Abstained annotation index
  ((result, _), _) <- runFormPost (abstainForm lang)
  case result of
    FormSuccess (reasonCode, mTextarea)
      | Just reason <- parseAbstentionReason reasonCode -> do
          let note = fmap (T.strip . unTextarea) mTextarea
              notePresent = maybe False (not . T.null) note
              noteRequired = reason `elem` [AmbiguousBetweenLabels, OtherReason]
          if noteRequired && not notePresent
            then do
              setLocalizedMessage lang
                "Для ambiguous_between_labels и other нужен короткий комментарий."
                "A short note is required for ambiguous_between_labels and other."
              redirect (ItemR index)
            else do
              runDB $ update aid
                [ AnnotationAbstentionReason =. Just (abstentionCode reason)
                , AnnotationAbstentionNote =. if notePresent then note else Nothing
                ]
              logEvent sid (Just $ itemId item) "abstention_submitted" (Just $ abstentionCode reason)
              advanceFrom index
    _ -> do
      setLocalizedMessage lang "Выберите причину abstained." "Choose an abstention reason."
      redirect (ItemR index)

postOriginalR :: Int -> Handler Html
postOriginalR index = do
  (sid, session) <- requireSurveySession
  lang <- sessionLanguage session
  item <- itemAt index
  Entity aid _ <- ensureAnnotation sid (itemId item)
  ((result, _), _) <- runFormPost csrfForm
  case result of
    FormSuccess () | shouldOfferOriginal lang item -> do
      runDB $ update aid [AnnotationOriginalRevealed =. True]
      logEvent sid (Just $ itemId item) "original_revealed" Nothing
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
      when (not $ isJust $ surveySessionCompletedAt session) $ do
        runDB $ update sid [SurveySessionCompletedAt =. Just now]
        logEvent sid Nothing "session_completed" Nothing
      defaultLayout [whamlet|
        <section .card>
          <p .eyebrow>Relationship Fix · Haskell/Yesod dogfood
          <h1>#{tr lang "Готово" "Done"}
          <p>#{tr lang "Ответы сохранены в SQLite на сервере. Финальный JSON содержит presentation/source provenance и факт раскрытия оригинала." "Answers are stored in SQLite on the server. The final JSON includes presentation/source provenance and whether the original was revealed."}
          <p><a href=@{SubmissionR} .primary .download>#{tr lang "Скачать submission.json" "Download submission.json"}
      |]

getSubmissionR :: Handler Value
getSubmissionR = do
  (sid, session0) <- requireSurveySession
  incomplete <- firstIncomplete sid
  when (isJust incomplete) $ permissionDenied "submission is incomplete"
  now <- liftIO getCurrentTime
  when (not $ isJust $ surveySessionCompletedAt session0) $
    runDB $ update sid [SurveySessionCompletedAt =. Just now]
  session <- runDB $ getJust sid
  lang <- sessionLanguage session
  annotationValues <- forM items $ \item -> do
    Entity aid annotation <- ensureAnnotation sid (itemId item)
    labels <- loadLabels aid
    evidence <- loadEvidence aid
    let evidenceFor label = lookup label evidence
        presentation = presentationFor lang item
    pure $ object
      [ "item_id" .= itemId item
      , "source_language" .= languageCode (itemSourceLanguage item)
      , "presentation_language" .= languageCode lang
      , "displayed_translation_provenance" .= presentationProvenance presentation
      , "decision" .= annotationDecision annotation
      , "labels" .=
          [ object
              [ "label" .= labelCode label
              , "evidence" .= evidenceFor label
              ]
          | label <- labels
          ]
      , "abstention_reason" .= annotationAbstentionReason annotation
      , "abstention_note" .= annotationAbstentionNote annotation
      , "original_revealed" .= annotationOriginalRevealed annotation
      ]
  addHeader "Content-Disposition" "attachment; filename=relationship-fix-submission.json"
  pure $ object
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
  mRaw <- lookupSession "annotation_session_id"
  case mRaw >>= parseSessionKey of
    Nothing -> redirect HomeR
    Just sid -> do
      mSession <- runDB $ get sid
      case mSession of
        Nothing -> do
          deleteSession "annotation_session_id"
          redirect HomeR
        Just session -> pure (sid, session)

parseSessionKey :: Text -> Maybe SurveySessionId
parseSessionKey raw = case TR.decimal raw of
  Right (n, rest) | T.null rest -> Just $ toSqlKey (n :: Int64)
  _ -> Nothing

sessionLanguage :: SurveySession -> Handler Language
sessionLanguage session = case parseLanguage (surveySessionPresentationLanguage session) of
  Just lang -> pure lang
  Nothing -> permissionDenied "invalid session language"

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
  pure $ catMaybes
    [ (, evidenceQuote value) <$> parseBehaviorLabel (evidenceLabelId value)
    | Entity _ value <- rows
    ]

stepFor :: Annotation -> [BehaviorLabel] -> Step
stepFor annotation labels = case annotationDecision annotation >>= parseDecision of
  Nothing -> StepDecision
  Just NoneObserved -> StepDecision
  Just Abstained -> StepAbstain
  Just Assigned
    | null labels -> StepLabels
    | otherwise -> StepEvidence

annotationComplete :: Annotation -> [BehaviorLabel] -> [(BehaviorLabel, Text)] -> Bool
annotationComplete annotation labels evidence = case annotationDecision annotation >>= parseDecision of
  Nothing -> False
  Just NoneObserved -> True
  Just Abstained -> isJust $ annotationAbstentionReason annotation >>= parseAbstentionReason
  Just Assigned -> not (null labels) && all (`elem` map fst evidence) labels

firstIncomplete :: SurveySessionId -> Handler (Maybe Int)
firstIncomplete sid = go 0 items
  where
    go _ [] = pure Nothing
    go index (item : rest) = do
      Entity aid annotation <- ensureAnnotation sid (itemId item)
      labels <- loadLabels aid
      evidence <- loadEvidence aid
      if annotationComplete annotation labels evidence
        then go (index + 1) rest
        else pure $ Just index

requireDecision :: Decision -> Annotation -> Int -> Handler ()
requireDecision expected annotation index =
  unless (annotationDecision annotation >>= parseDecision == Just expected) $
    redirect (ItemR index)

advanceFrom :: Int -> Handler a
advanceFrom index
  | index + 1 < length items = redirect (ItemR $ index + 1)
  | otherwise = redirect DoneR

setLocalizedMessage :: Language -> Text -> Text -> Handler ()
setLocalizedMessage lang ru en = setMessage $ toHtml $ tr lang ru en

logEvent :: SurveySessionId -> Maybe Text -> Text -> Maybe Text -> Handler ()
logEvent sid itemID kind value = do
  now <- liftIO getCurrentTime
  runDB $ insert_ $ Event sid itemID kind value now

main :: IO ()
main = do
  dbPath <- fromMaybe "annotation.db" <$> lookupEnv "RF_DB_PATH"
  sessionKeyPath <- fromMaybe "client-session-key.aes" <$> lookupEnv "RF_SESSION_KEY_PATH"
  secureCookies <- maybe False (`elem` ["1", "true", "yes"]) <$> lookupEnv "RF_SECURE_COOKIES"
  port <- maybe 8080 (fromMaybe 8080 . readMaybe) <$> lookupEnv "PORT"
  pool <- runStdoutLoggingT $ createSqlitePool (T.pack dbPath) 4
  runSqlPool (runMigration migrateAll) pool
  let app = App pool sessionKeyPath secureCookies
  wai <- toWaiApp app
  runSettings (setPort port $ setHost "127.0.0.1" defaultSettings) wai
