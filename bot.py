import json
import logging
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

try:
    import asyncpg
except ImportError:
    asyncpg = None  # bot still runs without a DB — falls back to in-memory progress

# =========================================================
# "Артикли на автомате" — Telegram bot for practicing German articles
# Stack: python-telegram-bot v22+
# Run:
#   1) pip3 install -r requirements.txt
#   2) export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
#   3) (optional) export DATABASE_URL="postgresql://..." — enables persistent progress
#   4) python3 bot.py
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
class Word:
    word: str
    artikel: str      # "der" / "die" / "das"
    translation: str


GENDER = {"der": "m", "die": "f", "das": "n"}

DEFINITE = {
    "m": {"Nominativ": "der", "Akkusativ": "den", "Dativ": "dem"},
    "f": {"Nominativ": "die", "Akkusativ": "die", "Dativ": "der"},
    "n": {"Nominativ": "das", "Akkusativ": "das", "Dativ": "dem"},
}

INDEFINITE = {
    "m": {"Nominativ": "ein", "Akkusativ": "einen", "Dativ": "einem"},
    "f": {"Nominativ": "eine", "Akkusativ": "eine", "Dativ": "einer"},
    "n": {"Nominativ": "ein", "Akkusativ": "ein", "Dativ": "einem"},
}

DEF_POOL = ["der", "die", "das", "den", "dem"]
INDEF_POOL = ["ein", "eine", "einen", "einem", "einer"]


def build_options(answer: str, kind: str) -> List[str]:
    """kind: 'def' or 'indef'. Returns 3 shuffled options including the answer,
    matching the answer's capitalization (sentence-initial vs mid-sentence)."""
    cap = answer[0].isupper()
    base = DEF_POOL if kind == "def" else INDEF_POOL
    pool = [b.capitalize() for b in base] if cap else list(base)
    others = [p for p in pool if p.lower() != answer.lower()]
    distractors = random.sample(others, 2)
    options = [answer] + distractors
    random.shuffle(options)
    return options


# ─────────────────────────────────────────────────────────
# TOPICS: id -> (emoji, title)
# ─────────────────────────────────────────────────────────

TOPIC_ORDER = [
    "haus", "kueche", "bad", "kleidung", "stadt",
    "buero", "gesundheit", "einkaufen", "reisen", "menschen",
]

TOPIC_META = {
    "haus": ("🏠", "Haus und Wohnung"),
    "kueche": ("🍴", "Küche und Essen"),
    "bad": ("🚿", "Bad und Pflege"),
    "kleidung": ("👕", "Kleidung und Schuhe"),
    "stadt": ("🚇", "Stadt und Verkehr"),
    "buero": ("💻", "Arbeit und Büro"),
    "gesundheit": ("🩹", "Gesundheit und Arzt"),
    "einkaufen": ("🛒", "Einkaufen und Geld"),
    "reisen": ("🧳", "Reisen und Freizeit"),
    "menschen": ("💬", "Menschen und Kontakt"),
}

# ─────────────────────────────────────────────────────────
# WORD LISTS (15 words per topic)
# ─────────────────────────────────────────────────────────

WORDS: Dict[str, List[Word]] = {
    "haus": [
        Word("Balkon", "der", "балкон"),
        Word("Teppich", "der", "ковёр"),
        Word("Regal", "das", "стеллаж, полка"),
        Word("Spiegel", "der", "зеркало"),
        Word("Decke", "die", "потолок / одеяло"),
        Word("Boden", "der", "пол"),
        Word("Wand", "die", "стена"),
        Word("Kissen", "das", "подушка"),
        Word("Steckdose", "die", "розетка"),
        Word("Schrank", "der", "шкаф"),
        Word("Schublade", "die", "ящик"),
        Word("Fenster", "das", "окно"),
        Word("Flur", "der", "коридор"),
        Word("Treppe", "die", "лестница"),
        Word("Schlüssel", "der", "ключ"),
    ],
    "kueche": [
        Word("Butter", "die", "масло"),
        Word("Joghurt", "der", "йогурт"),
        Word("Öl", "das", "масло"),
        Word("Reis", "der", "рис"),
        Word("Gemüse", "das", "овощи"),
        Word("Salat", "der", "салат"),
        Word("Löffel", "der", "ложка"),
        Word("Käse", "der", "сыр"),
        Word("Marmelade", "die", "варенье"),
        Word("Mehl", "das", "мука"),
        Word("Zucker", "der", "сахар"),
        Word("Zwiebel", "die", "лук"),
        Word("Knoblauch", "der", "чеснок"),
        Word("Ei", "das", "яйцо"),
        Word("Messer", "das", "нож"),
    ],
    "bad": [
        Word("Shampoo", "das", "шампунь"),
        Word("Seife", "die", "мыло"),
        Word("Creme", "die", "крем"),
        Word("Handtuch", "das", "полотенце"),
        Word("Duschgel", "das", "гель для душа"),
        Word("Zahnbürste", "die", "зубная щётка"),
        Word("Kamm", "der", "расчёска"),
        Word("Bürste", "die", "щётка"),
        Word("Rasierer", "der", "бритва"),
        Word("Waschbecken", "das", "раковина"),
        Word("Dusche", "die", "душ"),
        Word("Badewanne", "die", "ванна"),
        Word("Toilettenpapier", "das", "туалетная бумага"),
        Word("Föhn", "der", "фен"),
        Word("Abfluss", "der", "слив"),
    ],
    "kleidung": [
        Word("Pullover", "der", "свитер"),
        Word("Hemd", "das", "рубашка"),
        Word("Hose", "die", "брюки"),
        Word("Gürtel", "der", "ремень"),
        Word("Sakko", "das", "пиджак"),
        Word("Mantel", "der", "пальто"),
        Word("Kleid", "das", "платье"),
        Word("Rock", "der", "юбка"),
        Word("Handschuh", "der", "перчатка"),
        Word("Schuh", "der", "туфля / ботинок"),
        Word("Stiefel", "der", "сапог"),
        Word("Mütze", "die", "шапка"),
        Word("Schal", "der", "шарф"),
        Word("Bluse", "die", "блузка"),
        Word("T-Shirt", "das", "футболка"),
    ],
    "stadt": [
        Word("Bürgersteig", "der", "тротуар"),
        Word("Bahn", "die", "поезд / городской транспорт"),
        Word("Haltestelle", "die", "остановка"),
        Word("Bahnhof", "der", "вокзал"),
        Word("Taxi", "das", "такси"),
        Word("Verkehr", "der", "движение, транспорт"),
        Word("Eingang", "der", "вход"),
        Word("Weg", "der", "путь, дорога"),
        Word("Kreuzung", "die", "перекрёсток"),
        Word("Ampel", "die", "светофор"),
        Word("Parkplatz", "der", "парковка"),
        Word("Fahrrad", "das", "велосипед"),
        Word("Zug", "der", "поезд"),
        Word("U-Bahn", "die", "метро"),
        Word("Führerschein", "der", "водительские права"),
    ],
    "buero": [
        Word("Büro", "das", "офис"),
        Word("Termin", "der", "встреча, назначенный срок"),
        Word("E-Mail", "die", "электронное письмо"),
        Word("Vertrag", "der", "договор"),
        Word("Besprechung", "die", "совещание"),
        Word("Abteilung", "die", "отдел"),
        Word("Frist", "die", "срок"),
        Word("Gehalt", "das", "зарплата"),
        Word("Aufgabe", "die", "задача"),
        Word("Projekt", "das", "проект"),
        Word("Drucker", "der", "принтер"),
        Word("Bildschirm", "der", "экран"),
        Word("Tastatur", "die", "клавиатура"),
        Word("Dokument", "das", "документ"),
        Word("Auftrag", "der", "заказ, поручение"),
    ],
    "gesundheit": [
        Word("Schmerz", "der", "боль"),
        Word("Husten", "der", "кашель"),
        Word("Medikament", "das", "лекарство"),
        Word("Rezept", "das", "рецепт"),
        Word("Untersuchung", "die", "обследование"),
        Word("Praxis", "die", "врачебный кабинет / практика"),
        Word("Verband", "der", "бинт, повязка"),
        Word("Apotheke", "die", "аптека"),
        Word("Fieber", "das", "температура, жар"),
        Word("Erkältung", "die", "простуда"),
        Word("Rücken", "der", "спина"),
        Word("Salbe", "die", "мазь"),
        Word("Symptom", "das", "симптом"),
        Word("Tablette", "die", "таблетка"),
        Word("Pflaster", "das", "пластырь"),
    ],
    "einkaufen": [
        Word("Preis", "der", "цена"),
        Word("Angebot", "das", "предложение / акция"),
        Word("Rechnung", "die", "счёт"),
        Word("Rabatt", "der", "скидка"),
        Word("Kasse", "die", "касса"),
        Word("Gebühr", "die", "сбор, комиссия"),
        Word("Einkauf", "der", "покупка / закупка"),
        Word("Laden", "der", "магазин"),
        Word("Geschäft", "das", "магазин / дело"),
        Word("Quittung", "die", "чек"),
        Word("Betrag", "der", "сумма"),
        Word("Karte", "die", "карта"),
        Word("Bargeld", "das", "наличные"),
        Word("Cent", "der", "цент"),
        Word("Wechselgeld", "das", "сдача"),
    ],
    "reisen": [
        Word("Urlaub", "der", "отпуск"),
        Word("Reise", "die", "поездка"),
        Word("Buchung", "die", "бронирование"),
        Word("Ausflug", "der", "экскурсия, выезд"),
        Word("Freizeit", "die", "свободное время"),
        Word("Koffer", "der", "чемодан"),
        Word("Tasche", "die", "сумка"),
        Word("Pass", "der", "паспорт"),
        Word("Ticket", "das", "билет"),
        Word("Unterkunft", "die", "жильё"),
        Word("Strand", "der", "пляж"),
        Word("Meer", "das", "море"),
        Word("Grenze", "die", "граница"),
        Word("Wanderung", "die", "поход"),
        Word("Gepäck", "das", "багаж"),
    ],
    "menschen": [
        Word("Mensch", "der", "человек"),
        Word("Person", "die", "человек, персона"),
        Word("Kontakt", "der", "контакт"),
        Word("Bekannte", "der", "знакомый"),
        Word("Bekanntschaft", "die", "знакомство / знакомый человек"),
        Word("Gast", "der", "гость"),
        Word("Besuch", "der", "визит / гости"),
        Word("Gespräch", "das", "разговор"),
        Word("Nachricht", "die", "сообщение"),
        Word("Anruf", "der", "звонок"),
        Word("Verhalten", "das", "поведение"),
        Word("Eindruck", "der", "впечатление"),
        Word("Einladung", "die", "приглашение"),
        Word("Beziehung", "die", "отношения"),
        Word("Paar", "das", "пара"),
    ],
}

