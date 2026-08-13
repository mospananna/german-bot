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

# =========================================================
# "Артикли на автомате" — Telegram bot for practicing German articles
# Stack: python-telegram-bot v22+
# Run:
#   1) pip3 install -r requirements.txt
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
    "haus": ("🏠", "Дом и квартира"),
    "kueche": ("🍴", "Кухня и еда"),
    "bad": ("🚿", "Ванная и уход"),
    "kleidung": ("👕", "Одежда и обувь"),
    "stadt": ("🚇", "Город и транспорт"),
    "buero": ("💻", "Работа и офис"),
    "gesundheit": ("🩹", "Здоровье и врач"),
    "einkaufen": ("🛒", "Покупки и деньги"),
    "reisen": ("🧳", "Путешествия и свободное время"),
    "menschen": ("💬", "Люди и общение"),
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
        ("Schlüssel", "Akkusativ", "unbestimmt", "Ich suche ___ Schlüssel.", "einen"),
        ("Steckdose", "Dativ", "unbestimmt", "Neben ___ Steckdose steht eine Lampe.", "einer"),
        ("Regal", "Nominativ", "unbestimmt", "___ Regal steht im Wohnzimmer.", "Ein"),
        ("Teppich", "Dativ", "unbestimmt", "Die Katze liegt auf ___ Teppich.", "einem"),
        ("Schrank", "Akkusativ", "unbestimmt", "Wir kaufen ___ neuen Schrank.", "einen"),
        ("Boden", "Dativ", "bestimmt", "Die Schuhe stehen auf ___ Boden.", "dem"),
        ("Balkon", "Nominativ", "bestimmt", "___ Balkon ist ziemlich klein.", "Der"),
        ("Spiegel", "Akkusativ", "bestimmt", "Wir kaufen ___ Spiegel für den Flur.", "den"),
        ("Decke", "Dativ", "bestimmt", "An ___ Decke hängt eine Lampe.", "der"),
        ("Wand", "Akkusativ", "unbestimmt", "Wir streichen ___ Wand blau.", "eine"),
        ("Kissen", "Nominativ", "unbestimmt", "___ Kissen liegt auf dem Sofa.", "Ein"),
        ("Schublade", "Dativ", "unbestimmt", "In ___ Schublade liegt ein Messer.", "einer"),
        ("Fenster", "Akkusativ", "bestimmt", "Ich öffne ___ Fenster.", "das"),
        ("Flur", "Dativ", "bestimmt", "Die Schuhe stehen in ___ Flur.", "dem"),
        ("Treppe", "Nominativ", "bestimmt", "___ Treppe ist sehr steil.", "Die"),
    ],
    "kueche": [
        ("Butter", "Nominativ", "bestimmt", "___ Butter ist im Kühlschrank.", "Die"),
        ("Joghurt", "Akkusativ", "unbestimmt", "Ich kaufe ___ Joghurt.", "einen"),
        ("Öl", "Dativ", "bestimmt", "Wir kochen mit ___ Öl.", "dem"),
        ("Reis", "Akkusativ", "bestimmt", "Ich koche ___ Reis.", "den"),
        ("Gemüse", "Nominativ", "bestimmt", "___ Gemüse ist frisch.", "Das"),
        ("Salat", "Dativ", "unbestimmt", "Ich esse Brot zu ___ Salat.", "einem"),
        ("Löffel", "Akkusativ", "unbestimmt", "Ich nehme ___ Löffel.", "einen"),
        ("Käse", "Nominativ", "unbestimmt", "___ Käse schmeckt gut.", "Ein"),
        ("Marmelade", "Akkusativ", "unbestimmt", "Ich streiche ___ Marmelade aufs Brot.", "eine"),
        ("Mehl", "Dativ", "bestimmt", "Wir backen mit ___ Mehl.", "dem"),
        ("Zucker", "Akkusativ", "bestimmt", "Ich brauche ___ Zucker für den Kuchen.", "den"),
        ("Zwiebel", "Nominativ", "unbestimmt", "___ Zwiebel liegt neben der Tomate.", "Eine"),
        ("Knoblauch", "Dativ", "bestimmt", "Die Soße schmeckt nach ___ Knoblauch.", "dem"),
        ("Ei", "Akkusativ", "bestimmt", "Ich koche ___ Ei.", "das"),
        ("Messer", "Nominativ", "unbestimmt", "___ Messer liegt auf dem Tisch.", "Ein"),
    ],
    "bad": [
        ("Shampoo", "Nominativ", "bestimmt", "___ Shampoo ist nicht so gut.", "Das"),
        ("Seife", "Akkusativ", "unbestimmt", "Ich kaufe ___ Seife.", "eine"),
        ("Creme", "Dativ", "bestimmt", "Ich bin zufrieden mit ___ Creme.", "der"),
        ("Handtuch", "Akkusativ", "unbestimmt", "Ich nehme ___ Handtuch.", "ein"),
        ("Duschgel", "Nominativ", "bestimmt", "___ Duschgel riecht nach Zitrone.", "Das"),
        ("Zahnbürste", "Dativ", "bestimmt", "Ich putze die Zähne mit ___ Zahnbürste.", "der"),
        ("Kamm", "Akkusativ", "unbestimmt", "Ich nehme ___ Kamm.", "einen"),
        ("Bürste", "Nominativ", "bestimmt", "___ Bürste liegt im Bad.", "Die"),
        ("Rasierer", "Akkusativ", "unbestimmt", "Ich kaufe ___ neuen Rasierer.", "einen"),
        ("Waschbecken", "Dativ", "unbestimmt", "Die Seife liegt neben ___ Waschbecken.", "einem"),
        ("Dusche", "Akkusativ", "bestimmt", "Ich putze ___ Dusche.", "die"),
        ("Badewanne", "Nominativ", "bestimmt", "___ Badewanne ist sehr groß.", "Die"),
        ("Toilettenpapier", "Dativ", "bestimmt", "Neben ___ Toilettenpapier liegt ein Handtuch.", "dem"),
        ("Föhn", "Akkusativ", "unbestimmt", "Ich brauche ___ Föhn.", "einen"),
        ("Abfluss", "Nominativ", "unbestimmt", "___ Abfluss ist verstopft.", "Ein"),
    ],
    "kleidung": [
        ("Pullover", "Nominativ", "unbestimmt", "___ Pullover ist warm.", "Ein"),
        ("Hemd", "Akkusativ", "bestimmt", "Ich kaufe ___ Hemd.", "das"),
        ("Hose", "Dativ", "bestimmt", "Der Fleck ist an ___ Hose.", "der"),
        ("Gürtel", "Akkusativ", "bestimmt", "Ich trage ___ Gürtel.", "den"),
        ("Sakko", "Nominativ", "unbestimmt", "___ Sakko passt gut.", "Ein"),
        ("Mantel", "Dativ", "unbestimmt", "Ich stehe mit ___ Mantel an der Tür.", "einem"),
        ("Kleid", "Akkusativ", "unbestimmt", "Ich ziehe ___ Kleid an.", "ein"),
        ("Rock", "Nominativ", "unbestimmt", "___ Rock ist zu lang.", "Ein"),
        ("Handschuh", "Akkusativ", "bestimmt", "Ich verliere ___ Handschuh.", "den"),
        ("Schuh", "Dativ", "unbestimmt", "Ein Stein ist in ___ Schuh.", "einem"),
        ("Stiefel", "Nominativ", "bestimmt", "___ Stiefel steht im Flur.", "Der"),
        ("Mütze", "Akkusativ", "bestimmt", "Ich setze ___ Mütze auf.", "die"),
        ("Schal", "Dativ", "unbestimmt", "An ___ Schal hängt ein Preisschild.", "einem"),
        ("Bluse", "Akkusativ", "bestimmt", "Ich kaufe ___ Bluse.", "die"),
        ("T-Shirt", "Nominativ", "bestimmt", "___ T-Shirt ist zu klein.", "Das"),
    ],
    "stadt": [
        ("Bürgersteig", "Nominativ", "bestimmt", "___ Bürgersteig ist nass.", "Der"),
        ("Bahn", "Akkusativ", "bestimmt", "Ich nehme ___ Bahn.", "die"),
        ("Haltestelle", "Dativ", "unbestimmt", "Ich warte an ___ Haltestelle.", "einer"),
        ("Bahnhof", "Akkusativ", "bestimmt", "Ich sehe ___ Bahnhof von hier.", "den"),
        ("Taxi", "Nominativ", "bestimmt", "___ Taxi steht vor der Tür.", "Das"),
        ("Verkehr", "Nominativ", "bestimmt", "___ Verkehr ist heute sehr dicht.", "Der"),
        ("Eingang", "Akkusativ", "unbestimmt", "Ich suche ___ Eingang.", "einen"),
        ("Weg", "Nominativ", "unbestimmt", "___ Weg ist sehr lang.", "Ein"),
        ("Kreuzung", "Dativ", "bestimmt", "An ___ Kreuzung ist ein Unfall passiert.", "der"),
        ("Ampel", "Akkusativ", "bestimmt", "Ich sehe ___ Ampel nicht.", "die"),
        ("Parkplatz", "Nominativ", "unbestimmt", "___ Parkplatz ist frei.", "Ein"),
        ("Fahrrad", "Akkusativ", "unbestimmt", "Ich kaufe ___ Fahrrad.", "ein"),
        ("Zug", "Dativ", "bestimmt", "Ich fahre mit ___ Zug.", "dem"),
        ("U-Bahn", "Akkusativ", "bestimmt", "Ich nehme ___ U-Bahn.", "die"),
        ("Führerschein", "Nominativ", "unbestimmt", "___ Führerschein ist noch gültig.", "Ein"),
    ],
    "buero": [
        ("Büro", "Nominativ", "bestimmt", "___ Büro ist im dritten Stock.", "Das"),
        ("Termin", "Akkusativ", "unbestimmt", "Ich habe ___ Termin um zehn Uhr.", "einen"),
        ("E-Mail", "Dativ", "bestimmt", "Der Anhang ist in ___ E-Mail.", "der"),
        ("Vertrag", "Akkusativ", "bestimmt", "Ich unterschreibe ___ Vertrag.", "den"),
        ("Besprechung", "Nominativ", "unbestimmt", "___ Besprechung beginnt gleich.", "Eine"),
        ("Abteilung", "Dativ", "unbestimmt", "Er arbeitet in ___ anderen Abteilung.", "einer"),
        ("Frist", "Akkusativ", "bestimmt", "Wir verpassen ___ Frist.", "die"),
        ("Gehalt", "Nominativ", "bestimmt", "___ Gehalt kommt am Monatsende.", "Das"),
        ("Aufgabe", "Akkusativ", "unbestimmt", "Ich bekomme ___ neue Aufgabe.", "eine"),
        ("Projekt", "Dativ", "unbestimmt", "Wir arbeiten an ___ Projekt.", "einem"),
        ("Drucker", "Nominativ", "bestimmt", "___ Drucker funktioniert nicht.", "Der"),
        ("Bildschirm", "Akkusativ", "bestimmt", "Ich putze ___ Bildschirm.", "den"),
        ("Tastatur", "Dativ", "bestimmt", "Ich tippe mit ___ neuen Tastatur.", "der"),
        ("Dokument", "Akkusativ", "unbestimmt", "Ich unterschreibe ___ Dokument.", "ein"),
        ("Auftrag", "Nominativ", "bestimmt", "___ Auftrag ist sehr wichtig.", "Der"),
    ],
    "gesundheit": [
        ("Schmerz", "Nominativ", "bestimmt", "___ Schmerz kommt und geht.", "Der"),
        ("Husten", "Akkusativ", "unbestimmt", "Ich habe ___ starken Husten.", "einen"),
        ("Medikament", "Dativ", "bestimmt", "Ich helfe mit ___ Medikament.", "dem"),
        ("Rezept", "Akkusativ", "unbestimmt", "Ich hole ___ Rezept ab.", "ein"),
        ("Untersuchung", "Nominativ", "unbestimmt", "___ Untersuchung dauert eine Stunde.", "Eine"),
        ("Praxis", "Dativ", "unbestimmt", "Ich warte in ___ vollen Praxis.", "einer"),
        ("Verband", "Akkusativ", "unbestimmt", "Die Ärztin wechselt ___ Verband.", "einen"),
        ("Apotheke", "Nominativ", "bestimmt", "___ Apotheke ist gleich um die Ecke.", "Die"),
        ("Fieber", "Akkusativ", "unbestimmt", "Ich habe ___ hohes Fieber.", "ein"),
        ("Erkältung", "Dativ", "unbestimmt", "Ich leide an ___ Erkältung.", "einer"),
        ("Rücken", "Nominativ", "bestimmt", "___ Rücken tut weh.", "Der"),
        ("Salbe", "Akkusativ", "bestimmt", "Ich kaufe ___ Salbe.", "die"),
        ("Symptom", "Nominativ", "bestimmt", "___ Symptom ist harmlos.", "Das"),
        ("Tablette", "Dativ", "bestimmt", "Ich helfe mir mit ___ Tablette.", "der"),
        ("Pflaster", "Akkusativ", "unbestimmt", "Ich klebe ___ Pflaster auf die Wunde.", "ein"),
    ],
    "einkaufen": [
        ("Preis", "Nominativ", "bestimmt", "___ Preis ist zu hoch.", "Der"),
        ("Angebot", "Akkusativ", "unbestimmt", "Ich nutze ___ Angebot.", "ein"),
        ("Rechnung", "Dativ", "bestimmt", "Der Betrag steht auf ___ Rechnung.", "der"),
        ("Rabatt", "Akkusativ", "unbestimmt", "Ich bekomme ___ Rabatt.", "einen"),
        ("Kasse", "Nominativ", "unbestimmt", "___ Kasse ist gerade frei.", "Eine"),
        ("Gebühr", "Dativ", "bestimmt", "Ich zahle mit ___ zusätzlichen Gebühr.", "der"),
        ("Einkauf", "Akkusativ", "bestimmt", "Ich trage ___ Einkauf nach Hause.", "den"),
        ("Laden", "Nominativ", "unbestimmt", "___ Laden schließt um acht.", "Ein"),
        ("Geschäft", "Akkusativ", "bestimmt", "Ich eröffne ___ Geschäft.", "das"),
        ("Quittung", "Dativ", "bestimmt", "Ich brauche eine Kopie von ___ Quittung.", "der"),
        ("Betrag", "Nominativ", "bestimmt", "___ Betrag ist falsch.", "Der"),
        ("Karte", "Akkusativ", "unbestimmt", "Ich nehme ___ Karte.", "eine"),
        ("Bargeld", "Dativ", "bestimmt", "Ich zahle mit ___ Bargeld.", "dem"),
        ("Cent", "Nominativ", "unbestimmt", "___ Cent liegt auf dem Boden.", "Ein"),
        ("Wechselgeld", "Akkusativ", "bestimmt", "Ich zähle ___ Wechselgeld.", "das"),
    ],
    "reisen": [
        ("Urlaub", "Nominativ", "bestimmt", "___ Urlaub beginnt morgen.", "Der"),
        ("Reise", "Akkusativ", "unbestimmt", "Ich plane ___ Reise.", "eine"),
        ("Buchung", "Dativ", "unbestimmt", "Es gibt ein Problem mit ___ Buchung.", "einer"),
        ("Ausflug", "Akkusativ", "bestimmt", "Wir machen ___ Ausflug.", "den"),
        ("Freizeit", "Nominativ", "bestimmt", "___ Freizeit ist mir wichtig.", "Die"),
        ("Koffer", "Akkusativ", "unbestimmt", "Ich packe ___ Koffer.", "einen"),
        ("Tasche", "Dativ", "unbestimmt", "Der Pass ist in ___ Tasche.", "einer"),
        ("Pass", "Akkusativ", "bestimmt", "Ich zeige ___ Pass.", "den"),
        ("Ticket", "Nominativ", "unbestimmt", "___ Ticket liegt auf dem Tisch.", "Ein"),
        ("Unterkunft", "Dativ", "bestimmt", "Ich bin zufrieden mit ___ Unterkunft.", "der"),
        ("Strand", "Nominativ", "bestimmt", "___ Strand ist leer.", "Der"),
        ("Meer", "Dativ", "bestimmt", "Wir wohnen nah an ___ Meer.", "dem"),
        ("Grenze", "Akkusativ", "bestimmt", "Wir sehen schon ___ Grenze.", "die"),
        ("Wanderung", "Nominativ", "unbestimmt", "___ Wanderung dauert sechs Stunden.", "Eine"),
        ("Gepäck", "Akkusativ", "bestimmt", "Ich hole ___ Gepäck ab.", "das"),
    ],
    "menschen": [
        ("Mensch", "Nominativ", "bestimmt", "___ Mensch wartet vor der Tür.", "Der"),
        ("Person", "Akkusativ", "unbestimmt", "Ich kenne ___ Person nicht.", "eine"),
        ("Kontakt", "Dativ", "unbestimmt", "Ich stehe mit ___ Kontakt in Verbindung.", "einem"),
        ("Bekannte", "Akkusativ", "unbestimmt", "Ich treffe ___ Bekannten.", "einen"),
        ("Bekanntschaft", "Nominativ", "unbestimmt", "___ Bekanntschaft war kurz.", "Eine"),
        ("Gast", "Dativ", "bestimmt", "Ich zeige ___ Gast das Zimmer.", "dem"),
        ("Besuch", "Akkusativ", "bestimmt", "Wir planen ___ Besuch.", "den"),
        ("Gespräch", "Nominativ", "bestimmt", "___ Gespräch war sehr offen.", "Das"),
        ("Nachricht", "Akkusativ", "bestimmt", "Ich schreibe ___ Nachricht.", "die"),
        ("Anruf", "Akkusativ", "unbestimmt", "Ich bekomme ___ Anruf.", "einen"),
        ("Verhalten", "Dativ", "bestimmt", "Wir sind überrascht von ___ Verhalten.", "dem"),
        ("Eindruck", "Nominativ", "unbestimmt", "___ Eindruck war positiv.", "Ein"),
        ("Einladung", "Akkusativ", "bestimmt", "Ich bekomme ___ Einladung.", "die"),
        ("Beziehung", "Dativ", "unbestimmt", "Sie ist in ___ neuen Beziehung.", "einer"),
        ("Paar", "Nominativ", "unbestimmt", "___ Paar sitzt im Café.", "Ein"),
    ],
}

