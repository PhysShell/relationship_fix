{-# LANGUAGE OverloadedStrings #-}

-- | The ontology artifact a pilot session is bound to, read for rendering and
-- nothing else.
--
-- The pilot intro page shows the annotator the definitions of the active
-- labels. Those come from the pinned ontology file the issuance record names,
-- verified by hash, not from the hand-written glossary in "Domain" that the
-- dogfood surface uses: what the annotator read has to be the artifact the
-- package manifest pins, or the provenance of the run says one thing and the
-- screen said another.
module Ontology
  ( OntologyLabel (..)
  , OntologyExample (..)
  , parseOntology
  ) where

import qualified Data.Aeson as A
import Data.Aeson.Types (Parser, parseEither, (.:), (.:?), (.!=))
import qualified Data.ByteString as BS
import Data.Text (Text)
import qualified Data.Text as T
import Data.Vector (toList)

data OntologyExample = OntologyExample
  { oeLanguage :: Text
  , oeText :: Text
  , oeVerdict :: Text
  , oeRationale :: Text
  }
  deriving stock (Eq, Show)

data OntologyLabel = OntologyLabel
  { olId :: Text
  , olNameRu :: Text
  , olNameEn :: Text
  , olDefinition :: Text
  , olInclusion :: [Text]
  , olExclusion :: [Text]
  , olExamples :: [OntologyExample]
  }
  deriving stock (Eq, Show)

-- | Parse the ontology file and keep the labels named in @active@, in that
-- order. An active label the file does not define is an error: the manifest
-- and the artifact disagree, and the server is not the place to pick a side.
parseOntology :: [Text] -> BS.ByteString -> Either Text (Text, [OntologyLabel])
parseOntology active raw = do
  value <- either (Left . T.pack) Right (A.eitherDecodeStrict raw)
  (version, labels) <- either (Left . T.pack) Right (parseEither topParser value)
  chosen <- mapM (\wanted -> case [l | l <- labels, olId l == wanted] of
                    (l : _) -> Right l
                    [] -> Left ("ontology does not define active label " <> wanted)) active
  pure (version, chosen)
  where
    topParser :: A.Value -> Parser (Text, [OntologyLabel])
    topParser (A.Object o) = do
      version <- o .: "ontology_version"
      labelsValue <- o .: "labels"
      labels <- case labelsValue of
        A.Array xs -> mapM labelParser (toList xs)
        _ -> fail "labels is not an array"
      pure (version, labels)
    topParser _ = fail "ontology is not an object"
    labelParser :: A.Value -> Parser OntologyLabel
    labelParser (A.Object o) = do
      lid <- o .: "id"
      nameRu <- o .:? "plain_language_name_ru" .!= lid
      nameEn <- o .:? "plain_language_name_en" .!= lid
      definition <- o .:? "operational_definition" .!= ""
      inclusion <- o .:? "inclusion_criteria" .!= []
      exclusion <- o .:? "exclusion_criteria" .!= []
      examplesValue <- o .:? "examples" .!= A.Array mempty
      examples <- case examplesValue of
        A.Array xs -> mapM exampleParser (toList xs)
        _ -> fail "examples is not an array"
      pure OntologyLabel
        { olId = lid, olNameRu = nameRu, olNameEn = nameEn, olDefinition = definition
        , olInclusion = inclusion, olExclusion = exclusion, olExamples = examples }
    labelParser _ = fail "label is not an object"
    exampleParser :: A.Value -> Parser OntologyExample
    exampleParser (A.Object o) =
      OntologyExample
        <$> o .:? "language" .!= ""
        <*> o .: "text"
        <*> o .:? "verdict" .!= ""
        <*> o .:? "rationale" .!= ""
    exampleParser _ = fail "example is not an object"
