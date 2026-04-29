import streamlit as st
import pandas as pd
from datetime import date

from feature_database import filter_destinations
from Feature_Temperatur_API import hole_durchschnittstemperatur
from Feature_Tagespreise_API import hole_tageskosten


# Toleranz in Grad Celsius rund um die Wunschtemperatur.
# Als Konstante, damit wir den Wert spaeter leicht anpassen koennen.
TEMP_TOLERANZ = 5


# Wrapper mit Streamlit-Cache, damit wir die APIs nicht jedes Mal
# neu aufrufen muessen wenn sich an den Inputs nichts geaendert hat.
# Wichtig vor allem bei der Temperatur-API: pro Stadt sind 5 HTTP-Calls
# noetig (einer pro Vorjahr), das wuerde sonst jedes Mal lange dauern.
@st.cache_data(show_spinner=False)
def get_temperatur_cached(stadt, start_str, end_str):
    return hole_durchschnittstemperatur(stadt, start_str, end_str)

@st.cache_data(show_spinner=False)
def get_tageskosten_cached(land):
    return hole_tageskosten(land)


st.title("FitMyTrip")

st.header("Finde dein Traumreiseziel in Europa!")

st.markdown("Bist auch Du überwältigt von der Auswahl verschiedener Reiseziele? " \
        "Kein Problem! Unsere App liefert dir ein **personalisiertes Reiseziel** " \
        "basierend auf verschiedenen **Matchmaking Kriterien**.")

st.subheader("Kriterien Input")

st.write("Folgende Kriterien stehen zur Auswahl:")
#Die Inputs werden in den Variablen category, temperature, safety, flighttime, bduget, trip_duration abgespeichert

st.write("Art des Reiseziels")
category = st.selectbox("Bitte wähle deine gewünschte Kategorie von Reiseziel:", 
                        ["Berge", "Meer", "Stadt", "Natur"], 
                        index = None, 
                        placeholder = "Bitte wählen")

st.write("Temperatur")
temperature = st.slider("Bitte gib deine gewünschte Temperatur am Reiseziel ein: ", 
                        -30, 40, 0)

st.write("Sicherheit")
safety = st.slider("Bitte gib deine gewünschtes Sicherheitsniveau am Reiseziel ein:", 
                   1, 5, 1)

st.write("Flugzeit")
flighttime_label = st.selectbox("Bitte gib die maximal zulässige Flugzeit von Zürich ein: ", 
                          ["weniger als 1.5 Stunden", "1.5 bis 3 Stunden", "mehr als 3 Stunden"], 
                          index = None, 
                          placeholder = "Bitte wählen")

#flighttime_label in Stunden-Wert umwandeln
flighttime_mapping = {
    "weniger als 1.5 Stunden": 1.5,
    "1.5 bis 3 Stunden": 3.0,
    "mehr als 3 Stunden": float("inf"),
}

st.write("Budget")
budget = st.number_input("Bitte gib dein gewünschtes Budget für die Reise ein:", 
                         min_value = 0, 
                         step = 100)

st.write("Reisezeitraum")
trip_start = st.date_input("Bitte gib dein gewünschten Startzeitpunkt ein:")
trip_end = st.date_input("Bitte gib dein gewünschten Endzeitpunkt ein:")

# Reisedauer in Tagen berechnen
trip_duration_days = (trip_end - trip_start).days