# ─────────────────────────────────────────────────────────
# PART 4 — Akkusativ/Dativ contrast pairs (Wechselpräpositionen)
# Each entry: header word, akk (template, answer), dat (template, answer)
# ─────────────────────────────────────────────────────────

PART4: Dict[str, List[dict]] = {
    "haus": [
        {"word": "der Teppich", "type": "unbestimmt", "akk": ("Ich lege das Kissen auf ___ Teppich.", "einen"), "dat": ("Das Kissen liegt auf ___ Teppich.", "einem")},
        {"word": "die Wand", "type": "bestimmt", "akk": ("Wir hängen das Bild an ___ Wand.", "die"), "dat": ("Das Bild hängt an ___ Wand.", "der")},
        {"word": "das Regal", "type": "unbestimmt", "akk": ("Ich stelle die Bücher in ___ Regal.", "ein"), "dat": ("Die Bücher stehen in ___ Regal.", "einem")},
        {"word": "der Balkon", "type": "bestimmt", "akk": ("Wir stellen einen Tisch auf ___ Balkon.", "den"), "dat": ("Der Tisch steht auf ___ Balkon.", "dem")},
    ],
    "kueche": [
        {"word": "der Topf", "type": "unbestimmt", "akk": ("Ich lege das Ei in ___ Topf.", "einen"), "dat": ("Das Ei liegt in ___ Topf.", "einem")},
        {"word": "die Pfanne", "type": "bestimmt", "akk": ("Ich lege das Gemüse in ___ Pfanne.", "die"), "dat": ("Das Gemüse liegt in ___ Pfanne.", "der")},
        {"word": "der Kühlschrank", "type": "unbestimmt", "akk": ("Ich lege den Käse in ___ Kühlschrank.", "einen"), "dat": ("Der Käse liegt in ___ Kühlschrank.", "einem")},
    ],
    "bad": [
        {"word": "das Waschbecken", "type": "bestimmt", "akk": ("Ich lege die Seife auf ___ Waschbecken.", "das"), "dat": ("Die Seife liegt auf ___ Waschbecken.", "dem")},
        {"word": "die Dusche", "type": "unbestimmt", "akk": ("Ich stelle das Shampoo in ___ Dusche.", "eine"), "dat": ("Das Shampoo steht in ___ Dusche.", "einer")},
        {"word": "die Badewanne", "type": "bestimmt", "akk": ("Ich setze mich in ___ Badewanne.", "die"), "dat": ("Ich sitze in ___ Badewanne.", "der")},
    ],
    "kleidung": [
        {"word": "der Haken", "type": "unbestimmt", "akk": ("Ich hänge den Mantel an ___ Haken.", "einen"), "dat": ("Der Mantel hängt an ___ Haken.", "einem")},
        {"word": "der Schrank", "type": "bestimmt", "akk": ("Ich lege das Kleid in ___ Schrank.", "den"), "dat": ("Das Kleid liegt in ___ Schrank.", "dem")},
        {"word": "die Tür", "type": "bestimmt", "akk": ("Ich stelle den Schuh vor ___ Tür.", "die"), "dat": ("Der Schuh steht vor ___ Tür.", "der")},
    ],
    "stadt": [
        {"word": "der Bahnhof", "type": "unbestimmt", "akk": ("Ich gehe in ___ Bahnhof.", "einen"), "dat": ("Ich bin in ___ Bahnhof.", "einem")},
        {"word": "die Kreuzung", "type": "bestimmt", "akk": ("Das Auto fährt an ___ Kreuzung.", "die"), "dat": ("Das Auto steht an ___ Kreuzung.", "der")},
        {"word": "der Parkplatz", "type": "unbestimmt", "akk": ("Ich fahre auf ___ Parkplatz.", "einen"), "dat": ("Das Auto steht auf ___ Parkplatz.", "einem")},
    ],
    "buero": [
        {"word": "das Büro", "type": "bestimmt", "akk": ("Ich gehe in ___ Büro.", "das"), "dat": ("Ich bin in ___ Büro.", "dem")},
        {"word": "der Schreibtisch", "type": "unbestimmt", "akk": ("Ich lege das Dokument auf ___ Schreibtisch.", "einen"), "dat": ("Das Dokument liegt auf ___ Schreibtisch.", "einem")},
        {"word": "der Ordner", "type": "unbestimmt", "akk": ("Ich lege die Akte in ___ Ordner.", "einen"), "dat": ("Die Akte liegt in ___ Ordner.", "einem")},
    ],
    "gesundheit": [
        {"word": "die Apotheke", "type": "unbestimmt", "akk": ("Ich gehe in ___ Apotheke.", "eine"), "dat": ("Ich bin in ___ Apotheke.", "einer")},
        {"word": "die Praxis", "type": "bestimmt", "akk": ("Ich gehe in ___ Praxis.", "die"), "dat": ("Ich warte in ___ Praxis.", "der")},
        {"word": "der Rücken", "type": "bestimmt", "akk": ("Ich lege die Hand auf ___ Rücken.", "den"), "dat": ("Die Hand liegt auf ___ Rücken.", "dem")},
    ],
    "einkaufen": [
        {"word": "der Laden", "type": "unbestimmt", "akk": ("Ich gehe in ___ Laden.", "einen"), "dat": ("Ich bin in ___ Laden.", "einem")},
        {"word": "die Kasse", "type": "bestimmt", "akk": ("Ich stelle mich an ___ Kasse.", "die"), "dat": ("Ich stehe an ___ Kasse.", "der")},
        {"word": "das Geschäft", "type": "unbestimmt", "akk": ("Ich gehe in ___ Geschäft.", "ein"), "dat": ("Ich arbeite in ___ Geschäft.", "einem")},
    ],
    "reisen": [
        {"word": "der Koffer", "type": "unbestimmt", "akk": ("Ich lege das T-Shirt in ___ Koffer.", "einen"), "dat": ("Das T-Shirt liegt in ___ Koffer.", "einem")},
        {"word": "die Tasche", "type": "bestimmt", "akk": ("Ich stecke den Pass in ___ Tasche.", "die"), "dat": ("Der Pass steckt in ___ Tasche.", "der")},
        {"word": "das Meer", "type": "bestimmt", "akk": ("Wir gehen in ___ Meer.", "das"), "dat": ("Wir schwimmen in ___ Meer.", "dem")},
    ],
    "menschen": [
        {"word": "der Kontakt", "type": "bestimmt", "akk": ("Wir kommen in ___ Kontakt.", "den"), "dat": ("Wir bleiben in ___ Kontakt.", "dem")},
        {"word": "das Gespräch", "type": "bestimmt", "akk": ("Wir kommen in ___ Gespräch.", "das"), "dat": ("Wir sind in ___ Gespräch vertieft.", "dem")},
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
    "Dem и einem уже не так страшно встречаться с тобой в тёмном переулке.",
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


def kb_main_menu(completed: set) -> InlineKeyboardMarkup:
    rows = []
    for tid in TOPIC_ORDER:
        emoji, title = TOPIC_META[tid]
        mark = " ✅" if tid in completed else ""
        rows.append([InlineKeyboardButton(f"{emoji} {title}{mark}", callback_data=f"topic:{tid}")])
    rows.append([InlineKeyboardButton("🔠 Таблица артиклей", callback_data="go:cheat")])
    return InlineKeyboardMarkup(rows)


def kb_cheat_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад к заданию", callback_data="go:menu")]])


def kb_intro(callback: str, label: str = "Начать") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=callback)]])


