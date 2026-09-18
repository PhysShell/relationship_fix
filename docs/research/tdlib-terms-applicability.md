# TDLIB-0 шаг 1 — применимость условий Telegram

**Я не юрист, и этот документ не заключение.** Это сопоставление дословных цитат
из двух документов Telegram с нашим дизайном плюс перечень вопросов, на которые
текст не отвечает. Решение — ваше и, возможно, юриста.

Прочитано 2026-09-18: [API Terms of Service](https://core.telegram.org/api/terms)
и [Terms of Service for Content Licensing](https://telegram.org/tos/content-licensing).

## 0. Вывод одной строкой

Технически TDLib подходит под `C_target` идеально. **Юридически применимость не
подтверждается, и текст читается скорее против нас, а не нейтрально.** Это
меняет статус C с «основной кандидат, нужен аккаунт» на «основной кандидат,
заблокированный до юридической оценки».

## 1. Четыре разных вопроса, которые постоянно склеивают

```
1  лицензия БИБЛИОТЕКИ        Boost 1.0 — закрыт, разрешает поставку
2  применимость API Terms     кому эти условия адресованы — ОТКРЫТ
3  Content Licensing          разрешена ли ЦЕЛЬ доступа — ОТКРЫТ
4  запрет AI/ML               прямой запрет — ЗАКРЫТ ПРОТИВ НАС
```

Строка 1 не влияет на строки 2–4. Лицензия на код и условия доступа к данным —
разные вещи, и вывод «библиотека пермиссивная → использование разрешено»
механически неверен.

## 2. Кому адресованы API Terms

Преамбула:

> «We welcome all developers to use our API and source code to create
> **Telegram-like messaging applications** on our platform free of charge. In
> order to ensure consistency and security across the Telegram ecosystem, all
> **third-party client apps** must comply with the following Terms of Service.»

§1.3:

> «As a **client developer**, you must make sure that **all the basic features
> of the main Telegram apps function correctly** and in an expected way both in
> your app and when users of your app communicate with other Telegram users.»

Наше приложение — не мессенджер. Отсюда вилка, неприятная с обеих сторон:

```
если мы НЕ client app  →  непонятно, что вообще разрешает нам доступ
если мы client app     →  §1.3 невыполним по построению
```

Ни один из вариантов не даёт «наверное можно».

## 3. Разрешена ли сама ЦЕЛЬ — Content Licensing

Общее правило:

> «Access to user-generated content for **any purpose other than ordinary,
> legitimate, and intended use of the Telegram platform as its user** is
> prohibited.»

Исключение — закрытым перечислением:

> «As a **limited exception**, Telegram permits access to data required to
> launch and operate a legitimate **third-party Telegram Client, Telegram Bot,
> or Telegram Mini App** … Any such data is licensed … **solely to the extent
> strictly required to operate the relevant service**.»

Исследовательский измеритель в перечисление из трёх не входит. И даже внутри
исключения чтение истории ради метрик трудно назвать «strictly required to
operate» клиент: измерение — это не работа клиента, это другая цель.

## 4. AI/ML — здесь текст однозначен, и он против

API Terms §1.5:

> «you are prohibited from using, accessing or aggregating data obtained from
> the Telegram platform to **train, fine-tune or otherwise engage in the
> development, enhancement or deployment of artificial intelligence, machine
> learning models and similar technologies**.»

Content Licensing формулирует шире, добавляя «scraping, indexing, harvesting»,
«validate» и «benchmarking».

Исключение существует, но требовательное:

> «Exceptions may be granted in instances where **all relevant users
> individually** provide **explicit, informed, affirmative and continued
> consent** that is strictly limited to the specific content and chat … consent
> obtained in one context is **non-transferable**.»

**«All relevant users» для диады означает обоих партнёров.** Это ровно то
согласие второго человека, которое prereg §3.1 уже держит открытым — и здесь оно
перестаёт быть этической тонкостью и становится условием доступа.

### Архитектурный firewall — с этого момента, а не «когда дойдём до AI»

```
TDLib acquisition
      ↓
metadata extraction
      ↓
FROZEN deterministic extractor
      ↓
aggregates
      ╳──────  LLM / embeddings / ML
```

Граница обязана действовать **уже на feasibility-спайке**. Разведочный прогон не
должен случайно стать первым AI-путём: так запреты и пересекаются — никем
конкретно, по дороге к другой задаче.

## 5. Что известно и выполнимо, если путь окажется допустим

§2.1–2.4 и §1.1 перечисляют обязательства прямо: собственный `api_id`; факт
использования Telegram API должен быть «featured prominently» для пользователя;
слово «Telegram» в названии запрещено (кроме «Unofficial»); официальный логотип
использовать нельзя; соблюдение Security Guidelines обязательно.

§4: нарушение → уведомление → 10 дней → отключение доступа и обращение в магазины
приложений.

Всё это выполнимо и **не отвечает** на вопросы §2 и §3.

Побочное: раскрытие «приложение использует Telegram API» входит в onboarding, то
есть в `C`, и должно быть учтено в burden budget.

## 6. Ирония, которую стоит записать

Экспортный путь, вероятно, стоит на **более прочном** основании — именно потому,
что действие выполняет человек:

```
watcher:   человек пользуется штатной функцией Telegram как ЕГО ПОЛЬЗОВАТЕЛЬ
           («ordinary, legitimate, and intended use … as its user»)
           и делится своим файлом с нами

TDLib:     наше приложение обращается к платформе само
```

То есть ручной экспорт — не только UX-burden. Возможно, он и есть юридическое
основание. Убирая его, мы переходим из «пользователь выгружает свои данные» в
«стороннее приложение обращается к платформе», и именно этот переход и вызывает
вопросы §2–§3.

Это не аргумент против облегчения `C`. Это указание, что **`C_target` может иметь
потолок, заданный не инженерией.** И тогда вопрос возвращается в
[control-arm memo](control-arm-decision-memo.md): если самый крупный touchpoint
неустраним, контрольная рука остаётся тяжёлой, и это надо признать в интерпретации
null, а не обойти.

## 7. Статус в ledger

`extractor/adapters/telegram_tdlib.py`: **13 свойств — 6 QUALIFIED · 2 PARTIAL ·
4 UNKNOWN · 1 UNAVAILABLE**, открытых допущений **3**.

| свойство | статус |
|---|---|
| `legal.library_license` | **QUALIFIED** — Boost 1.0 |
| `legal.api_terms_app_scope` | **UNKNOWN / блокирует** |
| `legal.content_access_purpose` | **UNKNOWN / блокирует** |
| `legal.ai_use` | **UNAVAILABLE** — запрет прямой |
| `legal.transparency_obligations` | **QUALIFIED** — известны и выполнимы |
| `legal.security_guidelines` | **QUALIFIED** — обязательны |

Два первых — юридическая оценка, тестом не закрывается. Третий закрыт как запрет:
это ответ, а не дыра, и он уже стал ограничением дизайна.

## 8. Порядок

```
1  ToS applicability memo                        ✔ этот документ
2  разделить четыре вопроса                      ✔ §1
3  решить: ясности достаточно / нужен юрист
   или разъяснение от Telegram                   ← ВАШЕ РЕШЕНИЕ
4  только затем api_id и тестовый аккаунт
5  затем проверка разовости авторизации
   и сырой семантики истории
```

Шаги 4–5 не начинаются. Есть ненулевая вероятность, что после нормального
юридического прохода вывод будет «TDLib технически прекрасен, для этого продукта
слишком спорен» — и тогда живой аккаунт окажется отлично выполненной работой над
веткой, которую следовало убить на бумаге.

## 9. Журнал

| дата | что | почему |
|---|---|---|
| 2026-09-18 | Прочитаны оба документа. `legal.ai_use` → **UNAVAILABLE** (прямой запрет, исключение требует согласия ОБОИХ участников диады). Применимость API Terms и Content Licensing → **UNKNOWN, блокирует**. Введён архитектурный firewall, действующий с этапа спайка | Текст адресован «Telegram-like messaging applications», а исключение Content Licensing перечисляет Client/Bot/Mini App закрытым списком и лицензирует данные «solely to the extent strictly required to operate the relevant service». Исследовательский измеритель туда не попадает автоматически. Двадцать минут юридической скуки дешевле недели отличного кода |
