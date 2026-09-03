package catalog

import "github.com/PhysShell/relationship_fix/src/annotation-web/internal/model"

var Labels = []model.Label{
	{ID: "B.BLAME_CRITICISM", DisplayName: map[model.Language]string{model.LanguageRU: "Обвинение / критика", model.LanguageEN: "Blame / criticism"}},
	{ID: "B.PRESSURE_FOR_CHANGE", DisplayName: map[model.Language]string{model.LanguageRU: "Давление с целью изменения", model.LanguageEN: "Pressure for change"}},
	{ID: "B.VALIDATION", DisplayName: map[model.Language]string{model.LanguageRU: "Признание / понимание переживания или позиции", model.LanguageEN: "Validation / substantive acknowledgement"}},
	{ID: "B.REPAIR_ATTEMPT", DisplayName: map[model.Language]string{model.LanguageRU: "Попытка снизить накал / восстановить взаимодействие", model.LanguageEN: "Repair attempt / de-escalation"}},
	{ID: "B.AVOIDANCE_TOPIC_SHIFT", DisplayName: map[model.Language]string{model.LanguageRU: "Уход / смена поднятой темы", model.LanguageEN: "Avoidance / topic shift"}},
}

var Items = []model.Item{
	{
		ID: "dg-04", SourceLanguage: model.LanguageRU,
		Source: []model.Message{{Author: "A", Text: "Я проснулась от холода."}, {Author: "B", Text: "Ты вчера оставил окно открытым, и утром в комнате было холодно.", Target: true}},
		Presentation: map[model.Language]model.Presentation{
			model.LanguageRU: {Context: "Я проснулась от холода.", Target: "Ты вчера оставил окно открытым, и утром в комнате было холодно.", TranslationProvenance: "source"},
			model.LanguageEN: {Context: "I woke up because I was cold.", Target: "You left the window open yesterday, and the room was cold in the morning.", TranslationProvenance: "prototype_mt_v1"},
		},
	},
	{
		ID: "dg-05", SourceLanguage: model.LanguageRU,
		Source: []model.Message{{Author: "A", Text: "Мне было страшно одной ждать результаты обследования."}, {Author: "B", Text: "Понимаю, почему тебе было страшно. Это правда тяжёлое ожидание.", Target: true}},
		Presentation: map[model.Language]model.Presentation{
			model.LanguageRU: {Context: "Мне было страшно одной ждать результаты обследования.", Target: "Понимаю, почему тебе было страшно. Это правда тяжёлое ожидание.", TranslationProvenance: "source"},
			model.LanguageEN: {Context: "I was scared waiting for the test results alone.", Target: "I understand why you were scared. That really is a hard wait.", TranslationProvenance: "prototype_mt_v1"},
		},
	},
	{
		ID: "dg-06", SourceLanguage: model.LanguageRU,
		Source: []model.Message{{Author: "A", Text: "Мы опять кричим друг на друга, это уже никуда не ведёт."}, {Author: "B", Text: "Стоп. Я сейчас злой и говорю лишнее. Давай на час разойдёмся и вернёмся к этому в девять.", Target: true}},
		Presentation: map[model.Language]model.Presentation{
			model.LanguageRU: {Context: "Мы опять кричим друг на друга, это уже никуда не ведёт.", Target: "Стоп. Я сейчас злой и говорю лишнее. Давай на час разойдёмся и вернёмся к этому в девять.", TranslationProvenance: "source"},
			model.LanguageEN: {Context: "We're yelling at each other again; this isn't getting us anywhere.", Target: "Stop. I'm angry right now and saying things I shouldn't. Let's take an hour apart and come back to this at nine.", TranslationProvenance: "prototype_mt_v1"},
		},
	},
	{
		ID: "dg-07", SourceLanguage: model.LanguageRU,
		Source: []model.Message{{Author: "A", Text: "Я случайно купил билеты не на тот день 🤦"}, {Author: "B", Text: "гений планирования 😂❤️ люблю тебя, катастрофа", Target: true}},
		Presentation: map[model.Language]model.Presentation{
			model.LanguageRU: {Context: "Я случайно купил билеты не на тот день 🤦", Target: "гений планирования 😂❤️ люблю тебя, катастрофа", TranslationProvenance: "source"},
			model.LanguageEN: {Context: "I accidentally bought the tickets for the wrong day 🤦", Target: "planning genius 😂❤️ love you, disaster", TranslationProvenance: "prototype_mt_v1"},
		},
	},
	{
		ID: "dg-08", SourceLanguage: model.LanguageRU,
		Source: []model.Message{{Author: "A", Text: "Я опять всё испортил."}, {Author: "B", Text: "Ну ты гений.", Target: true}},
		Presentation: map[model.Language]model.Presentation{
			model.LanguageRU: {Context: "Я опять всё испортил.", Target: "Ну ты гений.", TranslationProvenance: "source"},
			model.LanguageEN: {Context: "I messed everything up again.", Target: "Well, you're a genius.", TranslationProvenance: "prototype_mt_v1"},
		},
	},
	{
		ID: "dg-09", SourceLanguage: model.LanguageRU,
		Source: []model.Message{{Author: "A", Text: "Я опять забыл предупредить, что задержусь."}, {Author: "B", Text: "Я не должна была на тебя орать, прости. Но мне правда нужно, чтобы ты начал писать, когда задерживаешься. Каждый раз.", Target: true}},
		Presentation: map[model.Language]model.Presentation{
			model.LanguageRU: {Context: "Я опять забыл предупредить, что задержусь.", Target: "Я не должна была на тебя орать, прости. Но мне правда нужно, чтобы ты начал писать, когда задерживаешься. Каждый раз.", TranslationProvenance: "source"},
			model.LanguageEN: {Context: "I forgot again to say I'd be late.", Target: "I shouldn't have yelled at you, I'm sorry. But I really need you to start texting me when you're running late. Every time.", TranslationProvenance: "prototype_mt_v1"},
		},
	},
}
