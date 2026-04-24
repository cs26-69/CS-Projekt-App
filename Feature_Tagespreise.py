# ============================================================
# Preisniveau-API fuer FitMyTrip
# ============================================================
# Dieses Modul liefert einen geschaetzten Tageskosten-Wert in CHF
# fuer Restaurants und Hotels in einem europaeischen Land.
#
# WICHTIG: Die Werte gelten pro LAND, nicht pro STADT!
# Eurostat bietet keine Preisdaten auf Staedte-Ebene an. Der Wert
# fuer "Spanien" gilt also gleichermassen fuer Madrid, Barcelona,
# Valencia usw. Das ist eine bewusste Vereinfachung, die wir in
# Kauf nehmen, damit wir eine zuverlaessige, offizielle Datenquelle
# nutzen koennen.
#
# So funktioniert's:
# Eurostat liefert einen "Price Level Index" (PLI) fuer Restaurants
# und Hotels. Das ist ein dimensionsloser Vergleichswert mit
# EU-Durchschnitt = 100. Ein Wert von 108 heisst: "Restaurants und
# Hotels sind dort 8% teurer als im EU-Schnitt".
# Damit wir daraus einen konkreten CHF-Betrag machen, legen wir
# einen Baseline-Wert fest (siehe BASELINE_CHF unten) und skalieren
# den Index damit:
#   Tageskosten in CHF = BASELINE_CHF * (Index / 100)
#
# Anhaltswerte mit 100 CHF als Baseline:
#   Schweiz:    ~170 CHF/Tag  (teuerstes Land Europas)
#   Daenemark:  ~145 CHF/Tag
#   Frankreich: ~115 CHF/Tag
#   Spanien:    ~100 CHF/Tag  (etwa EU-Schnitt)
#   Portugal:    ~90 CHF/Tag
#   Polen:       ~70 CHF/Tag
#   Bulgarien:   ~60 CHF/Tag
#
# Datenquelle: Eurostat (Datensatz prc_ppp_ind). Eurostat ist das
# statistische Amt der EU. Die API ist oeffentlich, braucht keinen
# API-Key und hat keine Rate-Limits.

import requests


# Basis-URL der Eurostat-API.
# "prc_ppp_ind" ist der Datensatz fuer Purchasing Power Parities
# (Kaufkraftparitaeten) und Price Level Indices (Preisniveau-Indizes).
EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_ppp_ind"

# Filter-Werte fuer unsere API-Anfrage:
# - "ppp_cat" (Analytical categories for PPPs calculation) ist
#   die Dimension, in der die Konsumkategorien stehen.
#   Der Code "A0111" steht fuer "Restaurants and hotels".
# - "na_item" ist die Dimension fuer die Art der Zahl, die wir wollen.
#   "PLI_EU27_2020" ist der Preisniveau-Index mit EU27 = 100.
PPP_CAT_RESTAURANTS = "A0111"
NA_ITEM_PLI = "PLI_EU27_2020"

# Baseline-Wert in CHF: So viel kostet ein typischer Reisetag
# (Restaurants + Hotels) in einem Land mit EU-durchschnittlichem
# Preisniveau. Der Wert dient als Ankerpunkt fuer die Umrechnung.
# Falls ihr das spaeter kalibrieren wollt, einfach hier anpassen -
# der Rest des Codes uebernimmt den neuen Wert automatisch.
BASELINE_CHF = 100


# Mapping: Laendernamen (wie in unserer Excel) -> Eurostat-Laendercode.
# Die Codes sind die ueblichen ISO-2-Laendercodes, mit zwei Ausnahmen:
# - Eurostat nutzt "EL" fuer Griechenland (nicht "GR")
# - Eurostat nutzt "UK" fuer Grossbritannien (nicht "GB")
LAENDER_CODES = {
    "Portugal":      "PT",
    "Spanien":       "ES",
    "Frankreich":    "FR",
    "Italien":       "IT",
    "Griechenland":  "EL",
    "Malta":         "MT",
    "Slowenien":     "SI",
    "Österreich":    "AT",
    "Tschechien":    "CZ",
    "Ungarn":        "HU",
    "Polen":         "PL",
    "Slowakei":      "SK",
    "Bulgarien":     "BG",
    "Rumänien":      "RO",
    "Serbien":       "RS",
    "Albanien":      "AL",
    "Kroatien":      "HR",
    "Deutschland":   "DE",
    "Niederlande":   "NL",
    "Belgien":       "BE",
    "UK":            "UK",
    "Irland":        "IE",
    "Dänemark":      "DK",
    "Schweden":      "SE",
    "Norwegen":      "NO",
    "Finnland":      "FI",
    "Island":        "IS"
}


