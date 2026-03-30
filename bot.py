import logging
import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# =========================================================
# Telegram bot for practicing German articles
# Stack: python-telegram-bot v22+
# Run:
#   1) pip3 install python-telegram-bot==22.5
#   2) export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
#   3) python3 bot.py
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# DATA MODEL
# ─────────────────────────────────────────────────────────

@dataclass
class Exercise:
    template: str  # "Ich sehe ▢ Hund."
    answer: str    # correct form, e.g. "den"
    case: str      # "Nominativ" / "Akkusativ" / "Dativ"


@dataclass
class Card:
    word: str
    article: str
    translation: str
    topic: str
    plural: str
    semantic: str   # meaning-based explanation
    morpho: str     # ending/suffix rule
    historic: str   # etymology
    exercises: List[Exercise] = field(default_factory=list)


# ─────────────────────────────────────────────────────────
# WORD DATABASE
# ─────────────────────────────────────────────────────────

CARDS: List[Card] = [

    # ══════ ALLTAG ══════

    Card(
        word="Tisch", article="der", translation="стол",
        topic="Alltag", plural="Tische",
        semantic="🧠 *Семантика:* Мебель без явного «женского» или «нейтрального» признака часто мужского рода: *der Stuhl, der Tisch, der Schrank*.",
        morpho="📐 *Морфология:* Односложное слово на согласную без суффиксов → чаще мужской. Мн.ч.: *Tische* (+e).",
        historic="📜 *История:* От лат. *discus* (диск, блюдо) → *tisk → Tisch*. Изначально «доска для еды». Родственно англ. *dish*.",
        exercises=[
            Exercise("▢ Tisch ist groß.", "Der", "Nominativ"),
            Exercise("Ich kaufe ▢ Tisch.", "einen", "Akkusativ"),
            Exercise("Das Buch liegt auf ▢ Tisch.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Lampe", article="die", translation="лампа",
        topic="Alltag", plural="Lampen",
        semantic="🧠 *Семантика:* Предметы освещения и бытовые приборы часто женского рода: *die Lampe, die Kerze, die Uhr*.",
        morpho="📐 *Морфология:* Окончание *-e* → женский род в ~90% случаев. Одно из самых надёжных правил! Мн.ч.: *Lampen* (+n).",
        historic="📜 *История:* Из греч. *lampas* (факел, светильник) через лат. *lampada*. Пришло во все европейские языки.",
        exercises=[
            Exercise("▢ Lampe ist kaputt.", "Die", "Nominativ"),
            Exercise("Ich kaufe ▢ Lampe.", "eine", "Akkusativ"),
            Exercise("Das Zimmer ist dank ▢ Lampe hell.", "der", "Dativ"),
        ],
    ),

    Card(
        word="Fenster", article="das", translation="окно",
        topic="Alltag", plural="Fenster",
        semantic="🧠 *Семантика:* Строительные элементы-«проёмы» часто среднего рода: *das Fenster, das Dach, das Tor*.",
        morpho="📐 *Морфология:* Слова на *-er* среднего рода часто имеют нулевое множественное число. Мн.ч.: *Fenster* (без изменений).",
        historic="📜 *История:* От лат. *fenestra* (окно, отверстие). В рус. «окно» от «ока» (глаз) — интересный параллелизм: окно = «глаз дома».",
        exercises=[
            Exercise("▢ Fenster ist offen.", "Das", "Nominativ"),
            Exercise("Ich öffne ▢ Fenster.", "das", "Akkusativ"),
            Exercise("Die Luft kommt durch ▢ Fenster.", "das", "Akkusativ"),
        ],
    ),

    Card(
        word="Stuhl", article="der", translation="стул",
        topic="Alltag", plural="Stühle",
        semantic="🧠 *Семантика:* Мебель для сидения мужского рода: *der Stuhl, der Sessel, der Hocker*. Исключение: *das Sofa*.",
        morpho="📐 *Морфология:* Односложное слово на согласную → часто мужской. Мн.ч. с умлаутом: *Stühle*.",
        historic="📜 *История:* От германского *stōla* — «место для сидения». Родственно рус. *стол* и англ. *stool*. Изначально означало трон.",
        exercises=[
            Exercise("▢ Stuhl ist bequem.", "Der", "Nominativ"),
            Exercise("Ich nehme ▢ Stuhl.", "den", "Akkusativ"),
            Exercise("Ich sitze auf ▢ Stuhl.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Tasche", article="die", translation="сумка",
        topic="Alltag", plural="Taschen",
        semantic="🧠 *Семантика:* Ёмкости для личных вещей часто женского рода: *die Tasche, die Tüte, die Box*.",
        morpho="📐 *Морфология:* Окончание *-e* → женский. Мн.ч.: *Taschen* (+n).",
        historic="📜 *История:* От средневерхненем. *tasche* — «карман». Родственно итал. *tasca*. Вероятно из арабского через торговые пути.",
        exercises=[
            Exercise("▢ Tasche ist schwer.", "Die", "Nominativ"),
            Exercise("Ich trage ▢ Tasche.", "die", "Akkusativ"),
            Exercise("Der Schlüssel ist in ▢ Tasche.", "der", "Dativ"),
        ],
    ),

    Card(
        word="Buch", article="das", translation="книга",
        topic="Alltag", plural="Bücher",
        semantic="🧠 *Семантика:* Носители информации: *das Buch, das Heft, das Magazin* — часто средний род.",
        morpho="📐 *Морфология:* Слова на *-uch* → почти всегда средний: *das Buch, das Tuch, das Fach*. Мн.ч.: *Bücher* (умлаут + -er).",
        historic="📜 *История:* От германского *bōk-* — «буковое дерево». Германцы вырезали руны на буковых дощечках. Родственно англ. *book*.",
        exercises=[
            Exercise("▢ Buch ist interessant.", "Das", "Nominativ"),
            Exercise("Ich lese ▢ Buch.", "das", "Akkusativ"),
            Exercise("Ich lerne aus ▢ Buch.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Schlüssel", article="der", translation="ключ",
        topic="Alltag", plural="Schlüssel",
        semantic="🧠 *Семантика:* Инструменты с функцией воздействия — мужского рода: *der Schlüssel, der Hammer, der Stift*.",
        morpho="📐 *Морфология:* Слова на *-el* → чаще мужской: *der Schlüssel, der Mantel, der Spiegel*. Мн.ч. без изменений.",
        historic="📜 *История:* От *schließen* (закрывать) + *-el*. Буквально — «то, чем закрывают». Тот же корень в *Schloss* (замок/дворец).",
        exercises=[
            Exercise("▢ Schlüssel liegt auf dem Tisch.", "Der", "Nominativ"),
            Exercise("Ich suche ▢ Schlüssel.", "den", "Akkusativ"),
            Exercise("Mit ▢ Schlüssel öffne ich die Tür.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Uhr", article="die", translation="часы",
        topic="Alltag", plural="Uhren",
        semantic="🧠 *Семантика:* Измерительные приборы нередко женского рода: *die Uhr, die Waage, die Bremse*.",
        morpho="📐 *Морфология:* Исторически женский род, нужно запомнить. Мн.ч.: *Uhren* (+en).",
        historic="📜 *История:* От лат. *hora* (час) через *ore → Uhr*. Родственно рус. «урок» и «час» (через другой путь).",
        exercises=[
            Exercise("▢ Uhr ist kaputt.", "Die", "Nominativ"),
            Exercise("Ich kaufe ▢ Uhr.", "eine", "Akkusativ"),
            Exercise("Ich schaue auf ▢ Uhr.", "die", "Akkusativ"),
        ],
    ),

    # ══════ ESSEN ══════

    Card(
        word="Kaffee", article="der", translation="кофе",
        topic="Essen", plural="(nur Sg.)",
        semantic="🧠 *Семантика:* Напитки — мужского рода: *der Kaffee, der Tee, der Saft, der Wein*. Запомни как группу!",
        morpho="📐 *Морфология:* Двойное *-ee* — сигнал заимствования. Напитки-заимствования почти всегда мужского рода.",
        historic="📜 *История:* Из тур. *kahve* → арабск. *qahwa*. В Европу попал через Османскую империю в XVI–XVII вв. Первые кофейни — в Вене и Гамбурге.",
        exercises=[
            Exercise("▢ Kaffee ist heiß.", "Der", "Nominativ"),
            Exercise("Ich trinke ▢ Kaffee.", "den", "Akkusativ"),
            Exercise("Mit ▢ Kaffee fange ich den Tag an.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Suppe", article="die", translation="суп",
        topic="Essen", plural="Suppen",
        semantic="🧠 *Семантика:* Жидкие блюда — женского рода: *die Suppe, die Soße, die Brühe*.",
        morpho="📐 *Морфология:* Окончание *-e* → женский. Мн.ч.: *Suppen* (+n).",
        historic="📜 *История:* От старофранц. *soupe* — «хлеб, намоченный в бульоне». Родственно англ. *soup*. В средние века суп ели, обмакивая хлеб.",
        exercises=[
            Exercise("▢ Suppe ist lecker.", "Die", "Nominativ"),
            Exercise("Ich koche ▢ Suppe.", "eine", "Akkusativ"),
            Exercise("Das Brot passt gut zu ▢ Suppe.", "der", "Dativ"),
        ],
    ),

    Card(
        word="Brot", article="das", translation="хлеб",
        topic="Essen", plural="Brote",
        semantic="🧠 *Семантика:* Основные продукты питания: *das Brot, das Brötchen, das Müsli* — часто средний.",
        morpho="📐 *Морфология:* Слово на *-t*, без «женских» или специальных суффиксов — исторически средний. Мн.ч.: *Brote* (+e).",
        historic="📜 *История:* Германский корень *braudą* — «заквашенный хлеб». Родственно англ. *bread*. Рус. «хлеб» — из готск. *hlaifs* (другой путь).",
        exercises=[
            Exercise("▢ Brot ist frisch.", "Das", "Nominativ"),
            Exercise("Ich esse ▢ Brot.", "das", "Akkusativ"),
            Exercise("Zum Frühstück greife ich nach ▢ Brot.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Apfel", article="der", translation="яблоко",
        topic="Essen", plural="Äpfel",
        semantic="🧠 *Семантика:* Круглые фрукты с косточкой — запомни группой: *der Apfel, der Pfirsich* (мужской) vs. *die Birne, die Pflaume* (женский).",
        morpho="📐 *Морфология:* Слова на *-el* → чаще мужской: *der Apfel, der Mantel, der Gürtel*. Мн.ч.: *Äpfel* (умлаут).",
        historic="📜 *История:* Германский корень *aplaz* — одно из древнейших слов. Родственно рус. «яблоко» и лат. *Abella* (итальянский город яблок).",
        exercises=[
            Exercise("▢ Apfel ist rot.", "Der", "Nominativ"),
            Exercise("Ich esse ▢ Apfel.", "einen", "Akkusativ"),
            Exercise("Der Saft kommt aus ▢ Apfel.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Tomate", article="die", translation="помидор",
        topic="Essen", plural="Tomaten",
        semantic="🧠 *Семантика:* Овощи на *-e* — женского рода: *die Tomate, die Kartoffel, die Zwiebel, die Gurke*.",
        morpho="📐 *Морфология:* Окончание *-e* → женский. Почти без исключений. Мн.ч.: *Tomaten* (+n).",
        historic="📜 *История:* Из нахуатльского *tomatl* через испанский. В Европу привезли из Америки в XVI в. Долго считали ядовитыми.",
        exercises=[
            Exercise("▢ Tomate ist reif.", "Die", "Nominativ"),
            Exercise("Ich kaufe ▢ Tomate.", "eine", "Akkusativ"),
            Exercise("Der Salat wird mit ▢ Tomate gemacht.", "der", "Dativ"),
        ],
    ),

    Card(
        word="Ei", article="das", translation="яйцо",
        topic="Essen", plural="Eier",
        semantic="🧠 *Семантика:* Животные продукты без явной формы: *das Ei, das Fleisch, das Fett* — часто средний.",
        morpho="📐 *Морфология:* Очень короткое слово — нужно запомнить. Мн.ч.: *Eier* (+er, без умлаута).",
        historic="📜 *История:* Германский корень *ajją*. Родственно рус. «яйцо», лат. *ovum*, греч. *ōón*. Один из древнейших праиндоевропейских корней.",
        exercises=[
            Exercise("▢ Ei ist frisch.", "Das", "Nominativ"),
            Exercise("Ich koche ▢ Ei.", "ein", "Akkusativ"),
            Exercise("Mit ▢ Ei macht man Kuchen.", "einem", "Dativ"),
        ],
    ),

    Card(
        word="Milch", article="die", translation="молоко",
        topic="Essen", plural="(nur Sg.)",
        semantic="🧠 *Семантика:* Молочные продукты — женского рода: *die Milch, die Butter, die Sahne*.",
        morpho="📐 *Морфология:* Слово на *-ch* — нет чёткого правила, нужно запомнить. Только ед.ч.",
        historic="📜 *История:* Германский корень *meluks*. Родственно рус. «молоко», лат. *mulgere* (доить), греч. *amelgō*.",
        exercises=[
            Exercise("▢ Milch ist kalt.", "Die", "Nominativ"),
            Exercise("Ich trinke ▢ Milch.", "die", "Akkusativ"),
            Exercise("Der Kaffee wird mit ▢ Milch getrunken.", "der", "Dativ"),
        ],
    ),

    # ══════ MENSCHEN ══════

    Card(
        word="Lehrer", article="der", translation="учитель",
        topic="Menschen", plural="Lehrer",
        semantic="🧠 *Семантика:* Профессии с суффиксом *-er* для мужчин → мужской. Женская форма: *die Lehrerin*.",
        morpho="📐 *Морфология:* Суффикс *-er* (агенс) → мужской: *der Lehrer, der Fahrer, der Bäcker*. Мн.ч. без изменений.",
        historic="📜 *История:* От *lehren* (учить) + *-er*. *Lehren* из германского *laizjan* — «следовать по следу, указывать путь». Знание как «след».",
        exercises=[
            Exercise("▢ Lehrer erklärt das gut.", "Der", "Nominativ"),
            Exercise("Ich frage ▢ Lehrer.", "den", "Akkusativ"),
            Exercise("Ich danke ▢ Lehrer.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Studentin", article="die", translation="студентка",
        topic="Menschen", plural="Studentinnen",
        semantic="🧠 *Семантика:* Суффикс *-in* обозначает женщину → всегда женский род.",
        morpho="📐 *Морфология:* Суффикс *-in* → 100% женский. Мн.ч.: *-innen*. Примеры: *die Ärztin, die Lehrerin, die Freundin*.",
        historic="📜 *История:* *Student* из лат. *studere* (стараться, учиться). Суффикс *-in* — исконно германский способ образования женского рода.",
        exercises=[
            Exercise("▢ Studentin lernt viel.", "Die", "Nominativ"),
            Exercise("Ich kenne ▢ Studentin.", "die", "Akkusativ"),
            Exercise("Ich helfe ▢ Studentin.", "der", "Dativ"),
        ],
    ),

    Card(
        word="Kind", article="das", translation="ребёнок",
        topic="Menschen", plural="Kinder",
        semantic="🧠 *Семантика:* Слова для детей без гендерного маркера — средний: *das Kind, das Baby, das Mädchen*.",
        morpho="📐 *Морфология:* Мн.ч. с *-er*: *Kinder*. Типичный паттерн для односложных слов среднего рода.",
        historic="📜 *История:* Германский корень *kinda-* — «потомство». Родственно англ. *kin* (родственники). Отсюда *Kindergarten* (сад детей).",
        exercises=[
            Exercise("▢ Kind spielt draußen.", "Das", "Nominativ"),
            Exercise("Ich sehe ▢ Kind.", "das", "Akkusativ"),
            Exercise("Ich lese ▢ Kind eine Geschichte vor.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Arzt", article="der", translation="врач",
        topic="Menschen", plural="Ärzte",
        semantic="🧠 *Семантика:* Профессии для мужчин — мужского рода. Пара: *der Arzt / die Ärztin*.",
        morpho="📐 *Морфология:* Слово на согласную, без суффиксов → мужской. Мн.ч. с умлаутом: *Ärzte*.",
        historic="📜 *История:* Из греч. *arkhiatros* (главный врач) через лат. *archiater*. В средние века сократилось до *arzāt → Arzt*.",
        exercises=[
            Exercise("▢ Arzt ist freundlich.", "Der", "Nominativ"),
            Exercise("Ich besuche ▢ Arzt.", "den", "Akkusativ"),
            Exercise("Ich vertraue ▢ Arzt.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Freundin", article="die", translation="подруга / девушка",
        topic="Menschen", plural="Freundinnen",
        semantic="🧠 *Семантика:* Суффикс *-in* → всегда женский. *die Freundin* — подруга или романтическая партнёрша.",
        morpho="📐 *Морфология:* *Freund* (мужской) + *-in* = *Freundin* (женский). Мн.ч.: *Freundinnen*.",
        historic="📜 *История:* От германского *frijōnd* — «любящий, дорогой». Родственно праиндоевроп. корню *preyH-* (любить), откуда рус. «свободный».",
        exercises=[
            Exercise("▢ Freundin ruft mich an.", "Die", "Nominativ"),
            Exercise("Ich besuche ▢ Freundin.", "die", "Akkusativ"),
            Exercise("Ich schreibe ▢ Freundin eine Nachricht.", "der", "Dativ"),
        ],
    ),

    Card(
        word="Baby", article="das", translation="младенец",
        topic="Menschen", plural="Babys",
        semantic="🧠 *Семантика:* Международные слова для маленьких детей — средний: *das Baby, das Kind*.",
        morpho="📐 *Морфология:* Слова на *-y* (заимствования) → средний: *das Baby, das Hobby, das Handy*. Мн.ч.: *Babys* (+s).",
        historic="📜 *История:* Английское *baby* — звукоподражательное слово из детской речи. Вошло в немецкий через американскую культуру XX в.",
        exercises=[
            Exercise("▢ Baby schläft.", "Das", "Nominativ"),
            Exercise("Ich halte ▢ Baby.", "das", "Akkusativ"),
            Exercise("Ich singe ▢ Baby ein Lied.", "dem", "Dativ"),
        ],
    ),

    # ══════ STADT ══════

    Card(
        word="Zug", article="der", translation="поезд",
        topic="Stadt", plural="Züge",
        semantic="🧠 *Семантика:* Наземный транспорт — мужского рода: *der Zug, der Bus, der Wagen*. Исключение: *das Auto, das Flugzeug*.",
        morpho="📐 *Морфология:* Слово на согласную, односложное → мужской. Мн.ч. с умлаутом: *Züge*.",
        historic="📜 *История:* От *ziehen* (тянуть). Поезд — то, что тянет или тянется. Родственно рус. «тяга» и англ. *tug*.",
        exercises=[
            Exercise("▢ Zug kommt pünktlich.", "Der", "Nominativ"),
            Exercise("Ich nehme ▢ Zug.", "den", "Akkusativ"),
            Exercise("Ich fahre mit ▢ Zug.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Straße", article="die", translation="улица",
        topic="Stadt", plural="Straßen",
        semantic="🧠 *Семантика:* Пути и дороги — женского рода: *die Straße, die Allee, die Gasse*.",
        morpho="📐 *Морфология:* Окончание *-e* → женский. Мн.ч.: *Straßen*.",
        historic="📜 *История:* Из лат. *via strata* — «вымощенная дорога». *Strata* от *sternere* (мостить). Отсюда же англ. *street*.",
        exercises=[
            Exercise("▢ Straße ist lang.", "Die", "Nominativ"),
            Exercise("Ich überquere ▢ Straße.", "die", "Akkusativ"),
            Exercise("Am Ende ▢ Straße ist die Post.", "der", "Genitiv"),
        ],
    ),

    Card(
        word="Auto", article="das", translation="машина",
        topic="Stadt", plural="Autos",
        semantic="🧠 *Семантика:* Технические заимствования на *-o* — средний: *das Auto, das Radio, das Foto, das Kino*.",
        morpho="📐 *Морфология:* Окончание *-o* у заимствований → средний. Мн.ч.: *Autos* (+s).",
        historic="📜 *История:* Сокращение от *Automobil* = греч. *autos* (сам) + лат. *mobilis* (подвижный). «Самодвижущийся» — первое название машин.",
        exercises=[
            Exercise("▢ Auto ist neu.", "Das", "Nominativ"),
            Exercise("Ich kaufe ▢ Auto.", "ein", "Akkusativ"),
            Exercise("Ich fahre mit ▢ Auto.", "dem", "Dativ"),
        ],
    ),

    Card(
        word="Bahnhof", article="der", translation="вокзал",
        topic="Stadt", plural="Bahnhöfe",
        semantic="🧠 *Семантика:* Главное правило сложных слов: род = род *последней части*. *der Hof* → *der Bahn**hof***.",
        morpho="📐 *Морфология:* *Bahn + Hof → der Bahnhof*. Это правило работает всегда: *der Handschuh, das Schlafzimmer, die Bahnfahrt*.",
        historic="📜 *История:* *Bahn* (дорога) + *Hof* (двор). Первые вокзалы строились как большие дворы. Рус. «вокзал» — из лондонского Vauxhall.",
        exercises=[
            Exercise("▢ Bahnhof ist groß.", "Der", "Nominativ"),
            Exercise("Ich suche ▢ Bahnhof.", "den", "Akkusativ"),
            Exercise("Ich warte am ▢ Bahnhof.", "Bahnhof (am = an dem)", "Dativ"),
        ],
    ),

    Card(
        word="Brücke", article="die", translation="мост",
        topic="Stadt", plural="Brücken",
        semantic="🧠 *Семантика:* Инфраструктурные сооружения — женского рода: *die Brücke, die Mauer, die Treppe*.",
        morpho="📐 *Морфология:* Окончание *-e* → женский. Мн.ч.: *Brücken* (+n).",
        historic="📜 *История:* От германского *brugjō* — «бревно через ручей». Родственно англ. *bridge*. Изначально — просто бревно над водой.",
        exercises=[
            Exercise("▢ Brücke ist alt.", "Die", "Nominativ"),
            Exercise("Wir überqueren ▢ Brücke.", "die", "Akkusativ"),
            Exercise("Auf ▢ Brücke ist viel Verkehr.", "der", "Dativ"),
        ],
    ),

    Card(
        word="Museum", article="das", translation="музей",
        topic="Stadt", plural="Museen",
        semantic="🧠 *Семантика:* Слова латинского происхождения на *-um* → средний: *das Museum, das Zentrum, das Datum, das Stadium*.",
        morpho="📐 *Морфология:* Суффикс *-um* → средний. Мн.ч. *-um → -en*: *Museen*.",
        historic="📜 *История:* Из греч. *mouseion* — храм муз. Александрийский мусейон был местом учёных собраний, а не выставок.",
        exercises=[
            Exercise("▢ Museum ist interessant.", "Das", "Nominativ"),
            Exercise("Ich besuche ▢ Museum.", "das", "Akkusativ"),
            Exercise("Im Museum gibt es viele Kunstwerke.", "dem (im = in dem)", "Dativ"),
        ],
    ),

    Card(
        word="Schule", article="die", translation="школа",
        topic="Stadt", plural="Schulen",
        semantic="🧠 *Семантика:* Учебные заведения — женского рода: *die Schule, die Universität, die Bibliothek*.",
        morpho="📐 *Морфология:* Окончание *-e* → женский. Мн.ч.: *Schulen* (+n).",
        historic="📜 *История:* Из греч. *skholē* — «досуг, свободное время». Для греков учёба была благородным использованием свободного времени.",
        exercises=[
            Exercise("▢ Schule beginnt um 8 Uhr.", "Die", "Nominativ"),
            Exercise("Ich gehe in ▢ Schule.", "die", "Akkusativ"),
            Exercise("Vor ▢ Schule warten viele Kinder.", "der", "Dativ"),
        ],
    ),
]


# ─────────────────────────────────────────────────────────
# KEYBOARDS
# ─────────────────────────────────────────────────────────

def build_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Начать тренировку", callback_data="menu:start")],
        [InlineKeyboardButton("🎯 По темам", callback_data="menu:topics")],
        [InlineKeyboardButton("📊 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton("❓ Помощь", callback_data="menu:help")],
    ])


def build_topic_menu() -> InlineKeyboardMarkup:
    topics = sorted({c.topic for c in CARDS})
    emoji = {"Alltag": "🏠", "Essen": "🍽", "Menschen": "👥", "Stadt": "🏙"}
    keyboard = [
        [InlineKeyboardButton(f"{emoji.get(t, '')} {t}", callback_data=f"topic:{t}")]
        for t in topics
    ]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(keyboard)


def build_article_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("der 🔵", callback_data="answer:der"),
            InlineKeyboardButton("die 🔴", callback_data="answer:die"),
            InlineKeyboardButton("das 🟢", callback_data="answer:das"),
        ],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="action:skip")],
        [InlineKeyboardButton("🏠 В меню", callback_data="menu:home")],
    ])


def build_exercise_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Der", callback_data="ex:Der"),
            InlineKeyboardButton("Die", callback_data="ex:Die"),
            InlineKeyboardButton("Das", callback_data="ex:Das"),
        ],
        [
            InlineKeyboardButton("Den", callback_data="ex:Den"),
            InlineKeyboardButton("Dem", callback_data="ex:Dem"),
            InlineKeyboardButton("Der (Dat.f)", callback_data="ex:Der"),
        ],
        [
            InlineKeyboardButton("Ein", callback_data="ex:Ein"),
            InlineKeyboardButton("Eine", callback_data="ex:Eine"),
            InlineKeyboardButton("Einem", callback_data="ex:Einem"),
        ],
        [InlineKeyboardButton("🏠 В меню", callback_data="menu:home")],
    ])


def build_next_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Следующее слово", callback_data="action:next")],
        [InlineKeyboardButton("🏠 В меню", callback_data="menu:home")],
    ])


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def get_user_stats(user_data: Dict) -> Dict:
    if "stats" not in user_data:
        user_data["stats"] = {
            "correct": 0, "wrong": 0,
            "streak": 0, "best_streak": 0, "total": 0,
        }
    return user_data["stats"]


def format_stats(stats: Dict) -> str:
    total = stats["total"]
    accuracy = round((stats["correct"] / total) * 100, 1) if total else 0
    return (
        "📊 *Твоя статистика*\n\n"
        f"Всего ответов: *{total}*\n"
        f"Верно: *{stats['correct']}*\n"
        f"Неверно: *{stats['wrong']}*\n"
        f"Точность: *{accuracy}%*\n"
        f"Текущая серия: *{stats['streak']}* 🔥\n"
        f"Лучшая серия: *{stats['best_streak']}* 🏆"
    )


def pick_card(topic: Optional[str] = None, exclude_word: Optional[str] = None) -> Card:
    pool = [c for c in CARDS if topic is None or c.topic == topic]
    if exclude_word:
        filtered = [c for c in pool if c.word != exclude_word]
        if filtered:
            pool = filtered
    return random.choice(pool)


def article_emoji(article: str) -> str:
    return {"der": "🔵", "die": "🔴", "das": "🟢"}.get(article, "⚪")


def topic_emoji(topic: str) -> str:
    return {"Alltag": "🏠", "Essen": "🍽", "Menschen": "👥", "Stadt": "🏙"}.get(topic, "📖")


def current_card(ud: Dict) -> Card:
    return CARDS[ud["current_card"]]


# ─────────────────────────────────────────────────────────
# SEND QUESTION
# ─────────────────────────────────────────────────────────

async def send_new_question(query_or_message, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    card = pick_card(topic=ud.get("topic"), exclude_word=ud.get("current_word"))

    ud["current_word"] = card.word
    ud["current_card"] = CARDS.index(card)
    ud["phase"] = "question"

    text = (
        f"{topic_emoji(card.topic)} *{card.topic}*\n\n"
        f"Какой артикль?\n\n"
        f"📖 *{card.word}*  —  _{card.translation}_\n"
        f"Мн.ч.: *{card.plural}*"
    )

    kb = build_article_keyboard()
    if hasattr(query_or_message, "edit_message_text"):
        await query_or_message.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await query_or_message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────
# SEND EXPLANATION + FIRST EXERCISE
# ─────────────────────────────────────────────────────────

async def send_explanation(query, context: ContextTypes.DEFAULT_TYPE, is_correct: bool) -> None:
    ud = context.user_data
    card = current_card(ud)
    ud["phase"] = "exercise"
    ud["exercise_idx"] = 0

    result = "✅ Правильно!" if is_correct else "❌ Неверно."
    ae = article_emoji(card.article)
    ex = card.exercises[0]

    text = (
        f"{result}\n\n"
        f"*{ae} {card.article} {card.word}*  —  _{card.translation}_\n\n"
        f"{card.semantic}\n\n"
        f"{card.morpho}\n\n"
        f"{card.historic}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✏️ *Упражнение 1/{len(card.exercises)} — {ex.case}:*\n\n"
        f"_{ex.template}_"
    )
    await query.edit_message_text(text, reply_markup=build_exercise_keyboard(), parse_mode="Markdown")


# ─────────────────────────────────────────────────────────
# HANDLE EXERCISE ANSWER
# ─────────────────────────────────────────────────────────

async def handle_exercise_answer(query, context: ContextTypes.DEFAULT_TYPE, chosen: str) -> None:
    ud = context.user_data
    card = current_card(ud)
    idx = ud["exercise_idx"]
    ex = card.exercises[idx]

    correct = chosen.lower() == ex.answer.lower()
    result_icon = "✅" if correct else f"❌  (правильно: *{ex.answer}*)"
    next_idx = idx + 1

    if next_idx < len(card.exercises):
        ud["exercise_idx"] = next_idx
        next_ex = card.exercises[next_idx]
        text = (
            f"_{ex.template}_\n"
            f"Твой ответ: *{chosen}* {result_icon}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✏️ *Упражнение {next_idx + 1}/{len(card.exercises)} — {next_ex.case}:*\n\n"
            f"_{next_ex.template}_"
        )
        await query.edit_message_text(text, reply_markup=build_exercise_keyboard(), parse_mode="Markdown")
    else:
        ud["phase"] = "done"
        ae = article_emoji(card.article)
        text = (
            f"_{ex.template}_\n"
            f"Твой ответ: *{chosen}* {result_icon}\n\n"
            f"🎉 Все упражнения пройдены!\n\n"
            f"Запомни: *{ae} {card.article} {card.word}*  —  _{card.translation}_"
        )
        await query.edit_message_text(text, reply_markup=build_next_keyboard(), parse_mode="Markdown")


# ─────────────────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["topic"] = None
    context.user_data["phase"] = None
    await update.message.reply_text(
        "👋 Привет! Я тренирую немецкие артикли.\n\n"
        "После каждого слова:\n"
        "1️⃣ Угадай артикль\n"
        "2️⃣ Читай объяснение — семантика + морфология + история\n"
        "3️⃣ Упражняйся в склонении\n\n"
        "Выбирай режим:",
        reply_markup=build_main_menu(),
    )


async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["stats"] = {
        "correct": 0, "wrong": 0, "streak": 0, "best_streak": 0, "total": 0,
    }
    await update.message.reply_text("Статистика сброшена ✅", reply_markup=build_main_menu())


# ─────────────────────────────────────────────────────────
# CALLBACK HANDLERS
# ─────────────────────────────────────────────────────────

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data
    stats = get_user_stats(context.user_data)

    if action in {"menu:home", "menu:back"}:
        context.user_data["topic"] = None
        context.user_data["phase"] = None
        await query.edit_message_text("Главное меню:", reply_markup=build_main_menu())

    elif action == "menu:start":
        context.user_data["topic"] = None
        await send_new_question(query, context)

    elif action == "menu:topics":
        await query.edit_message_text("Выбери тему:", reply_markup=build_topic_menu())

    elif action == "menu:stats":
        await query.edit_message_text(
            format_stats(stats),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Назад", callback_data="menu:back")]]
            ),
            parse_mode="Markdown",
        )

    elif action == "menu:help":
        await query.edit_message_text(
            "❓ *Как пользоваться*\n\n"
            "1. «Начать тренировку» — случайные слова.\n"
            "2. «По темам» — выбери тему.\n"
            "3. Угадай артикль → читай объяснение → склоняй.\n\n"
            "*Темы:* Alltag 🏠 · Essen 🍽 · Menschen 👥 · Stadt 🏙\n\n"
            "Команды:\n"
            "/start — главное меню\n"
            "/resetstats — сброс статистики",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Назад", callback_data="menu:back")]]
            ),
            parse_mode="Markdown",
        )


async def topic_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    topic = query.data.split(":", 1)[1]
    context.user_data["topic"] = topic
    await send_new_question(query, context)


async def answer_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ud = context.user_data
    if ud.get("phase") != "question":
        return

    selected = query.data.split(":", 1)[1]
    card = current_card(ud)
    stats = get_user_stats(ud)
    stats["total"] += 1

    if selected == card.article:
        stats["correct"] += 1
        stats["streak"] += 1
        stats["best_streak"] = max(stats["best_streak"], stats["streak"])
        is_correct = True
    else:
        stats["wrong"] += 1
        stats["streak"] = 0
        is_correct = False

    await send_explanation(query, context, is_correct)


async def exercise_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ud = context.user_data
    if ud.get("phase") != "exercise":
        return

    chosen = query.data.split(":", 1)[1]
    await handle_exercise_answer(query, context, chosen)


async def action_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "next":
        await send_new_question(query, context)

    elif action == "skip":
        ud = context.user_data
        card = current_card(ud)
        ae = article_emoji(card.article)
        await query.edit_message_text(
            f"⏭ Пропущено.\n\n"
            f"Правильный ответ: *{ae} {card.article} {card.word}* — _{card.translation}_",
            reply_markup=build_next_keyboard(),
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resetstats", reset_stats))
    app.add_handler(CallbackQueryHandler(menu_router, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(topic_router, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(answer_router, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(exercise_router, pattern=r"^ex:"))
    app.add_handler(CallbackQueryHandler(action_router, pattern=r"^action:"))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
