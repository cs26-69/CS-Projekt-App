# ============================================================
# Wetter-API fuer FitMyTrip
# ============================================================
# Dieses Modul holt Temperaturdaten ueber die Open-Meteo API.
# Open-Meteo ist gratis und braucht keinen API-Key.
#
# Zweck: Fuer einen Ort und einen Reisezeitraum gibt uns die
# Hauptfunktion EINEN einzigen Wert zurueck – die erwartete
# Durchschnittstemperatur in Grad Celsius.
# Diesen Wert brauchen wir spaeter fuer das Matching mit der
# Temperatur-Praeferenz der Nutzer:innen (z.B. "ich mag 20-25 °C").
#
# Warum der Umweg ueber historische Daten?
# Reisen werden meistens Wochen oder Monate im Voraus geplant.
# Eine "echte" Wettervorhersage geht aber nur 16 Tage in die Zukunft.
# Darum schaetzen wir die erwartete Temperatur ueber den Durchschnitt
# der letzten 5 Jahre im gleichen Zeitraum (selber Monat, selber Tag).
# Das gibt eine stabilere Schaetzung als nur ein einzelnes Vorjahr.
 
import requests
from datetime import date, datetime
 
 
# URLs der beiden Open-Meteo Endpunkte, die wir brauchen
# - GEO_URL:    wandelt einen Ortsnamen (z.B. "Madrid") in Koordinaten um
# - ARCHIV_URL: liefert historische Wetterdaten zu gegebenen Koordinaten
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIV_URL = "https://archive-api.open-meteo.com/v1/archive"
 
# Anzahl vergangener Jahre, ueber die der Durchschnitt gebildet wird.
# Als Konstante, damit wir die Zahl spaeter leicht anpassen koennen
# (z.B. auf 3 oder 10), ohne den restlichen Code zu veraendern.
ANZAHL_JAHRE = 5
 
 
def finde_koordinaten(ort):
    # Sucht Laengen- und Breitengrad zu einem Ortsnamen.
    # Brauchen wir, weil die Wetter-API nur mit Koordinaten arbeitet,
    # nicht direkt mit Ortsnamen.
 
    # Parameter fuer die Geocoding-Anfrage:
    # - name:     der Ortsname, den wir suchen
    # - count=1:  wir nehmen nur den besten Treffer (reicht uns)
    # - language: Ergebnisse in Deutsch (z.B. "Spanien" statt "Spain")
    params = {"name": ort, "count": 1, "language": "de"}
 
    # Anfrage an die API schicken und Antwort als JSON einlesen
    antwort = requests.get(GEO_URL, params=params)
    daten = antwort.json()
 
    # Wenn die API nichts gefunden hat, fehlt das Feld "results".
    # In dem Fall geben wir None zurueck, damit die aufrufende
    # Funktion weiss, dass der Ort nicht existiert.
    if "results" not in daten:
        return None
 
    # Ersten (und besten) Treffer auslesen und die Koordinaten
    # in einem Dictionary zurueckgeben
    treffer = daten["results"][0]
    return {
        "lat": treffer["latitude"],
        "lon": treffer["longitude"]
    }
 
 
