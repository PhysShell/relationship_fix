{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Catalog (items)
import Data.List (nub)
import Domain
import Test.Hspec

main :: IO ()
main = hspec $ do
  describe "dogfood catalog" $ do
    it "has unique item ids" $ do
      let ids = map itemId items
      length ids `shouldBe` length (nub ids)

    it "contains both RU and EN presentations for every item" $
      mapM_ (\item -> do
        presentationContext (presentationFor RU item) `shouldNotBe` ""
        presentationTarget (presentationFor RU item) `shouldNotBe` ""
        presentationContext (presentationFor EN item) `shouldNotBe` ""
        presentationTarget (presentationFor EN item) `shouldNotBe` ""
      ) items

  describe "original reveal semantics" $ do
    let russianItem = head items
    it "does not offer original when presentation language equals source" $
      shouldOfferOriginal RU russianItem `shouldBe` False
    it "offers original when a translation is displayed" $
      shouldOfferOriginal EN russianItem `shouldBe` True

  describe "evidence validation" $ do
    let item = head items
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