# ─────────────────────────────────────────────────────────
# PART 3 — sentences in context (word, case, type, template, answer)
# type: "bestimmt" / "unbestimmt"
# ─────────────────────────────────────────────────────────

PART3: Dict[str, List[tuple]] = {
    "haus": [
        ("Schlüssel", "Akkusativ", "unbestimmt", "Ich suche ▢▢▢ Schlüssel.", "einen"),
        ("Steckdose", "Dativ", "unbestimmt", "Neben ▢▢▢ Steckdose steht eine Lampe.", "einer"),
        ("Regal", "Nominativ", "unbestimmt", "▢▢▢ Regal steht im Wohnzimmer.", "Ein"),
        ("Teppich", "Dativ", "unbestimmt", "Die Katze liegt auf ▢▢▢ Teppich.", "einem"),
        ("Schrank", "Akkusativ", "unbestimmt", "Wir kaufen ▢▢▢ neuen Schrank.", "einen"),
        ("Boden", "Dativ", "bestimmt", "Die Schuhe stehen auf ▢▢▢ Boden.", "dem"),
        ("Balkon", "Nominativ", "bestimmt", "▢▢▢ Balkon ist ziemlich klein.", "Der"),
        ("Spiegel", "Akkusativ", "bestimmt", "Wir kaufen ▢▢▢ Spiegel für den Flur.", "den"),
        ("Decke", "Dativ", "bestimmt", "An ▢▢▢ Decke hängt eine Lampe.", "der"),
        ("Wand", "Akkusativ", "unbestimmt", "Wir streichen ▢▢▢ Wand blau.", "eine"),
        ("Kissen", "Nominativ", "unbestimmt", "▢▢▢ Kissen liegt auf dem Sofa.", "Ein"),
        ("Schublade", "Dativ", "unbestimmt", "In ▢▢▢ Schublade liegt ein Messer.", "einer"),
        ("Fenster", "Akkusativ", "bestimmt", "Ich öffne ▢▢▢ Fenster.", "das"),
        ("Flur", "Dativ", "bestimmt", "Die Schuhe stehen in ▢▢▢ Flur.", "dem"),
        ("Treppe", "Nominativ", "bestimmt", "▢▢▢ Treppe ist sehr steil.", "Die"),
    ],
    "kueche": [
        ("Butter", "Nominativ", "bestimmt", "▢▢▢ Butter ist im Kühlschrank.", "Die"),
        ("Joghurt", "Akkusativ", "unbestimmt", "Ich kaufe ▢▢▢ Joghurt.", "einen"),
        ("Öl", "Dativ", "bestimmt", "Wir kochen mit ▢▢▢ Öl.", "dem"),
        ("Reis", "Akkusativ", "bestimmt", "Ich koche ▢▢▢ Reis.", "den"),
        ("Gemüse", "Nominativ", "bestimmt", "▢▢▢ Gemüse ist frisch.", "Das"),
        ("Salat", "Dativ", "unbestimmt", "Ich esse Brot zu ▢▢▢ Salat.", "einem"),
        ("Löffel", "Akkusativ", "unbestimmt", "Ich nehme ▢▢▢ Löffel.", "einen"),
        ("Käse", "Nominativ", "bestimmt", "▢▢▢ Käse schmeckt gut.", "Der"),
        ("Marmelade", "Akkusativ", "bestimmt", "Ich streiche ▢▢▢ Marmelade aufs Brot.", "die"),
        ("Mehl", "Dativ", "bestimmt", "Wir backen mit ▢▢▢ Mehl.", "dem"),
        ("Zucker", "Akkusativ", "bestimmt", "Ich brauche ▢▢▢ Zucker für den Kuchen.", "den"),
        ("Zwiebel", "Nominativ", "unbestimmt", "▢▢▢ Zwiebel liegt neben der Tomate.", "Eine"),
        ("Knoblauch", "Dativ", "bestimmt", "Die Soße schmeckt nach ▢▢▢ Knoblauch.", "dem"),
        ("Ei", "Akkusativ", "bestimmt", "Ich koche ▢▢▢ Ei.", "das"),
        ("Messer", "Nominativ", "unbestimmt", "▢▢▢ Messer liegt auf dem Tisch.", "Ein"),
    ],
    "bad": [
        ("Shampoo", "Nominativ", "bestimmt", "▢▢▢ Shampoo ist nicht so gut.", "Das"),
        ("Seife", "Akkusativ", "unbestimmt", "Ich kaufe ▢▢▢ Seife.", "eine"),
        ("Creme", "Dativ", "bestimmt", "Ich bin zufrieden mit ▢▢▢ Creme.", "der"),
        ("Handtuch", "Akkusativ", "unbestimmt", "Ich nehme ▢▢▢ Handtuch.", "ein"),
        ("Duschgel", "Nominativ", "bestimmt", "▢▢▢ Duschgel riecht nach Zitrone.", "Das"),
        ("Zahnbürste", "Dativ", "bestimmt", "Ich putze die Zähne mit ▢▢▢ Zahnbürste.", "der"),
        ("Kamm", "Akkusativ", "unbestimmt", "Ich nehme ▢▢▢ Kamm.", "einen"),
        ("Bürste", "Nominativ", "bestimmt", "▢▢▢ Bürste liegt im Bad.", "Die"),
        ("Rasierer", "Akkusativ", "unbestimmt", "Ich kaufe ▢▢▢ neuen Rasierer.", "einen"),
        ("Waschbecken", "Dativ", "unbestimmt", "Die Seife liegt neben ▢▢▢ Waschbecken.", "einem"),
        ("Dusche", "Akkusativ", "bestimmt", "Ich putze ▢▢▢ Dusche.", "die"),
        ("Badewanne", "Nominativ", "bestimmt", "▢▢▢ Badewanne ist sehr groß.", "Die"),
        ("Toilettenpapier", "Dativ", "bestimmt", "Neben ▢▢▢ Toilettenpapier liegt ein Handtuch.", "dem"),
        ("Föhn", "Akkusativ", "unbestimmt", "Ich brauche ▢▢▢ Föhn.", "einen"),
        ("Abfluss", "Nominativ", "unbestimmt", "▢▢▢ Abfluss ist verstopft.", "Ein"),
    ],
    "kleidung": [
        ("Pullover", "Nominativ", "unbestimmt", "▢▢▢ Pullover ist warm.", "Ein"),
        ("Hemd", "Akkusativ", "bestimmt", "Ich kaufe ▢▢▢ Hemd.", "das"),
        ("Hose", "Dativ", "bestimmt", "Der Fleck ist an ▢▢▢ Hose.", "der"),
        ("Gürtel", "Akkusativ", "bestimmt", "Ich trage ▢▢▢ Gürtel.", "den"),
        ("Sakko", "Nominativ", "unbestimmt", "▢▢▢ Sakko passt gut.", "Ein"),
        ("Mantel", "Dativ", "unbestimmt", "Ich stehe mit ▢▢▢ Mantel an der Tür.", "einem"),
        ("Kleid", "Akkusativ", "unbestimmt", "Ich ziehe ▢▢▢ Kleid an.", "ein"),
        ("Rock", "Nominativ", "unbestimmt", "▢▢▢ Rock ist zu lang.", "Ein"),
        ("Handschuh", "Akkusativ", "bestimmt", "Ich verliere ▢▢▢ Handschuh.", "den"),
        ("Schuh", "Dativ", "unbestimmt", "Ein Stein ist in ▢▢▢ Schuh.", "einem"),
        ("Stiefel", "Nominativ", "bestimmt", "▢▢▢ Stiefel steht im Flur.", "Der"),
        ("Mütze", "Akkusativ", "bestimmt", "Ich setze ▢▢▢ Mütze auf.", "die"),
        ("Schal", "Dativ", "unbestimmt", "An ▢▢▢ Schal hängt ein Preisschild.", "einem"),
        ("Bluse", "Akkusativ", "bestimmt", "Ich kaufe ▢▢▢ Bluse.", "die"),
        ("T-Shirt", "Nominativ", "bestimmt", "▢▢▢ T-Shirt ist zu klein.", "Das"),
    ],
    "stadt": [
        ("Bürgersteig", "Nominativ", "bestimmt", "▢▢▢ Bürgersteig ist nass.", "Der"),
        ("Bahn", "Akkusativ", "bestimmt", "Ich nehme ▢▢▢ Bahn.", "die"),
        ("Haltestelle", "Dativ", "unbestimmt", "Ich warte an ▢▢▢ Haltestelle.", "einer"),
        ("Bahnhof", "Akkusativ", "bestimmt", "Ich sehe ▢▢▢ Bahnhof von hier.", "den"),
        ("Taxi", "Nominativ", "bestimmt", "▢▢▢ Taxi steht vor der Tür.", "Das"),
        ("Verkehr", "Nominativ", "bestimmt", "▢▢▢ Verkehr ist heute sehr dicht.", "Der"),
        ("Eingang", "Akkusativ", "unbestimmt", "Ich suche ▢▢▢ Eingang.", "einen"),
        ("Weg", "Nominativ", "unbestimmt", "▢▢▢ Weg ist sehr lang.", "Ein"),
        ("Kreuzung", "Dativ", "bestimmt", "An ▢▢▢ Kreuzung ist ein Unfall passiert.", "der"),
        ("Ampel", "Akkusativ", "bestimmt", "Ich sehe ▢▢▢ Ampel nicht.", "die"),
        ("Parkplatz", "Nominativ", "unbestimmt", "▢▢▢ Parkplatz ist frei.", "Ein"),
        ("Fahrrad", "Akkusativ", "unbestimmt", "Ich kaufe ▢▢▢ Fahrrad.", "ein"),
        ("Zug", "Dativ", "bestimmt", "Ich fahre mit ▢▢▢ Zug.", "dem"),
        ("U-Bahn", "Akkusativ", "bestimmt", "Ich nehme ▢▢▢ U-Bahn.", "die"),
        ("Führerschein", "Nominativ", "unbestimmt", "▢▢▢ Führerschein ist noch gültig.", "Ein"),
    ],
    "buero": [
        ("Büro", "Nominativ", "bestimmt", "▢▢▢ Büro ist im dritten Stock.", "Das"),
        ("Termin", "Akkusativ", "unbestimmt", "Ich habe ▢▢▢ Termin um zehn Uhr.", "einen"),
        ("E-Mail", "Dativ", "bestimmt", "Der Anhang ist in ▢▢▢ E-Mail.", "der"),
        ("Vertrag", "Akkusativ", "bestimmt", "Ich unterschreibe ▢▢▢ Vertrag.", "den"),
        ("Besprechung", "Nominativ", "unbestimmt", "▢▢▢ Besprechung beginnt gleich.", "Eine"),
        ("Abteilung", "Dativ", "unbestimmt", "Er arbeitet in ▢▢▢ anderen Abteilung.", "einer"),
        ("Frist", "Akkusativ", "bestimmt", "Wir verpassen ▢▢▢ Frist.", "die"),
        ("Gehalt", "Nominativ", "bestimmt", "▢▢▢ Gehalt kommt am Monatsende.", "Das"),
        ("Aufgabe", "Akkusativ", "unbestimmt", "Ich bekomme ▢▢▢ neue Aufgabe.", "eine"),
        ("Projekt", "Dativ", "unbestimmt", "Wir arbeiten an ▢▢▢ Projekt.", "einem"),
        ("Drucker", "Nominativ", "bestimmt", "▢▢▢ Drucker funktioniert nicht.", "Der"),
        ("Bildschirm", "Akkusativ", "bestimmt", "Ich putze ▢▢▢ Bildschirm.", "den"),
        ("Tastatur", "Dativ", "bestimmt", "Ich tippe mit ▢▢▢ neuen Tastatur.", "der"),
        ("Dokument", "Akkusativ", "unbestimmt", "Ich unterschreibe ▢▢▢ Dokument.", "ein"),
        ("Auftrag", "Nominativ", "bestimmt", "▢▢▢ Auftrag ist sehr wichtig.", "Der"),
    ],
    "gesundheit": [
        ("Schmerz", "Nominativ", "bestimmt", "▢▢▢ Schmerz kommt und geht.", "Der"),
        ("Husten", "Nominativ", "bestimmt", "▢▢▢ Husten wird nicht besser.", "Der"),
        ("Medikament", "Dativ", "bestimmt", "Ich helfe mit ▢▢▢ Medikament.", "dem"),
        ("Rezept", "Akkusativ", "unbestimmt", "Ich hole ▢▢▢ Rezept ab.", "ein"),
        ("Untersuchung", "Nominativ", "unbestimmt", "▢▢▢ Untersuchung dauert eine Stunde.", "Eine"),
        ("Praxis", "Dativ", "unbestimmt", "Ich warte in ▢▢▢ vollen Praxis.", "einer"),
        ("Verband", "Akkusativ", "unbestimmt", "Die Ärztin wechselt ▢▢▢ Verband.", "einen"),
        ("Apotheke", "Nominativ", "bestimmt", "▢▢▢ Apotheke ist gleich um die Ecke.", "Die"),
        ("Fieber", "Akkusativ", "unbestimmt", "Ich habe ▢▢▢ hohes Fieber.", "ein"),
        ("Erkältung", "Dativ", "unbestimmt", "Ich leide an ▢▢▢ Erkältung.", "einer"),
        ("Rücken", "Nominativ", "bestimmt", "▢▢▢ Rücken tut weh.", "Der"),
        ("Salbe", "Akkusativ", "bestimmt", "Ich kaufe ▢▢▢ Salbe.", "die"),
        ("Symptom", "Nominativ", "bestimmt", "▢▢▢ Symptom ist harmlos.", "Das"),
        ("Tablette", "Dativ", "bestimmt", "Ich helfe mir mit ▢▢▢ Tablette.", "der"),
        ("Pflaster", "Akkusativ", "unbestimmt", "Ich klebe ▢▢▢ Pflaster auf die Wunde.", "ein"),
    ],
    "einkaufen": [
        ("Preis", "Nominativ", "bestimmt", "▢▢▢ Preis ist zu hoch.", "Der"),
        ("Angebot", "Akkusativ", "unbestimmt", "Ich nutze ▢▢▢ Angebot.", "ein"),
        ("Rechnung", "Dativ", "bestimmt", "Der Betrag steht auf ▢▢▢ Rechnung.", "der"),
        ("Rabatt", "Akkusativ", "unbestimmt", "Ich bekomme ▢▢▢ Rabatt.", "einen"),
        ("Kasse", "Nominativ", "unbestimmt", "▢▢▢ Kasse ist gerade frei.", "Eine"),
        ("Gebühr", "Dativ", "bestimmt", "Ich zahle mit ▢▢▢ zusätzlichen Gebühr.", "der"),
        ("Einkauf", "Akkusativ", "bestimmt", "Ich trage ▢▢▢ Einkauf nach Hause.", "den"),
        ("Laden", "Nominativ", "unbestimmt", "▢▢▢ Laden schließt um acht.", "Ein"),
        ("Geschäft", "Akkusativ", "bestimmt", "Ich eröffne ▢▢▢ Geschäft.", "das"),
        ("Quittung", "Dativ", "bestimmt", "Ich brauche eine Kopie von ▢▢▢ Quittung.", "der"),
        ("Betrag", "Nominativ", "bestimmt", "▢▢▢ Betrag ist falsch.", "Der"),
        ("Karte", "Akkusativ", "unbestimmt", "Ich nehme ▢▢▢ Karte.", "eine"),
        ("Bargeld", "Dativ", "bestimmt", "Ich zahle mit ▢▢▢ Bargeld.", "dem"),
        ("Cent", "Nominativ", "unbestimmt", "▢▢▢ Cent liegt auf dem Boden.", "Ein"),
        ("Wechselgeld", "Akkusativ", "bestimmt", "Ich zähle ▢▢▢ Wechselgeld.", "das"),
    ],
    "reisen": [
        ("Urlaub", "Nominativ", "bestimmt", "▢▢▢ Urlaub beginnt morgen.", "Der"),
        ("Reise", "Akkusativ", "unbestimmt", "Ich plane ▢▢▢ Reise.", "eine"),
        ("Buchung", "Dativ", "unbestimmt", "Es gibt ein Problem mit ▢▢▢ Buchung.", "einer"),
        ("Ausflug", "Akkusativ", "bestimmt", "Wir machen ▢▢▢ Ausflug.", "den"),
        ("Freizeit", "Nominativ", "bestimmt", "▢▢▢ Freizeit ist mir wichtig.", "Die"),
        ("Koffer", "Akkusativ", "unbestimmt", "Ich packe ▢▢▢ Koffer.", "einen"),
        ("Tasche", "Dativ", "unbestimmt", "Der Pass ist in ▢▢▢ Tasche.", "einer"),
        ("Pass", "Akkusativ", "bestimmt", "Ich zeige ▢▢▢ Pass.", "den"),
        ("Ticket", "Nominativ", "unbestimmt", "▢▢▢ Ticket liegt auf dem Tisch.", "Ein"),
        ("Unterkunft", "Dativ", "bestimmt", "Ich bin zufrieden mit ▢▢▢ Unterkunft.", "der"),
        ("Strand", "Nominativ", "bestimmt", "▢▢▢ Strand ist leer.", "Der"),
        ("Meer", "Dativ", "bestimmt", "Wir wohnen nah an ▢▢▢ Meer.", "dem"),
        ("Grenze", "Akkusativ", "bestimmt", "Wir sehen schon ▢▢▢ Grenze.", "die"),
        ("Wanderung", "Nominativ", "unbestimmt", "▢▢▢ Wanderung dauert sechs Stunden.", "Eine"),
        ("Gepäck", "Akkusativ", "bestimmt", "Ich hole ▢▢▢ Gepäck ab.", "das"),
    ],
    "menschen": [
        ("Mensch", "Nominativ", "bestimmt", "▢▢▢ Mensch wartet vor der Tür.", "Der"),
        ("Person", "Akkusativ", "unbestimmt", "Ich kenne ▢▢▢ Person nicht.", "eine"),
        ("Kontakt", "Dativ", "unbestimmt", "Ich stehe mit ▢▢▢ Kontakt in Verbindung.", "einem"),
        ("Bekannte", "Akkusativ", "unbestimmt", "Ich treffe ▢▢▢ Bekannten.", "einen"),
        ("Bekanntschaft", "Akkusativ", "unbestimmt", "Ich habe ▢▢▢ neue Bekanntschaft gemacht.", "eine"),
        ("Gast", "Dativ", "bestimmt", "Ich zeige ▢▢▢ Gast das Zimmer.", "dem"),
        ("Besuch", "Akkusativ", "bestimmt", "Wir planen ▢▢▢ Besuch.", "den"),
        ("Gespräch", "Nominativ", "bestimmt", "▢▢▢ Gespräch war sehr offen.", "Das"),
        ("Nachricht", "Akkusativ", "bestimmt", "Ich schreibe ▢▢▢ Nachricht.", "die"),
        ("Anruf", "Akkusativ", "unbestimmt", "Ich bekomme ▢▢▢ Anruf.", "einen"),
        ("Verhalten", "Dativ", "bestimmt", "Wir sind überrascht von ▢▢▢ Verhalten.", "dem"),
        ("Eindruck", "Akkusativ", "unbestimmt", "Er macht ▢▢▢ guten Eindruck.", "einen"),
        ("Einladung", "Akkusativ", "bestimmt", "Ich bekomme ▢▢▢ Einladung.", "die"),
        ("Beziehung", "Dativ", "unbestimmt", "Sie ist in ▢▢▢ neuen Beziehung.", "einer"),
        ("Paar", "Nominativ", "unbestimmt", "▢▢▢ Paar sitzt im Café.", "Ein"),
    ],
}

