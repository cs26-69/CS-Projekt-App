import streamlit as st
from datetime import date

st.title("FitMyTrip")

st.header("Finde dein Traumreiseziel in Europa!")

st.markdown("Bist auch Du überwältigt von der Auswahl verschiedener Reiseziele? " \
        "Kein Problem! Unsere App liefert dir ein **personalisiertes Reiseziel** " \
        "basierend auf verschiedenen **Matchmaking Kriterien**.")

st.subheader("Kriterien Input")

st.write("Folgende Kriterien stehen zur Auswahl:")
#Die Inputs werden in den Variablen category, temperature, safety, flighttime, bduget, trip_duration abgespeichert

st.write("Art des Reiseziels")
category = st.selectbox("Bitte wähle deine gewünschte Kategorie von Reiseziel:", ["Berge", "Meer", "Stadt", "Natur"], index = None, placeholder = "Bitte wählen")

st.write("Temperatur")
temperature = st.slider("Bitte gib deine gewünschte Temperatur am Reiseziel ein: ", -30, 40, 0)

st.write("Sicherheit")
safety = st.slider("Bitte gib deine gewünschtes Sicherheitsniveau am Reiseziel ein:", 1, 10, 1)

st.write("Flugzeit")
flighttime = st.selectbox("Bitte gib die maximal zulässige Flugzeit von Zürich ein: ", ["weniger als 2 Stunden", "2 bis 4 Stunden", "mehr als 4 Stunden"], index = None, placeholder = "Bitte wählen")

st.write("Budget")
budget = st.number_input("Bitte gib dein gewünschtes Budget für die Reise ein:", min_value = 0, step = 100)

st.write("Reisezeitraum")
trip_start = st.date_input("Bitte gib dein gewünschten Startzeitpunkt ein:")
trip_end = st.date_input("Bitte gib dein gewünschten Endzeitpunkt ein:")

trip_duration = trip_end - trip_start

trip = {
    "Art des Reiseziels": category, "Temperatur": temperature, "Sicherheit": safety, "Flugzeit": flighttime, "Budget": budget, "Reisestart": trip_start, "Reiseende": trip_end, "Reisedauer": trip_duration
}

st.subheader("Zusammenfassung")
st.write("Du hast folgende Inputfaktoren gewählt: ")

for key, value in trip.items():
    st.markdown(f"**{key}:** {value}")