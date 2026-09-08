{-# LANGUAGE OverloadedStrings #-}

-- | The dogfood catalog: annotation-ux-v7, the debug surface.
--
-- Source texts here are the RU messages of data/pilot/v0.1/form/dogfood-v7-items.yaml,
-- byte for byte; research/python/tests/test_catalog_dogfood.py checks that.
-- This is not where pilot stimuli come from: a pilot session renders its
-- sealed presentation packet and never consults this module.
--
-- EN presentations are translations and say so in their provenance string:
-- "prototype_mt_v1" for the lines that were translated for the v6 prototype,
-- "llm_translation_2026-09-08" for the lines that changed in v7. Nothing
-- scientific depends on them.
module Catalog
  ( items
  ) where

import Domain

items :: [Item]
items =
  [ Item
      { itemId = "dg-10"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Я ночью так замёрзла, кошмар." False
          , Message "B" "Ну так вентилятор всю ночь работал, ты его не выключила." True
          ]
      , itemPresentationRU = Presentation
          "Я ночью так замёрзла, кошмар."
          "Ну так вентилятор всю ночь работал, ты его не выключила."
          "source"
      , itemPresentationEN = Presentation
          "I was so cold last night, it was awful."
          "Well, the fan was running all night, you didn't turn it off."
          "llm_translation_2026-09-08"
      }
  , Item
      { itemId = "dg-05"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Мне было страшно одной ждать результаты обследования." False
          , Message "B" "Одной такое ждать — ещё бы не страшно. Там любой бы дёргался." True
          ]
      , itemPresentationRU = Presentation
          "Мне было страшно одной ждать результаты обследования."
          "Одной такое ждать — ещё бы не страшно. Там любой бы дёргался."
          "source"
      , itemPresentationEN = Presentation
          "I was scared waiting for the test results alone."
          "Waiting for something like that on your own — no wonder it was scary. Anyone would have been on edge."
          "context: prototype_mt_v1; target: llm_translation_2026-09-08"
      }
  , Item
      { itemId = "dg-06"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Мы опять кричим друг на друга, это уже никуда не ведёт." False
          , Message "B" "Стоп. Я злой сейчас, наговорю. Давай час, ну давай — я пройдусь, в девять вернусь, и нормально поговорим." True
          ]
      , itemPresentationRU = Presentation
          "Мы опять кричим друг на друга, это уже никуда не ведёт."
          "Стоп. Я злой сейчас, наговорю. Давай час, ну давай — я пройдусь, в девять вернусь, и нормально поговорим."
          "source"
      , itemPresentationEN = Presentation
          "We're yelling at each other again; this isn't getting us anywhere."
          "Stop. I'm angry right now, I'll say too much. Give me an hour, come on — I'll take a walk, be back at nine, and we'll talk properly."
          "context: prototype_mt_v1; target: llm_translation_2026-09-08"
      }
  , Item
      { itemId = "dg-07"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Я случайно купил билеты не на тот день 🤦" False
          , Message "B" "гений планирования 😂❤️ люблю тебя, катастрофа" True
          ]
      , itemPresentationRU = Presentation
          "Я случайно купил билеты не на тот день 🤦"
          "гений планирования 😂❤️ люблю тебя, катастрофа"
          "source"
      , itemPresentationEN = Presentation
          "I accidentally bought the tickets for the wrong day 🤦"
          "planning genius 😂❤️ love you, disaster"
          "prototype_mt_v1"
      }
  , Item
      { itemId = "dg-08"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Я опять всё испортил." False
          , Message "B" "Ну ты гений." True
          ]
      , itemPresentationRU = Presentation
          "Я опять всё испортил."
          "Ну ты гений."
          "source"
      , itemPresentationEN = Presentation
          "I messed everything up again."
          "Well, you're a genius."
          "prototype_mt_v1"
      }
  , Item
      { itemId = "dg-11"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Ну да, перевод забыл. Знаю." False
          , Message "B" "Ладно, орать я зря начала. Но поставь ты уже напоминалку на первое число, чтобы мне каждый месяц не писать." True
          ]
      , itemPresentationRU = Presentation
          "Ну да, перевод забыл. Знаю."
          "Ладно, орать я зря начала. Но поставь ты уже напоминалку на первое число, чтобы мне каждый месяц не писать."
          "source"
      , itemPresentationEN = Presentation
          "Yeah, I forgot the transfer. I know."
          "Okay, I shouldn't have started yelling. But set yourself a reminder for the first of the month already, so I don't have to text you every month."
          "llm_translation_2026-09-08"
      }
  ]