# ─────────────────────────────────────────────────────────
# PART 4 — Akkusativ/Dativ contrast pairs (Wechselpräpositionen)
# Each entry: header word, akk (template, answer), dat (template, answer)
# ─────────────────────────────────────────────────────────

PART4: Dict[str, List[dict]] = {
    "haus": [
        {"word": "der Teppich", "type": "unbestimmt", "akk": ("Ich lege das Kissen auf ▢▢▢ Teppich.", "einen"), "dat": ("Das Kissen liegt auf ▢▢▢ Teppich.", "einem")},
        {"word": "die Wand", "type": "bestimmt", "akk": ("Wir hängen das Bild an ▢▢▢ Wand.", "die"), "dat": ("Das Bild hängt an ▢▢▢ Wand.", "der")},
        {"word": "das Regal", "type": "unbestimmt", "akk": ("Ich stelle die Bücher in ▢▢▢ Regal.", "ein"), "dat": ("Die Bücher stehen in ▢▢▢ Regal.", "einem")},
        {"word": "der Balkon", "type": "bestimmt", "akk": ("Wir stellen einen Tisch auf ▢▢▢ Balkon.", "den"), "dat": ("Der Tisch steht auf ▢▢▢ Balkon.", "dem")},
    ],
    "kueche": [
        {"word": "der Topf", "type": "unbestimmt", "akk": ("Ich lege das Ei in ▢▢▢ Topf.", "einen"), "dat": ("Das Ei liegt in ▢▢▢ Topf.", "einem")},
        {"word": "die Pfanne", "type": "bestimmt", "akk": ("Ich lege das Gemüse in ▢▢▢ Pfanne.", "die"), "dat": ("Das Gemüse liegt in ▢▢▢ Pfanne.", "der")},
        {"word": "der Kühlschrank", "type": "unbestimmt", "akk": ("Ich lege den Käse in ▢▢▢ Kühlschrank.", "einen"), "dat": ("Der Käse liegt in ▢▢▢ Kühlschrank.", "einem")},
    ],
    "bad": [
        {"word": "das Waschbecken", "type": "bestimmt", "akk": ("Ich lege die Seife auf ▢▢▢ Waschbecken.", "das"), "dat": ("Die Seife liegt auf ▢▢▢ Waschbecken.", "dem")},
        {"word": "die Dusche", "type": "unbestimmt", "akk": ("Ich stelle das Shampoo in ▢▢▢ Dusche.", "eine"), "dat": ("Das Shampoo steht in ▢▢▢ Dusche.", "einer")},
        {"word": "die Badewanne", "type": "bestimmt", "akk": ("Ich setze mich in ▢▢▢ Badewanne.", "die"), "dat": ("Ich sitze in ▢▢▢ Badewanne.", "der")},
    ],
    "kleidung": [
        {"word": "der Haken", "type": "unbestimmt", "akk": ("Ich hänge den Mantel an ▢▢▢ Haken.", "einen"), "dat": ("Der Mantel hängt an ▢▢▢ Haken.", "einem")},
        {"word": "der Schrank", "type": "bestimmt", "akk": ("Ich lege das Kleid in ▢▢▢ Schrank.", "den"), "dat": ("Das Kleid liegt in ▢▢▢ Schrank.", "dem")},
        {"word": "die Tür", "type": "bestimmt", "akk": ("Ich stelle den Schuh vor ▢▢▢ Tür.", "die"), "dat": ("Der Schuh steht vor ▢▢▢ Tür.", "der")},
    ],
    "stadt": [
        {"word": "der Bahnhof", "type": "unbestimmt", "akk": ("Ich gehe in ▢▢▢ Bahnhof.", "einen"), "dat": ("Ich bin in ▢▢▢ Bahnhof.", "einem")},
        {"word": "die Kreuzung", "type": "bestimmt", "akk": ("Das Auto fährt an ▢▢▢ Kreuzung.", "die"), "dat": ("Das Auto steht an ▢▢▢ Kreuzung.", "der")},
        {"word": "der Parkplatz", "type": "unbestimmt", "akk": ("Ich fahre auf ▢▢▢ Parkplatz.", "einen"), "dat": ("Das Auto steht auf ▢▢▢ Parkplatz.", "einem")},
    ],
    "buero": [
        {"word": "das Büro", "type": "bestimmt", "akk": ("Ich gehe in ▢▢▢ Büro.", "das"), "dat": ("Ich bin in ▢▢▢ Büro.", "dem")},
        {"word": "der Schreibtisch", "type": "unbestimmt", "akk": ("Ich lege das Dokument auf ▢▢▢ Schreibtisch.", "einen"), "dat": ("Das Dokument liegt auf ▢▢▢ Schreibtisch.", "einem")},
        {"word": "der Ordner", "type": "unbestimmt", "akk": ("Ich lege die Akte in ▢▢▢ Ordner.", "einen"), "dat": ("Die Akte liegt in ▢▢▢ Ordner.", "einem")},
    ],
    "gesundheit": [
        {"word": "die Apotheke", "type": "unbestimmt", "akk": ("Ich gehe in ▢▢▢ Apotheke.", "eine"), "dat": ("Ich bin in ▢▢▢ Apotheke.", "einer")},
        {"word": "die Praxis", "type": "bestimmt", "akk": ("Ich gehe in ▢▢▢ Praxis.", "die"), "dat": ("Ich warte in ▢▢▢ Praxis.", "der")},
        {"word": "der Rücken", "type": "bestimmt", "akk": ("Ich lege die Hand auf ▢▢▢ Rücken.", "den"), "dat": ("Die Hand liegt auf ▢▢▢ Rücken.", "dem")},
    ],
    "einkaufen": [
        {"word": "der Laden", "type": "unbestimmt", "akk": ("Ich gehe in ▢▢▢ Laden.", "einen"), "dat": ("Ich bin in ▢▢▢ Laden.", "einem")},
        {"word": "die Kasse", "type": "bestimmt", "akk": ("Ich stelle mich an ▢▢▢ Kasse.", "die"), "dat": ("Ich stehe an ▢▢▢ Kasse.", "der")},
        {"word": "das Geschäft", "type": "unbestimmt", "akk": ("Ich gehe in ▢▢▢ Geschäft.", "ein"), "dat": ("Ich arbeite in ▢▢▢ Geschäft.", "einem")},
    ],
    "reisen": [
        {"word": "der Koffer", "type": "unbestimmt", "akk": ("Ich lege das T-Shirt in ▢▢▢ Koffer.", "einen"), "dat": ("Das T-Shirt liegt in ▢▢▢ Koffer.", "einem")},
        {"word": "die Tasche", "type": "bestimmt", "akk": ("Ich stecke den Pass in ▢▢▢ Tasche.", "die"), "dat": ("Der Pass steckt in ▢▢▢ Tasche.", "der")},
        {"word": "das Meer", "type": "bestimmt", "akk": ("Wir gehen in ▢▢▢ Meer.", "das"), "dat": ("Wir schwimmen in ▢▢▢ Meer.", "dem")},
    ],
    "menschen": [
        {"word": "der Kontakt", "type": "bestimmt", "akk": ("Wir kommen in ▢▢▢ Kontakt.", "den"), "dat": ("Wir bleiben in ▢▢▢ Kontakt.", "dem")},
        {"word": "das Gespräch", "type": "bestimmt", "akk": ("Wir kommen in ▢▢▢ Gespräch.", "das"), "dat": ("Wir sind in ▢▢▢ Gespräch vertieft.", "dem")},
    ],
}

