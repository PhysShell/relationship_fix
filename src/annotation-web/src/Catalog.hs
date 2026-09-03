{-# LANGUAGE OverloadedStrings #-}

module Catalog
  ( items
  ) where

import Domain

items :: [Item]
items =
  [ Item
      { itemId = "dg-04"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Я проснулась от холода." False
          , Message "B" "Ты вчера оставил окно открытым, и утром в комнате было холодно." True
          ]
      , itemPresentationRU = Presentation
          "Я проснулась от холода."
          "Ты вчера оставил окно открытым, и утром в комнате было холодно."
          "source"
      , itemPresentationEN = Presentation
          "I woke up because I was cold."
          "You left the window open yesterday, and the room was cold in the morning."
          "prototype_mt_v1"
      }
  , Item
      { itemId = "dg-05"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Мне было страшно одной ждать результаты обследования." False
          , Message "B" "Понимаю, почему тебе было страшно. Это правда тяжёлое ожидание." True
          ]
      , itemPresentationRU = Presentation
          "Мне было страшно одной ждать результаты обследования."
          "Понимаю, почему тебе было страшно. Это правда тяжёлое ожидание."
          "source"
      , itemPresentationEN = Presentation
          "I was scared waiting for the test results alone."
          "I understand why you were scared. That really is a hard wait."
          "prototype_mt_v1"
      }
  , Item
      { itemId = "dg-06"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Мы опять кричим друг на друга, это уже никуда не ведёт." False
          , Message "B" "Стоп. Я сейчас злой и говорю лишнее. Давай на час разойдёмся и вернёмся к этому в девять." True
          ]
      , itemPresentationRU = Presentation
          "Мы опять кричим друг на друга, это уже никуда не ведёт."
          "Стоп. Я сейчас злой и говорю лишнее. Давай на час разойдёмся и вернёмся к этому в девять."
          "source"
      , itemPresentationEN = Presentation
          "We're yelling at each other again; this isn't getting us anywhere."
          "Stop. I'm angry right now and saying things I shouldn't. Let's take an hour apart and come back to this at nine."
          "prototype_mt_v1"
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
      { itemId = "dg-09"
      , itemSourceLanguage = RU
      , itemSource =
          [ Message "A" "Я опять забыл предупредить, что задержусь." False
          , Message "B" "Я не должна была на тебя орать, прости. Но мне правда нужно, чтобы ты начал писать, когда задерживаешься. Каждый раз." True
          ]
      , itemPresentationRU = Presentation
          "Я опять забыл предупредить, что задержусь."
          "Я не должна была на тебя орать, прости. Но мне правда нужно, чтобы ты начал писать, когда задерживаешься. Каждый раз."
          "source"
      , itemPresentationEN = Presentation
          "I forgot again to say I'd be late."
          "I shouldn't have yelled at you, I'm sorry. But I really need you to start texting me when you're running late. Every time."
          "prototype_mt_v1"
      }
  ]