def hole_tageskosten(land):
    # Hauptfunktion dieses Moduls.
    # Gibt die geschaetzten Tageskosten in CHF fuer Restaurants
    # und Hotels im gewuenschten Land zurueck.
    #
    # Parameter:
    #   land: Laendername wie in unserer Excel-Datenbank
    #         (z.B. "Spanien", "Deutschland", "Dänemark")
    #
    # Rueckgabe:
    #   float mit den Tageskosten in CHF,
    #   oder None falls:
    #     - das Land nicht in unserem Mapping steht
    #     - Eurostat fuer dieses Land keine Daten hat
    #     - die API nicht erreichbar ist
    #
    # Es wird automatisch der neuste verfuegbare Datenpunkt genommen.
    # Eurostat-Daten werden jaehrlich aktualisiert, darum ist der
    # Wert typischerweise aus dem Vorjahr oder vor zwei Jahren.

    # Pruefen ob wir das Land ueberhaupt kennen
    if land not in LAENDER_CODES:
        return None
    code = LAENDER_CODES[land]

    # Parameter fuer die Eurostat-Anfrage zusammenbauen.
    # Wir filtern so stark wie moeglich (auf ein Land, eine Kategorie,
    # eine Index-Art), damit nur ein einziger Wert pro Jahr zurueckkommt.
    params = {
        "format": "JSON",
        "lang": "EN",
        "geo": code,
        "ppp_cat": PPP_CAT_RESTAURANTS,
        "na_item": NA_ITEM_PLI
    }

    # API-Aufruf und Antwort als JSON einlesen
    antwort = requests.get(EUROSTAT_URL, params=params)
    daten = antwort.json()

    # Eurostat liefert die Antwort im sogenannten "JSON-stat"-Format.
    # Die eigentlichen Zahlen stehen im "value"-Feld, und die
    # zugehoerigen Jahre in "dimension" -> "time" -> "category" -> "index".
    # Fehlt eins der beiden Felder, ist die Antwort unbrauchbar.
    if "value" not in daten or "dimension" not in daten:
        return None

    werte = daten["value"]

    # Zeit-Dimension auslesen. Das ist ein Dictionary wie z.B.
    #   {"1995": 0, "1996": 1, ..., "2024": 29}
    # Der Key ist das Jahr, der Value die Position im "value"-Feld.
    try:
        zeit_indizes = daten["dimension"]["time"]["category"]["index"]
    except KeyError:
        return None

    # Wir wollen den aktuellsten verfuegbaren Wert. Darum gehen wir
    # die Jahre absteigend (neuste zuerst) durch und nehmen den
    # ersten, fuer den tatsaechlich ein Wert existiert.
    # Grund: Nicht jedes Land hat fuer jedes Jahr Daten - manchmal
    # fehlen die letzten ein bis zwei Jahre.
    jahre_absteigend = sorted(zeit_indizes.keys(), reverse=True)

    for jahr in jahre_absteigend:
        # Die Keys im value-Dictionary sind Strings, darum konvertieren
        idx = str(zeit_indizes[jahr])
        if idx in werte and werte[idx] is not None:
            # Gefunden! Jetzt den Index-Wert in CHF umrechnen.
            # Formel: Tageskosten = BASELINE_CHF * (Index / 100)
            # Beispiel: Index 108 -> 100 * 108/100 = 108 CHF
            index = float(werte[idx])
            tageskosten_chf = BASELINE_CHF * index / 100
            # Auf eine Nachkommastelle runden und zurueckgeben
            return round(tageskosten_chf, 1)

    # Kein Wert fuer irgendein Jahr gefunden
    return None


# ============================================================
# Testblock
# ============================================================
# Laeuft nur, wenn die Datei direkt gestartet wird (also nicht
# bei einem "from preisniveau_api import hole_tageskosten").
# Praktisch, um die Funktion schnell auszuprobieren.
if __name__ == "__main__":
    # Ein paar Laender aus unserer Excel zum Testen.
    # Bewusst eine Mischung aus teureren und guenstigeren,
    # damit wir sehen ob die Werte plausibel sind.
    test_laender = [
        "Deutschland",
        "Frankreich",
        "Spanien",
        "Portugal",
        "Italien",
        "Bulgarien",
        "Dänemark",
        "Norwegen"
    ]

    print(f"Geschaetzte Tageskosten (Restaurants + Hotels)")
    print(f"Baseline: {BASELINE_CHF} CHF/Tag bei EU-Durchschnitt")
    print("-" * 50)

    for land in test_laender:
        kosten = hole_tageskosten(land)
        if kosten is None:
            print(f"  {land:15s}  keine Daten")
        else:
            print(f"  {land:15s}  {kosten} CHF/Tag")