# ─────────────────────────────────────────────────────────
# PRAISE VARIANTS
# ─────────────────────────────────────────────────────────

PRAISE_VARIANTS = [
    "Готово! Артикли понемногу теряют право на внезапность.",
    "Очень хорошо! Ещё 15 слов — и всё меньше поводов гадать на der/die/das.",
    "Хорошо идёт!",
    "Ещё одна тема готова.",
    "Отличная работа! Ещё 15 слов в копилку.",
    "Урааа, ты супергерой артиклей! 🦸",
    "Так держать! Ещё 15 слов теперь знают своё место и свой падеж.",
    "Ещё одна тема повержена. Der, die и das начинают нервничать.",
    "Готово! Артикли становятся подозрительно послушными.",
    "Отличная работа! Артикли пока не сдались, но явно начали волноваться.",
    "Отличная работа! Ещё 15 слов отправляются в отдел «не надо каждый раз угадывать».",
    "Артикли постепенно переходят на твою сторону: dem и einem — уже почти свои.",
]

FINAL_VARIANTS = [
    "Урааа, теперь это уже почти суперспособность. 🦸",
    "150 слов готовы. Der, die и das могут расходиться.",
    "Готово. Теперь угадывать придётся заметно реже.",
]

CASE_LABELS = {"Nominativ": "Nominativ", "Akkusativ": "Akkusativ", "Dativ": "Dativ"}