# Button zum Auslösen der Suche
if st.button("Reiseziele finden"):
    # Validierung der Inputs
    if category is None:
        st.error("Bitte wähle eine Kategorie aus.")
    elif flighttime_label is None:
        st.error("Bitte wähle eine maximale Flugzeit aus.")
    elif trip_duration_days <= 0:
        st.error("Das Enddatum muss nach dem Startdatum liegen.")
    elif budget <= 0:
        st.error("Bitte gib ein Budget grösser als 0 ein.")
    else:
        # Erst die statischen Kriterien aus der Datenbank filtern
        # (Kategorie, Sicherheit, Flugzeit, Flugpreise stehen alle in der CSV).
        # Das Budget setzen wir kuenstlich hoch, weil wir gleich mit den
        # echten Tageskosten aus der API neu rechnen.
        ergebnis = filter_destinations(
            category=category,
            safety=safety,
            flighttime=flighttime_mapping[flighttime_label],
            budget=10**9,
            trip_duration=trip_duration_days,
        )

        # Pruefen ob die Spalten da sind, die wir fuer die APIs brauchen.
        # Stadt -> Temperatur-API, Land -> Tageskosten-API, Flugpreise -> Gesamtkosten
        if len(ergebnis) > 0:
            for col in ("Stadt", "Land", "Flugpreise"):
                if col not in ergebnis.columns:
                    st.error(f"Die Spalte '{col}' fehlt in der Datenbank.")
                    st.stop()

        # Die gefilterten Reiseziele mit den API-Daten anreichern
        if len(ergebnis) > 0:
            ergebnis = ergebnis.copy()

            # Datum ins Format umwandeln, das die Temperatur-API erwartet (DD.MM.YYYY)
            start_str = trip_start.strftime("%d.%m.%Y")
            end_str = trip_end.strftime("%d.%m.%Y")

            with st.spinner(f"Hole Temperatur- und Preisdaten für {len(ergebnis)} Reiseziele..."):
                # Pro Zeile die beiden APIs aufrufen und Werte sammeln
                temperaturen = []
                tageskosten = []
                for _, row in ergebnis.iterrows():
                    temperaturen.append(get_temperatur_cached(row["Stadt"], start_str, end_str))
                    tageskosten.append(get_tageskosten_cached(row["Land"]))

                ergebnis["Erwartete Temperatur (°C)"] = temperaturen
                ergebnis["Tageskosten (CHF)"] = tageskosten

                # Gesamtkosten = Flugpreise (aus CSV) + Tageskosten (API) * Reisedauer
                # Falls eine der beiden Quellen keinen Wert hat, lassen wir das Feld
                # leer (NaN) und werfen die Zeile gleich anschliessend raus.
                ergebnis["Geschätzte Gesamtkosten (CHF)"] = ergebnis.apply(
                    lambda r: None
                    if pd.isna(r["Tageskosten (CHF)"]) or pd.isna(r["Flugpreise"])
                    else round(r["Flugpreise"] + r["Tageskosten (CHF)"] * trip_duration_days, 0),
                    axis=1,
                )

            # Reiseziele ohne API-Daten verwerfen wir (sonst kommen unten Fehler)
            ergebnis = ergebnis[
                ergebnis["Erwartete Temperatur (°C)"].notna()
                & ergebnis["Geschätzte Gesamtkosten (CHF)"].notna()
            ]

            # Temperatur-Match: nur Ziele, deren erwartete Temperatur innerhalb
            # der Toleranz um den Wunschwert liegt
            ergebnis = ergebnis[
                (ergebnis["Erwartete Temperatur (°C)"] >= temperature - TEMP_TOLERANZ)
                & (ergebnis["Erwartete Temperatur (°C)"] <= temperature + TEMP_TOLERANZ)
            ]

            # Budget-Match mit den echten Gesamtkosten
            ergebnis = ergebnis[ergebnis["Geschätzte Gesamtkosten (CHF)"] <= budget]

            # Sortieren nach Preis, guenstigstes zuerst
            ergebnis = ergebnis.sort_values("Geschätzte Gesamtkosten (CHF)").reset_index(drop=True)

        # Ergebnis anzeigen
        st.subheader("Deine passenden Reiseziele")
        if len(ergebnis) == 0:
            st.warning("Leider haben wir kein passendes Reiseziel gefunden. Versuche, deine Kriterien zu lockern.")
        else:
            st.success(f"Wir haben {len(ergebnis)} passende Reiseziele für dich gefunden!")
            st.caption(
                f"Temperatur-Toleranz: ±{TEMP_TOLERANZ} °C um deinen Wunschwert ({temperature} °C). "
                f"Flugpreise stammen aus unserer CSV, Tageskosten aus Eurostat-Daten."
            )
            st.dataframe(ergebnis)