import streamlit as st
from datetime import date
from Feature_Database import filter_destinations

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
        # Funktion aufrufen
        ergebnis = filter_destinations(
            category=category,
            safety=safety,
            flighttime=flighttime_mapping[flighttime_label],
            budget=budget,
            trip_duration=trip_duration_days,
            flight_cost=200,  # später von API
        )
        
        # Ergebnis anzeigen
        st.subheader("Deine passenden Reiseziele")
        if len(ergebnis) == 0:
            st.warning("Leider haben wir kein passendes Reiseziel gefunden. Versuche, deine Kriterien zu lockern.")
        else:
            st.success(f"Wir haben {len(ergebnis)} passende Reiseziele für dich gefunden!")
            st.dataframe(ergebnis)