# ─────────────────────────────────────────────────────────
# KEYBOARDS
# ─────────────────────────────────────────────────────────

def kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Начать", callback_data="go:howto")]])


def kb_howto() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Выбрать тему", callback_data="go:menu")],
        [InlineKeyboardButton("Таблица артиклей", callback_data="go:cheat")],
    ])


def kb_main_menu(completed: set, show_hardwords: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for tid in TOPIC_ORDER:
        emoji, title = TOPIC_META[tid]
        mark = " ✅" if tid in completed else ""
        rows.append([InlineKeyboardButton(f"{emoji} {title}{mark}", callback_data=f"topic:{tid}")])
    rows.append([InlineKeyboardButton(FAKE_DOOR_MENU_LABEL["nohint"], callback_data="fakedoor:nohint")])
    rows.append([InlineKeyboardButton(FAKE_DOOR_MENU_LABEL["plural"], callback_data="fakedoor:plural")])
    if show_hardwords:
        rows.append([InlineKeyboardButton(FAKE_DOOR_MENU_LABEL["hardwords"], callback_data="fakedoor:hardwords")])
    rows.append([InlineKeyboardButton("🔠 Таблица артиклей", callback_data="go:cheat")])
    return InlineKeyboardMarkup(rows)


def kb_offer3() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Мне интересно", callback_data="offer3:interested")],
        [InlineKeyboardButton("Продолжить бесплатную версию", callback_data="offer3:continue")],
    ])


def kb_offer10() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Хочу полную версию", callback_data="offer10:want")],
        [InlineKeyboardButton("Вернуться в бесплатный бот", callback_data="offer10:back")],
    ])


def kb_fakedoor(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(FAKE_DOOR_BUTTON_LABEL[kind], callback_data=f"fakedoor_click:{kind}")],
        [InlineKeyboardButton("🔙 В меню", callback_data="go:menu")],
    ])


def kb_cheat_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад к заданию", callback_data="backcheat")]])


def kb_intro(callback: str, label: str = "Начать") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=callback)],
        [InlineKeyboardButton("🔠 Таблица артиклей", callback_data="cheatmid")],
    ])


def kb_options(options: List[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(o, callback_data=f"answer:{o}")] for o in options]
    rows.append([InlineKeyboardButton("🔠 Таблица артиклей", callback_data="cheatmid")])
    return InlineKeyboardMarkup(rows)


def kb_continue() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Дальше ▶️", callback_data="continue")],
        [InlineKeyboardButton("🔠 Таблица артиклей", callback_data="cheatmid")],
    ])


# ─────────────────────────────────────────────────────────
# ITEM BUILDERS (per phase)
# ─────────────────────────────────────────────────────────

def build_p1_items(topic_id: str) -> List[dict]:
    items = []
    for w in WORDS[topic_id]:
        options = ["der", "die", "das"]
        random.shuffle(options)
        items.append({
            "prompt": f"▢▢▢ {w.word}",
            "full": f"{w.artikel} {w.word}",
            "options": options,
            "answer": w.artikel,
            "word": w.word,
            "translation": w.translation,
        })
    return items


def build_p2_items(topic_id: str) -> List[dict]:
    words = WORDS[topic_id]
    cases = ["Nominativ", "Akkusativ", "Dativ"]
    items = []
    for i, w in enumerate(words):
        case = cases[i % 3]  # even 5/5/5 split across 15 words
        gender = GENDER[w.artikel]
        def_form = DEFINITE[gender][case]
        answer = INDEFINITE[gender][case]
        options = build_options(answer, "indef")
        prompt = (
            f"*{w.artikel} {w.word}* · {case}\n\n"
            f"С определённым артиклем:\n\n*{def_form} {w.word}*\n\n"
            f"А с неопределённым?"
        )
        items.append({"prompt": prompt, "full": f"{answer} {w.word}", "options": options, "answer": answer})
    return items


