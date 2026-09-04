{-# LANGUAGE OverloadedStrings #-}

module Domain
  ( Language (..)
  , languageCode
  , parseLanguage
  , tr
  , Decision (..)
  , decisionCode
  , parseDecision
  , BehaviorLabel (..)
  , allBehaviorLabels
  , labelCode
  , parseBehaviorLabel
  , labelName
  , labelDefinition
  , labelExamples
  , AbstentionReason (..)
  , allAbstentionReasons
  , abstentionCode
  , parseAbstentionReason
  , abstentionName
  , abstentionRequiresNote
  , Message (..)
  , Presentation (..)
  , Item (..)
  , presentationFor
  , shouldOfferOriginal
  , EvidenceProblem (..)
  , checkEvidence
  , validEvidence
  ) where

import Data.Text (Text)
import qualified Data.Text as T

data Language = RU | EN
  deriving stock (Eq, Ord, Show, Read, Enum, Bounded)

languageCode :: Language -> Text
languageCode RU = "ru"
languageCode EN = "en"

parseLanguage :: Text -> Maybe Language
parseLanguage "ru" = Just RU
parseLanguage "en" = Just EN
parseLanguage _ = Nothing

tr :: Language -> Text -> Text -> Text
tr RU ru _ = ru
tr EN _ en = en

data Decision
  = Assigned
  | NoneObserved
  | Abstained
  deriving stock (Eq, Ord, Show, Read, Enum, Bounded)

decisionCode :: Decision -> Text
decisionCode Assigned = "assigned"
decisionCode NoneObserved = "none_observed"
decisionCode Abstained = "abstained"

parseDecision :: Text -> Maybe Decision
parseDecision "assigned" = Just Assigned
parseDecision "none_observed" = Just NoneObserved
parseDecision "abstained" = Just Abstained
parseDecision _ = Nothing

data BehaviorLabel
  = BlameCriticism
  | PressureForChange
  | Validation
  | RepairAttempt
  | AvoidanceTopicShift
  deriving stock (Eq, Ord, Show, Read, Enum, Bounded)

allBehaviorLabels :: [BehaviorLabel]
allBehaviorLabels = [minBound .. maxBound]

labelCode :: BehaviorLabel -> Text
labelCode BlameCriticism = "B.BLAME_CRITICISM"
labelCode PressureForChange = "B.PRESSURE_FOR_CHANGE"
labelCode Validation = "B.VALIDATION"
labelCode RepairAttempt = "B.REPAIR_ATTEMPT"
labelCode AvoidanceTopicShift = "B.AVOIDANCE_TOPIC_SHIFT"

parseBehaviorLabel :: Text -> Maybe BehaviorLabel
parseBehaviorLabel "B.BLAME_CRITICISM" = Just BlameCriticism
parseBehaviorLabel "B.PRESSURE_FOR_CHANGE" = Just PressureForChange
parseBehaviorLabel "B.VALIDATION" = Just Validation
parseBehaviorLabel "B.REPAIR_ATTEMPT" = Just RepairAttempt
parseBehaviorLabel "B.AVOIDANCE_TOPIC_SHIFT" = Just AvoidanceTopicShift
parseBehaviorLabel _ = Nothing

labelName :: Language -> BehaviorLabel -> Text
labelName lang label = case label of
  BlameCriticism -> tr lang "обвинение / критика" "blame / criticism"
  PressureForChange -> tr lang "давление с требованием измениться" "pressure demanding change"
  Validation -> tr lang "содержательное признание / понимание переживания или позиции" "substantive acknowledgement / understanding of an experience or position"
  RepairAttempt -> tr lang "попытка снизить накал / восстановить взаимодействие" "attempt to reduce tension / restore interaction"
  AvoidanceTopicShift -> tr lang "уход / смена поднятой темы" "avoiding / shifting the raised topic"

labelDefinition :: Language -> BehaviorLabel -> Text
labelDefinition lang label = case label of
  BlameCriticism -> tr lang
    "Партнёру приписывается вина или негативная характеристика личности/устойчивого паттерна в целом, а не только описывается конкретный эпизод."
    "The partner is assigned blame or a negative characterization of their personality or stable pattern overall, rather than only a concrete episode."
  PressureForChange -> tr lang
    "Настойчивое или повторное требование изменить поведение, давление либо ультиматум."
    "An insistent or repeated demand to change behavior, pressure, or an ultimatum."
  Validation -> tr lang
    "Наблюдаемое признание, понимание или содержательный отклик на чувство, опыт или точку зрения партнёра. Согласие с выводами не обязательно. Важен отклик именно на переживание или позицию, а не просто сигнал о получении сообщения."
    "Observable acknowledgement, understanding, or substantive response to the partner's feeling, experience, or point of view. Agreement with their conclusion is not required. The response must address the experience or position itself, not merely signal receipt of the message."
  RepairAttempt -> tr lang
    "Наблюдаемая попытка изменить негативный ход взаимодействия: взять часть ответственности, извиниться без немедленной контратаки, предложить начать заново, согласованно поставить разговор на паузу или иным способом снизить накал. Кодируется попытка, а не её успех и не предполагаемое внутреннее намерение."
    "An observable attempt to change a negative interaction trajectory: take some responsibility, apologize without an immediate counterattack, suggest starting over, explicitly pause the conversation with a concrete return, or otherwise reduce escalation. Code the attempt, not its success and not an assumed internal intention."
  AvoidanceTopicShift -> tr lang
    "Человек остаётся в разговоре, но наблюдаемо уводит его от только что поднятой темы: переводит разговор на другое без ответа по существу, отшучивается от содержания или неопределённо откладывает обсуждение. Смена темы или пауза сами по себе ещё не являются avoidance."
    "The person stays in the conversation but observably moves away from the topic that was just raised: changes to another topic without addressing it, jokes instead of responding to the substance, or postpones the discussion indefinitely. A topic change or pause alone is not avoidance."

labelExamples :: Language -> BehaviorLabel -> [(Text, Text)]
labelExamples lang label = case label of
  BlameCriticism ->
    [ (yes, tr lang "«Ты всегда обо всём забываешь.»" "“You always forget everything.”")
    , (boundary, tr lang "«ну ты дебил 😂❤️» в явно игровом контексте." "“you idiot 😂❤️” in a clearly playful context.")
    ]
  PressureForChange ->
    [ (yes, tr lang "«Сколько можно повторять — убери за собой, я серьёзно.»" "“How many times do I have to say it — clean up after yourself, I'm serious.”")
    , (no, tr lang "«Можешь завтра забрать посылку?»" "“Can you pick up the parcel tomorrow?”")
    ]
  Validation ->
    [ (yes, tr lang "«Понимаю, звучит обидно, я бы тоже разозлилась.»" "“I understand, that sounds hurtful; I'd be angry too.”")
    , (no, tr lang "«Понятно.» само по себе лишь подтверждает получение сообщения." "“Got it.” by itself only acknowledges receipt of the message.")
    ]
  RepairAttempt ->
    [ (yes, tr lang "«Прости, я правда затупил. Давай сначала?»" "“Sorry, I really messed up. Can we start over?”")
    , (yes, tr lang "«Стоп, мы сейчас только сильнее ругаемся. Давай поедим и вернёмся к этому через час.»" "“Stop, we're only making this worse. Let's eat and come back to it in an hour.”")
    , (no, tr lang "«Извини конечно, но это ты всё начала.»" "“Sorry, sure, but you started all of this.”")
    ]
  AvoidanceTopicShift ->
    [ (yes, tr lang "A: «Нам надо поговорить про кредит». B: «Кстати, видела новый сериал?»" "A: “We need to talk about the loan.” B: “By the way, did you see the new series?”")
    , (no, tr lang "«Давай вечером, сейчас встреча» — есть конкретный возврат к теме." "“Let's talk tonight, I'm in a meeting now.” There is a concrete return to the topic.")
    , (boundary, tr lang "Согласованная деэскалация или пауза с конкретным возвратом может быть repair, а не avoidance." "An agreed de-escalation or a pause with a concrete return can be repair rather than avoidance.")
    ]
  where
    yes = tr lang "Да" "Yes"
    no = tr lang "Нет" "No"
    boundary = tr lang "Граница" "Boundary"

data AbstentionReason
  = InsufficientContext
  | AmbiguousBetweenLabels
  | UnitNotApplicable
  | SourceCorrupted
  | LanguageUnsupported
  | OtherReason
  deriving stock (Eq, Ord, Show, Read, Enum, Bounded)

allAbstentionReasons :: [AbstentionReason]
allAbstentionReasons = [minBound .. maxBound]

abstentionCode :: AbstentionReason -> Text
abstentionCode InsufficientContext = "insufficient_context"
abstentionCode AmbiguousBetweenLabels = "ambiguous_between_labels"
abstentionCode UnitNotApplicable = "unit_not_applicable"
abstentionCode SourceCorrupted = "source_corrupted"
abstentionCode LanguageUnsupported = "language_unsupported"
abstentionCode OtherReason = "other"

parseAbstentionReason :: Text -> Maybe AbstentionReason
parseAbstentionReason "insufficient_context" = Just InsufficientContext
parseAbstentionReason "ambiguous_between_labels" = Just AmbiguousBetweenLabels
parseAbstentionReason "unit_not_applicable" = Just UnitNotApplicable
parseAbstentionReason "source_corrupted" = Just SourceCorrupted
parseAbstentionReason "language_unsupported" = Just LanguageUnsupported
parseAbstentionReason "other" = Just OtherReason
parseAbstentionReason _ = Nothing

abstentionName :: Language -> AbstentionReason -> Text
abstentionName lang reason = case reason of
  InsufficientContext -> tr lang "Недостаточно контекста" "Insufficient context"
  AmbiguousBetweenLabels -> tr lang "Неоднозначно между категориями" "Ambiguous between labels"
  UnitNotApplicable -> tr lang "Категория неприменима к этой единице анализа" "Unit not applicable"
  SourceCorrupted -> tr lang "Источник повреждён" "Source corrupted"
  LanguageUnsupported -> tr lang "Язык не поддерживается" "Language unsupported"
  OtherReason -> tr lang "Другая причина" "Other"

-- | Reasons that are meaningless without a note: both say "the categories or
-- the unit were the problem" without saying how, which is unusable in
-- adjudication unless the annotator writes it down.
abstentionRequiresNote :: AbstentionReason -> Bool
abstentionRequiresNote AmbiguousBetweenLabels = True
abstentionRequiresNote OtherReason = True
abstentionRequiresNote _ = False

data Message = Message
  { messageAuthor :: Text
  , messageText :: Text
  , messageTarget :: Bool
  }
  deriving stock (Eq, Show)

data Presentation = Presentation
  { presentationContext :: Text
  , presentationTarget :: Text
  , presentationProvenance :: Text
  }
  deriving stock (Eq, Show)

data Item = Item
  { itemId :: Text
  , itemSourceLanguage :: Language
  , itemSource :: [Message]
  , itemPresentationRU :: Presentation
  , itemPresentationEN :: Presentation
  }
  deriving stock (Eq, Show)

presentationFor :: Language -> Item -> Presentation
presentationFor RU = itemPresentationRU
presentationFor EN = itemPresentationEN

shouldOfferOriginal :: Language -> Item -> Bool
shouldOfferOriginal lang item = itemSourceLanguage item /= lang

-- | Why a submitted evidence quote was not usable.
--
-- The two are worth telling apart when reporting back: an empty box is a
-- respondent who has not answered yet, while a quote that is not a span is a
-- respondent who answered and was wrong about what they were shown.
data EvidenceProblem
  = EvidenceBlank
  | EvidenceNotASpan
  deriving stock (Eq, Ord, Show)

-- | Check a submitted quote against the message as it was displayed, returning
-- the normalised quote when it is usable.
--
-- Note that this is a question about the presentation and not about the
-- source: the same quote is a valid span of a Russian presentation of a
-- Russian item and is not a span of its English translation.
checkEvidence :: Language -> Item -> Text -> Either EvidenceProblem Text
checkEvidence lang item raw
  | T.null quote = Left EvidenceBlank
  | quote `T.isInfixOf` target = Right quote
  | otherwise = Left EvidenceNotASpan
  where
    quote = T.strip raw
    target = presentationTarget (presentationFor lang item)

validEvidence :: Language -> Item -> Text -> Bool
validEvidence lang item raw = case checkEvidence lang item raw of
  Right _ -> True
  Left _ -> False
