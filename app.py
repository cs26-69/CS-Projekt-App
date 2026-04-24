import streamlit as st
from datetime import date

st.title("FitMyTrip")

st.header("Finde dein Traumreiseziel in Europa!")

st.markdown("Bist auch Du überwältigt von der Auswahl verschiedener Reiseziele? " \
        "Kein Problem! Unsere App liefert dir ein **personalisiertes Reiseziel** " \
        "basierend auf verschiedenen **Matchmaking Kriterien**.")

st.write("Folgende Kriterien stehen zur Auswahl:")

st.write("Temperatur")
temperature = st.slider("Bitte gib deine gewünschte Temperatur am Reiseziel ein: ", -30, 40, 0)

st.write("Sicherheit")
safety = st.slider("Bitte gib deine gewünschte Sicherheit am Reiseziel ein:", 1, 10, 1)

st.write("Flugzeit")
flighttime = st.slider("Bitte gib deine gewünschte Flugzeit von Zürich in Stunden ein: ",0, 5, 0)

st.write("Budget")
budget = st.number_input("Bitte gib dein gewünschtes Budget für die Reise ein:", min_value = 0, step = 100)

st.write("Reisezeitraum")
trip_start = st.date_input("Bitte gib dein gewünschten Startzeitpunkt ein:")
trip_end = st.date_input("Bitte gib dein gewünschten Endzeitpunkt ein:")

trip_duration = trip_end - trip_start

trip = {
    "Temperatur": temperature, "Sicherheit": safety, "Flugzeit": flighttime, "Budget": budget, "Reisestart": trip_start, "Reiseende": trip_end, "Reisedauer": trip_duration
}

st.subheader("Zusammenfassung")
st.write("Du hast folgende Inputfaktoren gewählt: ")

for key, value in trip.items():
    st.markdown(f"**{key}:** {value}")

st.title("Test, ob diese Kacke funktioniert")

st.title("Test 2")