def build_p3_items(topic_id: str) -> List[dict]:
    items = []
    for word, case, atype, template, answer in PART3[topic_id]:
        kind = "def" if atype == "bestimmt" else "indef"
        options = build_options(answer, kind)
        art_label = "bestimmter" if atype == "bestimmt" else "unbestimmter"
        prompt = f"*{case} · {art_label} Artikel*\n\n{template}"
        full = template.replace("▢▢▢", answer)
        items.append({"prompt": prompt, "full": full, "options": options, "answer": answer})
    return items


def build_p4_items(topic_id: str) -> List[dict]:
    items = []
    for pair in PART4[topic_id]:
        kind = "def" if pair.get("type", "bestimmt") == "bestimmt" else "indef"
        for case_name, (template, answer) in (("Akkusativ", pair["akk"]), ("Dativ", pair["dat"])):
            options = build_options(answer, kind)
            prompt = f"*{pair['word']}*\n\n*{case_name}*\n\n{template}"
            full = template.replace("▢▢▢", answer)
            items.append({"prompt": prompt, "full": full, "options": options, "answer": answer})
    return items


PHASE_BUILDERS = {"p1": build_p1_items, "p2": build_p2_items, "p3": build_p3_items, "p4": build_p4_items}

PHASE_INTRO = {
    "p1": (
        "*Для начала — der, die или das?*\n\nПосмотрим, насколько хорошо знакомы сами слова.",
        "Начать",
    ),
    "p2": (
        "*Теперь — формы неопределённого артикля.*\n\n"
        "Посмотрим, что происходит с *ein* и *eine* в разных падежах.\n\n"
        "den → einen\ndem → einem\nder → einer",
        "Дальше",
    ),
    "p3": (
        "*Теперь — предложения.*\n\n"
        "Падеж и тип артикля уже указаны. Нужно выбрать правильную форму.",
        "Начать",
    ),
    # p4 (Akkusativ/Dativ на Wechselpräpositionen) — зарезервировано для платной версии,
    # в бесплатный флоу не подключено. PART4 и build_p4_items оставлены готовыми к использованию.
    "p4": (
        "*И последний короткий раунд.*\n\n"
        "Одно и то же слово появится сначала с Akkusativ, потом с Dativ. "
        "Так легче увидеть разницу между формами.",
        "Начать",
    ),
}

PHASE_ORDER = ["p1", "p2", "p3"]  # p4 живёт в данных, но не в бесплатном флоу — см. комментарий выше
NEXT_PHASE = {"p1": "p2", "p2": "p3", "p3": None}


# ─────────────────────────────────────────────────────────
# CHEAT SHEET
# ─────────────────────────────────────────────────────────

CHEAT_SHEET_TEXT = (
    "*Таблица-шпаргалка*\n\n"
    "```\n"
    "Падеж       Maskulin   Feminin   Neutrum\n"
    "Nominativ   der/ein    die/eine  das/ein\n"
    "Akkusativ   den/einen  die/eine  das/ein\n"
    "Dativ       dem/einem  der/einer dem/einem\n"
    "```\n\n"
    "*Быстрая подсказка*\n\n"
    "Maskulin: der → den → dem\n"
    "Feminin: die → die → der\n"
    "Neutrum: das → das → dem"
)


# ─────────────────────────────────────────────────────────
# PRO OFFERS & FAKE DOORS (demand validation, no real payment)
# ─────────────────────────────────────────────────────────

ADMIN_USER_ID = 87350308
PRICE = "€7.90 / месяц"

OFFER3_TEXT = (
    "*Похоже, формат вам подходит :)*\n\n"
    "Я планирую полную версию «Артикли на автомате».\n\n"
    "В ней будут:\n"
    "— вся лексика A1–B1\n"
    "— множественное число в предложениях\n"
    "— задания без подсказки падежа\n"
    "— предлоги и глаголы с управлением\n"
    "— интервальные повторения\n"
    "— тренировки по тем словам и формам, где чаще возникают ошибки\n\n"
    "Планируемая подписка:\n"
    f"*{PRICE}*"
)

OFFER3_THANKS_TEXT = (
    "Спасибо! Полная версия пока готовится. "
    "Интерес отмечен — сообщу, когда можно будет попробовать."
)

OFFER10_TEXT = (
    "*Все 150 слов пройдены!*\n\n"
    "Если хочется продолжить, в полной версии будет вся лексика A1–B1, Plural, "
    "более сложные предложения, падежи без подсказок, предлоги и управление, "
    "интервальные повторения и персональные тренировки.\n\n"
    f"*{PRICE}*"
)

FAKE_DOOR_TEXT = {
    "nohint": (
        "*Без подсказки падежа* 🔒\n\n"
        "Здесь падеж не подсказан — его нужно определить по предлогу и смыслу самому:\n\n"
        "_Wir sprechen morgen mit ▢▢▢ neuen Kollegen über das Projekt._\n\n"
        "В полной версии будут задания, где падеж нужно определять по самому предложению."
    ),
    "plural": (
        "*Plural in Sätzen* 🔒\n\n"
        "Множественное число — прямо в предложениях, вместе с падежами и другими словами:\n\n"
        "_Im Büro stehen mehrere neue ▢▢▢._\n\n"
        "В полной версии множественное число будет тренироваться прямо в предложениях — "
        "вместе с артиклями, падежами и другими словами из списка."
    ),
    "hardwords": (
        "*Мои сложные слова* 🔒\n\n"
        "В полной версии бот будет запоминать слова и формы, в которых чаще возникают ошибки, "
        "и собирать отдельные тренировки именно по ним."
    ),
}

FAKE_DOOR_BUTTON_LABEL = {
    "nohint": "Хочу такой режим",
    "plural": "Хочу Plural",
    "hardwords": "Хочу такую тренировку",
}

FAKE_DOOR_MENU_LABEL = {
    "nohint": "🔒 Без подсказки падежа",
    "plural": "🔒 Plural in Sätzen",
    "hardwords": "🔒 Мои сложные слова",
}

FAKE_DOOR_THANKS_TEXT = "Записала! Дам знать, когда режим будет готов."

# Round-robin schedule: topic-completion-count → which fake door to show.
# Spread across 4–9 (never on 3 or 10, those are the real offers), so a user who
# finishes all 10 topics sees all three fake doors by the end, one per checkpoint.
FAKE_DOOR_SCHEDULE = {4: "nohint", 6: "plural", 8: "hardwords"}


# ─────────────────────────────────────────────────────────
# DATABASE (persistent progress — Postgres via DATABASE_URL)
#
# Optional by design: if DATABASE_URL isn't set or the connection fails,
# DB_POOL stays None and every function below transparently falls back
# to the old in-memory context.user_data behaviour. The bot never crashes
# because of the DB — worst case, progress just doesn't survive a restart,
# same as before this was added.
# ─────────────────────────────────────────────────────────

DB_POOL = None  # type: Optional["asyncpg.Pool"]

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    telegram_user_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

PROGRESS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS progress (
    telegram_user_id BIGINT NOT NULL REFERENCES users(telegram_user_id),
    topic_id TEXT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (telegram_user_id, topic_id)
);
"""

ADD_SOURCE_COLUMN_SQL = "ALTER TABLE users ADD COLUMN IF NOT EXISTS source TEXT;"

EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def init_db(app: Application) -> None:
    global DB_POOL
    if asyncpg is None:
        logger.warning("asyncpg not installed — progress will not be saved across restarts.")
        return
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set — progress will not be saved across restarts.")
        return
    try:
        DB_POOL = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
        async with DB_POOL.acquire() as conn:
            await conn.execute(USERS_TABLE_SQL)
            await conn.execute(PROGRESS_TABLE_SQL)
            await conn.execute(ADD_SOURCE_COLUMN_SQL)
            await conn.execute(EVENTS_TABLE_SQL)
        logger.info("Database connected, schema ensured — progress is now persistent.")
    except Exception as e:
        logger.error(f"Database connection failed, falling back to in-memory progress: {e}")
        DB_POOL = None


async def close_db(app: Application) -> None:
    if DB_POOL is not None:
        await DB_POOL.close()


async def touch_user(user_id: int, source: Optional[str] = None) -> None:
    if DB_POOL is None:
        return
    if source:
        # source is only ever written on first insert — ON CONFLICT branch below
        # never touches it, so a user's original source is preserved forever.
        await DB_POOL.execute(
            "INSERT INTO users (telegram_user_id, source) VALUES ($1, $2) "
            "ON CONFLICT (telegram_user_id) DO UPDATE SET last_seen_at = now()",
            user_id, source,
        )
    else:
        await DB_POOL.execute(
            "INSERT INTO users (telegram_user_id) VALUES ($1) "
            "ON CONFLICT (telegram_user_id) DO UPDATE SET last_seen_at = now()",
            user_id,
        )


async def log_event(user_id: int, event_type: str, payload: Optional[dict] = None) -> None:
    if DB_POOL is None:
        return
    await DB_POOL.execute(
        "INSERT INTO events (telegram_user_id, event_type, payload) VALUES ($1, $2, $3::jsonb)",
        user_id, event_type, json.dumps(payload) if payload is not None else None,
    )


async def has_errors(user_id: int) -> bool:
    if DB_POOL is None:
        return False
    return await DB_POOL.fetchval(
        "SELECT EXISTS(SELECT 1 FROM events WHERE telegram_user_id = $1 AND event_type = 'answer_incorrect')",
        user_id,
    )


async def db_get_completed(user_id: int) -> Optional[set]:
    """Returns None if the DB isn't available, so callers know to fall back."""
    if DB_POOL is None:
        return None
    rows = await DB_POOL.fetch(
        "SELECT topic_id FROM progress WHERE telegram_user_id = $1", user_id
    )
    return {r["topic_id"] for r in rows}


