# ============================================================
# Wetter-API fuer FitMyTrip
# ============================================================
# Holt Temperaturdaten ueber die Open-Meteo API.
# Open-Meteo ist gratis und braucht keinen API-Key.
#
# Dieses Modul bietet drei Hauptfunktionen:
#
# 1) hole_durchschnittstemperatur(ort, start, end)
#    Gibt fuer EINEN Ort einen Durchschnittswert zurueck.
#    Macht 1 Geocoding-Call + 5 Archiv-Calls = 6 API-Calls.
#
# 2) hole_temperaturen_pro_jahr(ort, start, end)
#    Wie 1), aber gibt die Werte pro Jahr zurueck (fuer das Liniendiagramm).
#
# 3) hole_temperaturen_batch_pro_jahr(orte, start, end)  [NEU]
#    Holt fuer eine LISTE von Orten alle Daten in einem Rutsch.
#    Trick: Open-Meteo akzeptiert mehrere Koordinaten getrennt durch
#    Kommas und gibt eine Liste von Antworten zurueck. So machen wir
#    nur 5 Archiv-Calls (1 pro Vorjahr) statt 5*N Calls bei N Orten.
#    Das ist der grosse Performance-Gewinn fuer die App.

import requests
from datetime import date, datetime


GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIV_URL = "https://archive-api.open-meteo.com/v1/archive"

# Anzahl vergangener Jahre, ueber die der Durchschnitt gebildet wird.
ANZAHL_JAHRE = 5


def finde_koordinaten(ort):
    # Sucht Laengen- und Breitengrad zu einem Ortsnamen.
    params = {"name": ort, "count": 1, "language": "de"}
    antwort = requests.get(GEO_URL, params=params)
    daten = antwort.json()

    if "results" not in daten:
        return None

    treffer = daten["results"][0]
    return {
        "lat": treffer["latitude"],
        "lon": treffer["longitude"],
    }


# ============================================================
# EINZELORT-FUNKTIONEN (bestehen wie bisher, fuer Liniendiagramm)
# ============================================================
def hole_durchschnittstemperatur(ort, start_datum, end_datum):
    # Liefert eine Durchschnittstemperatur (in Grad) fuer einen Ort
    # ueber die letzten 5 Jahre im gleichen Reisezeitraum.

    koordinaten = finde_koordinaten(ort)
    if koordinaten is None:
        return None

    start = datetime.strptime(start_datum, "%d.%m.%Y").date()
    ende = datetime.strptime(end_datum, "%d.%m.%Y").date()
    heute = date.today()

    alle_temperaturen = []

    for n in range(1, ANZAHL_JAHRE + 1):
        referenz_jahr = heute.year - n
        try:
            hist_start = start.replace(year=referenz_jahr)
            hist_ende = ende.replace(year=referenz_jahr)
        except ValueError:
            hist_start = start.replace(year=referenz_jahr, day=28)
            hist_ende = ende.replace(year=referenz_jahr, day=28)

        params = {
            "latitude": koordinaten["lat"],
            "longitude": koordinaten["lon"],
            "start_date": hist_start.strftime("%Y-%m-%d"),
            "end_date": hist_ende.strftime("%Y-%m-%d"),
            "daily": "temperature_2m_mean",
            "timezone": "auto",
        }

        antwort = requests.get(ARCHIV_URL, params=params)
        daten = antwort.json()

        if "daily" not in daten:
            continue

        alle_temperaturen.extend(daten["daily"]["temperature_2m_mean"])

    if len(alle_temperaturen) == 0:
        return None

    alle_temperaturen = [t for t in alle_temperaturen if t is not None]
    if len(alle_temperaturen) == 0:
        return None

    durchschnitt = sum(alle_temperaturen) / len(alle_temperaturen)
    return round(durchschnitt, 1)


def hole_temperaturen_pro_jahr(ort, start_datum, end_datum):
    # Wie hole_durchschnittstemperatur, aber gibt einen Dict
    # {jahr: temp} zurueck (fuer das Liniendiagramm).

    koordinaten = finde_koordinaten(ort)
    if koordinaten is None:
        return None

    start = datetime.strptime(start_datum, "%d.%m.%Y").date()
    ende = datetime.strptime(end_datum, "%d.%m.%Y").date()
    heute = date.today()

    pro_jahr = {}

    for n in range(1, ANZAHL_JAHRE + 1):
        referenz_jahr = heute.year - n
        try:
            hist_start = start.replace(year=referenz_jahr)
            hist_ende = ende.replace(year=referenz_jahr)
        except ValueError:
            hist_start = start.replace(year=referenz_jahr, day=28)
            hist_ende = ende.replace(year=referenz_jahr, day=28)

        params = {
            "latitude": koordinaten["lat"],
            "longitude": koordinaten["lon"],
            "start_date": hist_start.strftime("%Y-%m-%d"),
            "end_date": hist_ende.strftime("%Y-%m-%d"),
            "daily": "temperature_2m_mean",
            "timezone": "auto",
        }

        antwort = requests.get(ARCHIV_URL, params=params)
        daten = antwort.json()

        if "daily" not in daten:
            continue

        werte = [t for t in daten["daily"]["temperature_2m_mean"] if t is not None]
        if werte:
            pro_jahr[referenz_jahr] = round(sum(werte) / len(werte), 1)

    return pro_jahr if pro_jahr else None