def kb_options(options: List[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(o, callback_data=f"answer:{o}")] for o in options])


def kb_continue() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Дальше ▶️", callback_data="continue")]])


def kb_after_topic(finished_all: bool) -> InlineKeyboardMarkup:
    if finished_all:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🏁 Итог", callback_data="action:final")]])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Следующая тема", callback_data="action:next_topic")],
        [InlineKeyboardButton("К списку тем", callback_data="go:menu")],
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
            "prompt": f"___ {w.word}",
            "options": options,
            "answer": w.artikel,
            "word": w.word,
            "translation": w.translation,
        })
    return items


def build_p2_items(topic_id: str) -> List[dict]:
    words = WORDS[topic_id]
    cases = ["Nominativ", "Akkusativ", "Dativ"]
    pick_indices = [0, 3, 6, 9, 12, 7]
    items = []
    for i, idx in enumerate(pick_indices):
        w = words[idx % len(words)]
        case = cases[i % 3]
        gender = GENDER[w.artikel]
        def_form = DEFINITE[gender][case]
        answer = INDEFINITE[gender][case]
        options = build_options(answer, "indef")
        prompt = (
            f"*{w.artikel} {w.word}* · {case}\n\n"
            f"С определённым артиклем:\n\n*{def_form} {w.word}*\n\n"
            f"А с неопределённым?"
        )
        items.append({"prompt": prompt, "options": options, "answer": answer})
    return items