async def db_mark_completed(user_id: int, topic_id: str) -> None:
    if DB_POOL is None:
        return
    await touch_user(user_id)
    await DB_POOL.execute(
        "INSERT INTO progress (telegram_user_id, topic_id) VALUES ($1, $2) "
        "ON CONFLICT (telegram_user_id, topic_id) DO NOTHING",
        user_id, topic_id,
    )


async def db_reset_progress(user_id: int) -> None:
    if DB_POOL is None:
        return
    await DB_POOL.execute("DELETE FROM progress WHERE telegram_user_id = $1", user_id)


# ─────────────────────────────────────────────────────────
# CORE FLOW HELPERS
# ─────────────────────────────────────────────────────────

async def get_completed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> set:
    """Source of truth for 'which topics has this user finished'.
    Tries the DB first; falls back to context.user_data if the DB is unavailable."""
    from_db = await db_get_completed(user_id)
    if from_db is not None:
        return from_db
    ud = context.user_data
    if "completed" not in ud:
        ud["completed"] = set()
    return ud["completed"]


async def build_main_menu(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> InlineKeyboardMarkup:
    completed = await get_completed(context, user_id)
    show_hardwords = await has_errors(user_id)
    return kb_main_menu(completed, show_hardwords)


async def mark_completed(context: ContextTypes.DEFAULT_TYPE, user_id: int, topic_id: str) -> None:
    if DB_POOL is not None:
        await db_mark_completed(user_id, topic_id)
    else:
        ud = context.user_data
        if "completed" not in ud:
            ud["completed"] = set()
        ud["completed"].add(topic_id)


async def show_phase_intro(query, context: ContextTypes.DEFAULT_TYPE, phase: str) -> None:
    ud = context.user_data
    ud["phase"] = phase
    ud["idx"] = None
    ud["items"] = None
    text, label = PHASE_INTRO[phase]
    await query.edit_message_text(
        text, reply_markup=kb_intro(f"phase_go:{phase}", label), parse_mode="Markdown"
    )


async def start_phase_quiz(query, context: ContextTypes.DEFAULT_TYPE, phase: str) -> None:
    ud = context.user_data
    topic_id = ud["topic"]
    items = PHASE_BUILDERS[phase](topic_id)
    ud["phase"] = phase
    ud["items"] = items
    ud["idx"] = 0
    await send_question(query, context)


async def send_question(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    item = ud["items"][ud["idx"]]
    total = len(ud["items"])
    header = f"_{ud['idx'] + 1}/{total}_\n\n"
    await query.edit_message_text(
        header + item["prompt"], reply_markup=kb_options(item["options"]), parse_mode="Markdown"
    )


async def handle_answer(query, context: ContextTypes.DEFAULT_TYPE, chosen: str) -> None:
    ud = context.user_data
    item = ud["items"][ud["idx"]]
    correct = chosen == item["answer"]
    if not correct:
        await log_event(
            query.from_user.id, "answer_incorrect",
            {"topic": ud.get("topic"), "phase": ud.get("phase")},
        )
    icon = "✅" if correct else f"❌  (правильно: *{item['answer']}*)"
    if ud["phase"] == "p1" and "translation" in item:
        text = f"Твой ответ: *{chosen}* {icon}\n\n_{item['full']} — {item['translation']}_"
    else:
        text = f"Твой ответ: *{chosen}* {icon}\n\n{item['full']}"
    await query.edit_message_text(text, reply_markup=kb_continue(), parse_mode="Markdown")


async def advance(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    ud["idx"] += 1
    if ud["idx"] < len(ud["items"]):
        await send_question(query, context)
        return

    phase = ud["phase"]
    next_phase = NEXT_PHASE[phase]
    if next_phase:
        await show_phase_intro(query, context, next_phase)
    else:
        await finish_topic(query, context)


async def finish_topic(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    topic_id = ud["topic"]
    user_id = query.from_user.id
    await mark_completed(context, user_id, topic_id)
    completed = await get_completed(context, user_id)
    count = len(completed)
    # The topic is definitively over — clear the quiz session so "Назад к заданию"
    # from the cheat sheet (or anything else that resumes a session) can never
    # resurrect this finished topic later. Leaving this is what caused the bug
    # where reopening the cheat sheet days later dropped people back into an
    # already-completed topic's last section.
    ud["items"] = None
    ud["idx"] = None
    ud["phase"] = None
    ud["topic"] = None
    await log_event(user_id, "topic_complete", {"topic_id": topic_id, "total_completed": count})

    if count >= len(TOPIC_ORDER):
        await log_event(user_id, "offer10_shown")
        text = (
            "*Все 150 слов пройдены!*\n\n"
            "10 бытовых тем, определённый и неопределённый артикль, "
            "Nominativ, Akkusativ и Dativ — готово.\n\n"
            f"{random.choice(FINAL_VARIANTS)}\n\n"
            "Если хочется продолжить, в полной версии будет вся лексика A1–B1, Plural, "
            "более сложные предложения, падежи без подсказок, предлоги и управление, "
            "интервальные повторения и персональные тренировки.\n\n"
            f"*{PRICE}*"
        )
        await query.edit_message_text(text, reply_markup=kb_offer10(), parse_mode="Markdown")
        return

    if count == 3:
        await log_event(user_id, "offer3_shown")
        await query.edit_message_text(OFFER3_TEXT, reply_markup=kb_offer3(), parse_mode="Markdown")
        return

    # Round-robin: three fixed checkpoints spread across topics 4–9, one door each,
    # so a user who completes all 10 topics sees all three by the end (not all at once).
    # "hardwords" only fires for users who've actually made a mistake by then — if not,
    # we just skip that checkpoint rather than showing an irrelevant offer.
    door = FAKE_DOOR_SCHEDULE.get(count)
    if door and (door != "hardwords" or await has_errors(user_id)):
        await log_event(user_id, "fakedoor_shown", {"kind": door, "auto": True})
        await query.edit_message_text(FAKE_DOOR_TEXT[door], reply_markup=kb_fakedoor(door), parse_mode="Markdown")
        return

    praise = random.choice(PRAISE_VARIANTS)
    await query.edit_message_text(
        f"{praise}\n\nВыбери следующую тему:",
        reply_markup=await build_main_menu(context, user_id),
        parse_mode="Markdown",
    )


async def enter_topic(query, context: ContextTypes.DEFAULT_TYPE, topic_id: str) -> None:
    ud = context.user_data
    ud["topic"] = topic_id
    await log_event(query.from_user.id, "topic_start", {"topic_id": topic_id})
    await show_phase_intro(query, context, "p1")


# ─────────────────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    user_id = update.effective_user.id
    source = context.args[0] if context.args else None
    await touch_user(user_id, source)
    await log_event(user_id, "start", {"source": source} if source else None)
    await update.message.reply_text(
        "*Артикли на автомате*\n\n"
        "_150 бытовых слов + тренировка Nominativ, Akkusativ и Dativ_\n\n"
        "Знать, что *Tisch* — это *der Tisch*, ещё полдела. "
        "В речи он превращается в *den Tisch, dem Tisch, einen Tisch* или *einem Tisch*.\n\n"
        "Здесь будем тренировать именно это.",
        reply_markup=kb_start(),
        parse_mode="Markdown",
    )


async def reset_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["completed"] = set()
    await db_reset_progress(update.effective_user.id)
    await update.message.reply_text("Прогресс сброшен ✅", reply_markup=kb_main_menu(set()))


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        return
    if DB_POOL is None:
        await update.message.reply_text("БД не подключена — статистика недоступна.")
        return

    def pct(n: int, total: int) -> str:
        return f"{n} ({round(n / total * 100)}%)" if total else f"{n}"

    total_users = await DB_POOL.fetchval("SELECT COUNT(*) FROM users") or 0
    by_source = await DB_POOL.fetch(
        "SELECT COALESCE(source, '(без источника)') AS src, COUNT(*) AS n "
        "FROM users GROUP BY src ORDER BY n DESC"
    )
    started_topic = await DB_POOL.fetchval(
        "SELECT COUNT(DISTINCT telegram_user_id) FROM events WHERE event_type = 'topic_start'"
    ) or 0

    per_user_counts = await DB_POOL.fetch(
        "SELECT telegram_user_id, COUNT(*) AS n FROM progress GROUP BY telegram_user_id"
    )
    completed_1 = sum(1 for r in per_user_counts if r["n"] >= 1)
    completed_3 = sum(1 for r in per_user_counts if r["n"] >= 3)
    completed_10 = sum(1 for r in per_user_counts if r["n"] >= 10)

    async def distinct_users(event_type: str, extra_where: str = "") -> int:
        query = f"SELECT COUNT(DISTINCT telegram_user_id) FROM events WHERE event_type = $1 {extra_where}"
        return await DB_POOL.fetchval(query, event_type) or 0

    offer3_shown = await distinct_users("offer3_shown")
    offer3_click = await distinct_users("offer3_click_interested")
    offer10_shown = await distinct_users("offer10_shown")
    offer10_click = await distinct_users("offer10_click_want")
    fd_nohint = await DB_POOL.fetchval(
        "SELECT COUNT(DISTINCT telegram_user_id) FROM events "
        "WHERE event_type = 'fakedoor_click' AND payload->>'kind' = 'nohint'"
    ) or 0
    fd_plural = await DB_POOL.fetchval(
        "SELECT COUNT(DISTINCT telegram_user_id) FROM events "
        "WHERE event_type = 'fakedoor_click' AND payload->>'kind' = 'plural'"
    ) or 0
    fd_hardwords = await DB_POOL.fetchval(
        "SELECT COUNT(DISTINCT telegram_user_id) FROM events "
        "WHERE event_type = 'fakedoor_click' AND payload->>'kind' = 'hardwords'"
    ) or 0

    lines = [
        "*Статистика*", "",
        f"Всего пользователей: {total_users}", "",
        "*По источникам:*",
    ]
    for r in by_source:
        lines.append(f"— {r['src']}: {r['n']}")
    lines += [
        "",
        f"Начали хотя бы 1 тему: {pct(started_topic, total_users)}",
        f"Завершили ≥1 тему: {pct(completed_1, total_users)}",
        f"Завершили ≥3 темы: {pct(completed_3, total_users)}",
        f"Завершили все 10 тем: {pct(completed_10, total_users)}",
        "",
        f"Оффер после 3-й темы показан: {pct(offer3_shown, total_users)}",
        f"— «Мне интересно»: {pct(offer3_click, offer3_shown)}",
        f"Финальный оффер показан: {pct(offer10_shown, total_users)}",
        f"— «Хочу полную версию»: {pct(offer10_click, offer10_shown)}",
        "",
        f"Клик «без подсказки падежа»: {pct(fd_nohint, total_users)}",
        f"Клик «Plural»: {pct(fd_plural, total_users)}",
        f"Клик «сложные слова»: {pct(fd_hardwords, total_users)}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─────────────────────────────────────────────────────────
# CALLBACK HANDLERS
# ─────────────────────────────────────────────────────────

async def go_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    target = query.data.split(":", 1)[1]

    if target == "howto":
        await query.edit_message_text(
            "В боте 10 бытовых тем по 15 слов.\n\n"
            "В заданиях с падежами будет указано, какой нужен падеж: "
            "*Nominativ, Akkusativ или Dativ*.\n\n"
            "Сначала потренируем сами артикли, потом формы неопределённого артикля, "
            "затем перенесём всё это в предложения.\n\n"
            "Таблицу склонения можно открыть в любой момент.",
            reply_markup=kb_howto(),
            parse_mode="Markdown",
        )
    elif target == "menu":
        await query.edit_message_text(
            "Главное меню:", reply_markup=await build_main_menu(context, update.effective_user.id)
        )
    elif target == "cheat":
        await query.edit_message_text(CHEAT_SHEET_TEXT, reply_markup=kb_cheat_back(), parse_mode="Markdown")


async def render_current_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Redraws whatever screen the user was on before opening the cheat sheet,
    without resetting quiz progress (idx/items/phase stay untouched)."""
    ud = context.user_data
    items = ud.get("items")
    idx = ud.get("idx")
    if items is not None and idx is not None and idx < len(items):
        await send_question(query, context)
    elif ud.get("phase") is not None and ud.get("topic") is not None:
        text, label = PHASE_INTRO[ud["phase"]]
        await query.edit_message_text(
            text, reply_markup=kb_intro(f"phase_go:{ud['phase']}", label), parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            "Главное меню:", reply_markup=await build_main_menu(context, query.from_user.id)
        )


async def cheatmid_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(CHEAT_SHEET_TEXT, reply_markup=kb_cheat_back(), parse_mode="Markdown")


async def backcheat_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await render_current_screen(query, context)


async def offer3_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    if action == "interested":
        await log_event(user_id, "offer3_click_interested")
        await query.edit_message_text(
            OFFER3_THANKS_TEXT, reply_markup=await build_main_menu(context, user_id)
        )
    else:
        await log_event(user_id, "offer3_click_continue")
        await query.edit_message_text(
            "Главное меню:", reply_markup=await build_main_menu(context, user_id)
        )


async def offer10_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    if action == "want":
        await log_event(user_id, "offer10_click_want")
        await query.edit_message_text(
            OFFER3_THANKS_TEXT, reply_markup=await build_main_menu(context, user_id)
        )
    else:
        await log_event(user_id, "offer10_click_back")
        await query.edit_message_text(
            "Главное меню:", reply_markup=await build_main_menu(context, user_id)
        )


async def fakedoor_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Persistent 🔒 menu entry points — same screens as the automatic mid-course show."""
    query = update.callback_query
    await query.answer()
    kind = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    await log_event(user_id, "fakedoor_shown", {"kind": kind, "auto": False})
    await query.edit_message_text(FAKE_DOOR_TEXT[kind], reply_markup=kb_fakedoor(kind), parse_mode="Markdown")


async def fakedoor_click_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    kind = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    await log_event(user_id, "fakedoor_click", {"kind": kind})
    await query.edit_message_text(
        FAKE_DOOR_THANKS_TEXT, reply_markup=await build_main_menu(context, user_id)
    )


async def topic_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    topic_id = query.data.split(":", 1)[1]
    await enter_topic(query, context, topic_id)


async def phase_go_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    phase = query.data.split(":", 1)[1]
    await start_phase_quiz(query, context, phase)


async def answer_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chosen = query.data.split(":", 1)[1]
    await handle_answer(query, context, chosen)


async def continue_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await advance(query, context)


async def action_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Kept for forward-compatibility with any future action:* buttons; no branches active currently.
    query = update.callback_query
    await query.answer()


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global safety net: turns 'bot silently does nothing' into a visible,
    actionable message. Most likely trigger is a stale inline keyboard from
    before a restart, pointing at quiz state that no longer exists."""
    logger.error("Unhandled exception while processing an update", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.answer(
                "Что-то пошло не так — напиши /start заново", show_alert=True
            )
    except Exception:
        pass


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set.")

    app = Application.builder().token(token).post_init(init_db).post_shutdown(close_db).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_progress))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(go_router, pattern=r"^go:"))
    app.add_handler(CallbackQueryHandler(cheatmid_router, pattern=r"^cheatmid$"))
    app.add_handler(CallbackQueryHandler(backcheat_router, pattern=r"^backcheat$"))
    app.add_handler(CallbackQueryHandler(offer3_router, pattern=r"^offer3:"))
    app.add_handler(CallbackQueryHandler(offer10_router, pattern=r"^offer10:"))
    app.add_handler(CallbackQueryHandler(fakedoor_menu_router, pattern=r"^fakedoor:"))
    app.add_handler(CallbackQueryHandler(fakedoor_click_router, pattern=r"^fakedoor_click:"))
    app.add_handler(CallbackQueryHandler(topic_router, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(phase_go_router, pattern=r"^phase_go:"))
    app.add_handler(CallbackQueryHandler(answer_router, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(continue_router, pattern=r"^continue$"))
    app.add_handler(CallbackQueryHandler(action_router, pattern=r"^action:"))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