# ============================================================
# BATCH-FUNKTION: ALLE ORTE AUF EINMAL [NEU]
# ============================================================
def hole_temperaturen_batch_pro_jahr(orte, start_datum, end_datum):
    # Holt fuer eine Liste von Orten alle Temperaturen in nur 5
    # Archiv-API-Calls (statt 5*N wie bisher).
    #
    # Trick: Open-Meteo akzeptiert mehrere Koordinaten in einem
    # Request, getrennt durch Kommas in latitude und longitude.
    # Die Antwort kommt dann als Liste zurueck - eine Antwort pro
    # Koordinaten-Paar, in der gleichen Reihenfolge.
    #
    # Hinweis: Geocoding muss leider trotzdem pro Ort gemacht werden,
    # weil die Geocoding-API kein Batch unterstuetzt. Aber das laeuft
    # nur einmal und kann gecached werden.
    #
    # Rueckgabe:
    #   {
    #     "durchschnitt": { "Lissabon": 18.5, "Paris": 14.3, ... },
    #     "pro_jahr":     { "Lissabon": {2021: 17.9, 2022: 18.1, ...},
    #                       "Paris":    {2021: 13.8, ...}, ... }
    #   }

    # Schritt 1: Koordinaten fuer alle Orte holen.
    # Orte ohne Koordinaten werden uebersprungen.
    koordinaten_liste = []
    valide_orte = []
    for ort in orte:
        k = finde_koordinaten(ort)
        if k is not None:
            koordinaten_liste.append(k)
            valide_orte.append(ort)

    if len(valide_orte) == 0:
        return {"durchschnitt": {}, "pro_jahr": {}}

    # Schritt 2: Datum parsen
    start = datetime.strptime(start_datum, "%d.%m.%Y").date()
    ende = datetime.strptime(end_datum, "%d.%m.%Y").date()
    heute = date.today()

    # Komma-separierte Strings fuer den API-Call zusammenbauen
    lats_str = ",".join(str(k["lat"]) for k in koordinaten_liste)
    lons_str = ",".join(str(k["lon"]) for k in koordinaten_liste)

    # Schritt 3: Speicher fuer die Werte pro Ort und Jahr.
    # Erst mal leer befuellen, dann Jahr fuer Jahr ergaenzen.
    pro_jahr_pro_ort = {ort: {} for ort in valide_orte}

    # Schritt 4: Fuer jedes Vorjahr einen einzelnen Batch-Request.
    # Insgesamt also nur ANZAHL_JAHRE Requests, egal wie viele Orte.
    for n in range(1, ANZAHL_JAHRE + 1):
        referenz_jahr = heute.year - n
        try:
            hist_start = start.replace(year=referenz_jahr)
            hist_ende = ende.replace(year=referenz_jahr)
        except ValueError:
            hist_start = start.replace(year=referenz_jahr, day=28)
            hist_ende = ende.replace(year=referenz_jahr, day=28)

        params = {
            "latitude": lats_str,
            "longitude": lons_str,
            "start_date": hist_start.strftime("%Y-%m-%d"),
            "end_date": hist_ende.strftime("%Y-%m-%d"),
            "daily": "temperature_2m_mean",
            "timezone": "auto",
        }

        try:
            antwort = requests.get(ARCHIV_URL, params=params, timeout=30)
            daten = antwort.json()
        except (requests.RequestException, ValueError):
            # Bei Netzwerkfehler dieses Jahr ueberspringen
            continue

        # Open-Meteo gibt bei mehreren Koordinaten eine Liste zurueck,
        # bei nur einer Koordinate ein Dict. Wir behandeln beide Faelle.
        if isinstance(daten, list):
            # Liste: ein Eintrag pro Ort, in der Reihenfolge der Inputs
            for i, response in enumerate(daten):
                if i >= len(valide_orte):
                    break
                ort = valide_orte[i]
                if not isinstance(response, dict) or "daily" not in response:
                    continue
                werte = [t for t in response["daily"]["temperature_2m_mean"] if t is not None]
                if werte:
                    pro_jahr_pro_ort[ort][referenz_jahr] = round(
                        sum(werte) / len(werte), 1
                    )
        elif isinstance(daten, dict) and len(valide_orte) == 1:
            # Nur ein Ort -> Dict statt Liste
            ort = valide_orte[0]
            if "daily" in daten:
                werte = [t for t in daten["daily"]["temperature_2m_mean"] if t is not None]
                if werte:
                    pro_jahr_pro_ort[ort][referenz_jahr] = round(
                        sum(werte) / len(werte), 1
                    )

    # Schritt 5: Durchschnitt pro Ort berechnen (Mittelwert aller Jahre)
    durchschnitt_pro_ort = {}
    for ort, jahr_werte in pro_jahr_pro_ort.items():
        if jahr_werte:
            durchschnitt_pro_ort[ort] = round(
                sum(jahr_werte.values()) / len(jahr_werte), 1
            )

    return {
        "durchschnitt": durchschnitt_pro_ort,
        "pro_jahr": pro_jahr_pro_ort,
    }


# ============================================================
# Testblock
# ============================================================
if __name__ == "__main__":
    # Test der Batch-Funktion
    print("Teste Batch-Funktion mit 3 Orten...")
    ergebnis = hole_temperaturen_batch_pro_jahr(
        ["Madrid", "Paris", "Berlin"],
        "01.05.2026", "10.05.2026",
    )
    print("\nDurchschnittstemperaturen:")
    for ort, temp in ergebnis["durchschnitt"].items():
        print(f"  {ort}: {temp}°C")
    print("\nPro Jahr (Madrid):")
    for jahr, temp in sorted(ergebnis["pro_jahr"].get("Madrid", {}).items()):
        print(f"  {jahr}: {temp}°C")