{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Catalog (items)
import qualified Data.List as List
import Data.Text (Text)
import qualified Data.Text as T
import Domain
import Test.Hspec

-- | Catalog lookup by stable item id. Tests must not depend on list order.
itemById :: Text -> Item
itemById wanted = case filter ((== wanted) . itemId) items of
  (item : _) -> item
  [] -> error $ "catalog is missing item " <> T.unpack wanted

main :: IO ()
main = hspec $ do
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
