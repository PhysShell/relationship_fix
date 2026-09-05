{-# LANGUAGE OverloadedStrings #-}

-- | Dogfood signal about an item, kept deliberately apart from the annotation.
--
-- Three things a respondent can say are easy to conflate and must not be:
--
--   * an observation label says what the partner did in the excerpt;
--   * an abstention reason says why the excerpt could not be judged;
--   * a feedback flag says the excerpt is a poor instrument.
--
-- Only the first two are annotation. The third is evidence about the item set,
-- which is why it lives in its own module, its own table and its own field of
-- the submission rather than anywhere near 'Domain.BehaviorLabel'.
module Feedback
  ( FeedbackFlag (..)
  , allFeedbackFlags
  , feedbackFlagCode
  , parseFeedbackFlag
  , feedbackFlagName
  ) where

import Data.Text (Text)
import Domain (Language, tr)

data FeedbackFlag
  = UnnaturalExample
  | InsufficientContext
  | WordingOrTranslation
  | OtherFeedback
  deriving stock (Eq, Ord, Show, Read, Enum, Bounded)

allFeedbackFlags :: [FeedbackFlag]
allFeedbackFlags = [minBound .. maxBound]

feedbackFlagCode :: FeedbackFlag -> Text
feedbackFlagCode UnnaturalExample = "unnatural_example"
feedbackFlagCode InsufficientContext = "insufficient_context"
feedbackFlagCode WordingOrTranslation = "wording_or_translation"
feedbackFlagCode OtherFeedback = "other"

parseFeedbackFlag :: Text -> Maybe FeedbackFlag
parseFeedbackFlag "unnatural_example" = Just UnnaturalExample
parseFeedbackFlag "insufficient_context" = Just InsufficientContext
parseFeedbackFlag "wording_or_translation" = Just WordingOrTranslation
parseFeedbackFlag "other" = Just OtherFeedback
parseFeedbackFlag _ = Nothing

feedbackFlagName :: Language -> FeedbackFlag -> Text
feedbackFlagName lang flag = case flag of
  UnnaturalExample -> tr lang "Пример звучит неестественно" "The example sounds unnatural"
  InsufficientContext -> tr lang "Не хватает контекста" "There is not enough context"
  WordingOrTranslation -> tr lang "Формулировка / перевод вызывает вопросы" "The wording or translation raises questions"
  OtherFeedback -> tr lang "Другое" "Something else"