def build_p3_items(topic_id: str) -> List[dict]:
    items = []
    for word, case, atype, template, answer in PART3[topic_id]:
        kind = "def" if atype == "bestimmt" else "indef"
        options = build_options(answer, kind)
        art_label = "bestimmter" if atype == "bestimmt" else "unbestimmter"
        prompt = f"*{case} · {art_label} Artikel*\n\n{template}"
        items.append({"prompt": prompt, "options": options, "answer": answer})
    return items


def build_p4_items(topic_id: str) -> List[dict]:
    items = []
    for pair in PART4[topic_id]:
        kind = "def" if pair.get("type", "bestimmt") == "bestimmt" else "indef"
        for case_name, (template, answer) in (("Akkusativ", pair["akk"]), ("Dativ", pair["dat"])):
            options = build_options(answer, kind)
            prompt = f"*{pair['word']}*\n\n*{case_name}*\n\n{template}"
            items.append({"prompt": prompt, "options": options, "answer": answer})
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
# CORE FLOW HELPERS
# ─────────────────────────────────────────────────────────

def get_completed(ud: dict) -> set:
    if "completed" not in ud:
        ud["completed"] = set()
    return ud["completed"]


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
    icon = "✅" if correct else f"❌  (правильно: *{item['answer']}*)"
    extra = ""
    if ud["phase"] == "p1" and "translation" in item:
        extra = f"\n\n_{item['word']} — {item['translation']}_"
    text = f"{item['prompt']}\n\nТвой ответ: *{chosen}* {icon}{extra}"
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
    completed = get_completed(ud)
    completed.add(topic_id)

    if len(completed) >= len(TOPIC_ORDER):
        await query.edit_message_text(
            "*Все 150 слов пройдены!*\n\n"
            "10 бытовых тем, определённый и неопределённый артикль, "
            "Nominativ, Akkusativ и Dativ — готово.\n\n"
            f"{random.choice(FINAL_VARIANTS)}",
            reply_markup=kb_main_menu(completed),
            parse_mode="Markdown",
        )
        return

    praise = random.choice(PRAISE_VARIANTS)
    await query.edit_message_text(
        praise, reply_markup=kb_after_topic(False), parse_mode="Markdown"
    )