def hole_durchschnittstemperatur(ort, start_datum, end_datum):
    # Hauptfunktion dieses Moduls.
    # Gibt die erwartete Durchschnittstemperatur (in Grad Celsius)
    # fuer einen Ort und Reisezeitraum als EINEN einzigen Wert zurueck.
    #
    # Ablauf:
    #   1. Koordinaten zum Ort holen
    #   2. Fuer jedes der letzten 5 Jahre die Tagesmittel-Temperaturen
    #      im gleichen Zeitraum abrufen und sammeln
    #   3. Ueber alle gesammelten Werte den Gesamtdurchschnitt bilden
    #
    # Beispiel: Madrid, 01.05.2026 - 10.05.2026
    # -> Wir holen je 10 Tagesmittel aus 2021, 2022, 2023, 2024, 2025
    #    (also insgesamt 50 Werte) und bilden deren Durchschnitt.
    #
    # Erwartetes Datumsformat: "YYYY-MM-DD" (z.B. "2026-05-01")
    # Rueckgabe: float (Temperatur in °C),
    #            oder None wenn der Ort nicht gefunden wurde oder die
    #            API keine Daten zurueckgegeben hat.
 
    # --- Schritt 1: Koordinaten holen -------------------------------
    koordinaten = finde_koordinaten(ort)
    if koordinaten is None:
        # Ort nicht gefunden -> frueh abbrechen, damit wir gar nicht
        # erst die Wetter-API aufrufen
        return None
 
    # Die Datums-Strings ("YYYY-MM-DD") in echte Datum-Objekte umwandeln.
    # Brauchen wir, um damit rechnen zu koennen (z.B. das Jahr ersetzen).
    start = datetime.strptime(start_datum, "%Y-%m-%d").date()
    ende = datetime.strptime(end_datum, "%Y-%m-%d").date()
    heute = date.today()
 
    # Liste, in der wir ALLE Tagesmittelwerte aus allen 5 Jahren sammeln.
    # Am Schluss bilden wir ueber diese ganze Liste den Durchschnitt.
    alle_temperaturen = []
 
    # --- Schritt 2: Schleife ueber die letzten 5 Jahre --------------
    # n=1 bedeutet letztes Jahr, n=2 vorletztes Jahr, und so weiter.
    for n in range(1, ANZAHL_JAHRE + 1):
        referenz_jahr = heute.year - n
 
        # Das Reisedatum ins Referenzjahr "verschieben":
        # Monat und Tag bleiben gleich, nur das Jahr wird ersetzt.
        # Beispiel: aus 2026-05-01 wird nacheinander 2025-05-01,
        # 2024-05-01, 2023-05-01, 2022-05-01, 2021-05-01.
        try:
            hist_start = start.replace(year=referenz_jahr)
            hist_ende = ende.replace(year=referenz_jahr)
        except ValueError:
            # Sonderfall: der 29. Februar existiert nur in Schaltjahren.
            # Wenn das Reisedatum ein 29.02. ist und das Referenzjahr kein
            # Schaltjahr ist, wirft .replace() einen ValueError.
            # Wir weichen dann auf den 28.02. aus.
            hist_start = start.replace(year=referenz_jahr, day=28)
            hist_ende = ende.replace(year=referenz_jahr, day=28)
 
        # Parameter fuer die Archiv-API zusammenbauen:
        # - latitude/longitude: wo wir die Daten wollen
        # - start_date/end_date: der Zeitraum im Referenzjahr
        # - daily: welchen Wert wir pro Tag wollen. Hier reicht uns
        #   das Tagesmittel ("temperature_2m_mean"), weil wir am
        #   Schluss nur einen Durchschnittswert brauchen.
        # - timezone=auto: Open-Meteo waehlt automatisch die richtige
        #   Zeitzone fuer den Ort. Sonst waeren die Tages-Grenzen in UTC,
        #   was zu komischen Ergebnissen fuehren kann.
        params = {
            "latitude": koordinaten["lat"],
            "longitude": koordinaten["lon"],
            "start_date": hist_start.strftime("%Y-%m-%d"),
            "end_date": hist_ende.strftime("%Y-%m-%d"),
            "daily": "temperature_2m_mean",
            "timezone": "auto"
        }
 
        # API-Aufruf fuer dieses Jahr + Antwort als JSON lesen
        antwort = requests.get(ARCHIV_URL, params=params)
        daten = antwort.json()
 
        # Falls die API keine Daten liefert (z.B. bei einem Fehler),
        # ueberspringen wir dieses Jahr mit "continue" und machen
        # mit dem naechsten Jahr weiter. So bricht nicht gleich alles ab.
        if "daily" not in daten:
            continue
 
        # Alle Tageswerte aus diesem Jahr an die Gesamtliste anhaengen.
        # Wir nehmen extend() statt append(), weil wir eine Liste an eine
        # andere Liste haengen wollen (und nicht die Liste als ein Element).
        alle_temperaturen.extend(daten["daily"]["temperature_2m_mean"])
 
    # Falls die API fuer keines der 5 Jahre Daten geliefert hat,
    # koennen wir keinen Durchschnitt bilden -> None zurueckgeben.
    if len(alle_temperaturen) == 0:
        return None
 
    # Manchmal liefert die API None-Werte fuer einzelne Tage (z.B. bei
    # Datenluecken). Die muessen wir rausfiltern, weil wir mit None
    # nicht rechnen koennen.
    alle_temperaturen = [t for t in alle_temperaturen if t is not None]
 
    # Nochmal pruefen: falls nach dem Filtern nichts mehr uebrig ist
    if len(alle_temperaturen) == 0:
        return None
 
    # --- Schritt 3: Gesamtdurchschnitt berechnen --------------------
    # Einfach Summe aller Werte geteilt durch die Anzahl der Werte.
    durchschnitt = sum(alle_temperaturen) / len(alle_temperaturen)
 
    # Auf eine Nachkommastelle runden (z.B. 18.347 -> 18.3)
    return round(durchschnitt, 1)
 
 
# ============================================================
# Testblock
# ============================================================
# Der Code hier drin laeuft nur, wenn wir diese Datei direkt starten
# (also z.B. mit "python wetter_api.py" im Terminal).
# Wird die Datei dagegen von woanders importiert, wird der Block
# uebersprungen. Praktisch, um die Funktion schnell zu testen,
# ohne gleich die ganze Streamlit-App starten zu muessen.
if __name__ == "__main__":
    # Beispiel: Madrid, Anfang Mai 2026
    temperatur = hole_durchschnittstemperatur("Madrid", "2026-05-01", "2026-05-10")
 
    if temperatur is None:
        print("Keine Daten gefunden.")
    else:
        print(f"Durchschnittstemperatur: {temperatur} °C")