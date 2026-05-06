# ============================================================
# User-Feedback-Speicher fuer FitMyTrip
# ============================================================
# Erlaubt, Bewertungen (1-5 Sterne) zu Empfehlungen lokal zu
# speichern. Diese Bewertungen fliessen beim naechsten Modell-
# Training in die Trainingsdaten ein und verbessern so die
# Empfehlungen ueber die Zeit.
#
# Die Daten werden in einer einfachen JSON-Datei abgelegt. Das
# reicht fuer ein Studienprojekt; in einer Produktivversion wuerde
# man eine richtige Datenbank verwenden.

import json
from pathlib import Path
from datetime import datetime


# JSON-Datei liegt im gleichen Ordner wie der Code
FEEDBACK_PATH = Path(__file__).parent / "user_feedback.json"


def lade_feedback():
    # Liest alle bisherigen Feedback-Eintraege aus der JSON-Datei.
    # Wenn die Datei nicht existiert oder kaputt ist, wird eine leere
    # Liste zurueckgegeben (so haben wir nie einen Crash beim ersten
    # Aufruf, bevor noch nichts gespeichert wurde).
    if not FEEDBACK_PATH.exists():
        return []
    try:
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def speichere_feedback(eintrag):
    # Fuegt einen neuen Feedback-Eintrag hinzu.
    # Erwartetes Format des Eintrags:
    # {
    #   "user_inputs": { wunsch_temp, budget, reisetage },
    #   "destination": "Lissabon",
    #   "destination_features": { dest_temp, dest_tageskosten,
    #                              dest_sicherheit, dest_flugzeit },
    #   "rating_stars": 1..5,
    # }
    feedback = lade_feedback()
    eintrag["timestamp"] = datetime.now().isoformat()
    feedback.append(eintrag)

    with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(feedback, f, indent=2, ensure_ascii=False)

    return len(feedback)


def anzahl_feedback():
    # Wie viele Bewertungen sind bereits gespeichert? Praktisch fuer
    # die Anzeige in der App ("Bisher 12 Bewertungen gesammelt").
    return len(lade_feedback())


# ============================================================
# Testblock
# ============================================================
if __name__ == "__main__":
    print(f"Aktuell {anzahl_feedback()} Feedback-Eintraege gespeichert.")
    print(f"Pfad: {FEEDBACK_PATH}")