def next_uncompleted_topic(completed: set) -> Optional[str]:
    for tid in TOPIC_ORDER:
        if tid not in completed:
            return tid
    return None


async def enter_topic(query, context: ContextTypes.DEFAULT_TYPE, topic_id: str) -> None:
    ud = context.user_data
    ud["topic"] = topic_id
    await show_phase_intro(query, context, "p1")


# ─────────────────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
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
    await update.message.reply_text("Прогресс сброшен ✅", reply_markup=kb_main_menu(set()))


# ─────────────────────────────────────────────────────────
# CALLBACK HANDLERS
# ─────────────────────────────────────────────────────────

async def go_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    target = query.data.split(":", 1)[1]
    ud = context.user_data

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
        completed = get_completed(ud)
        await query.edit_message_text("Главное меню:", reply_markup=kb_main_menu(completed))
    elif target == "cheat":
        await query.edit_message_text(CHEAT_SHEET_TEXT, reply_markup=kb_cheat_back(), parse_mode="Markdown")


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
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    ud = context.user_data
    completed = get_completed(ud)

    if action == "next_topic":
        nxt = next_uncompleted_topic(completed)
        if nxt is None:
            await query.edit_message_text(
                "*Все 150 слов пройдены!*\n\n"
                f"{random.choice(FINAL_VARIANTS)}",
                reply_markup=kb_main_menu(completed),
                parse_mode="Markdown",
            )
        else:
            await enter_topic(query, context, nxt)
    elif action == "final":
        await query.edit_message_text("Главное меню:", reply_markup=kb_main_menu(completed))


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_progress))
    app.add_handler(CallbackQueryHandler(go_router, pattern=r"^go:"))
    app.add_handler(CallbackQueryHandler(topic_router, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(phase_go_router, pattern=r"^phase_go:"))
    app.add_handler(CallbackQueryHandler(answer_router, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(continue_router, pattern=r"^continue$"))
    app.add_handler(CallbackQueryHandler(action_router, pattern=r"^action:"))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
