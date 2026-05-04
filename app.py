import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date

from Feature_Database import filter_destinations
from Feature_Temperatur_API import (
    hole_durchschnittstemperatur,
    hole_temperaturen_pro_jahr,
)
from Feature_Tagespreise_API import hole_tageskosten


TEMP_TOLERANZ = 5

# Wide-Layout, damit die zwei Charts auf der Auswertungs-Seite
# nebeneinander Platz haben
st.set_page_config(page_title="FitMyTrip", layout="wide")


# --- Cached API-Wrapper -----------------------------------------------------
# Damit die APIs nicht jedes Mal neu aufgerufen werden muessen wenn sich
# an den Inputs nichts geaendert hat. Vor allem bei der Wetter-API wichtig
# (5 HTTP-Calls pro Destination, einer pro Vorjahr).
@st.cache_data(show_spinner=False)
def get_temperatur_cached(destination, start_str, end_str):
    return hole_durchschnittstemperatur(destination, start_str, end_str)

@st.cache_data(show_spinner=False)
def get_tageskosten_cached(land):
    return hole_tageskosten(land)

@st.cache_data(show_spinner=False)
def get_temperaturen_pro_jahr_cached(destination, start_str, end_str):
    return hole_temperaturen_pro_jahr(destination, start_str, end_str)


# --- Match-Score-Logik ------------------------------------------------------
def berechne_scores(row, wunsch_temp, budget):
    # Berechnet pro Reiseziel vier Einzelscores (jeweils 0-100%) und
    # daraus einen gleichgewichteten Gesamt-Match-Score.
    #
    # Idee: Pro Kriterium misst der Score, wie gut das Reiseziel zum
    # Wunsch passt. 100% = perfekter Treffer, 0% = grosser Abstand.
    # Werte unter 0 werden auf 0 gekappt.

    # Temperatur: bei 0 Grad Abweichung 100%, bei 15 Grad Abweichung 0%.
    # 15 Grad als Schmerzgrenze, weil unsere Toleranz schon +-5 Grad ist
    # und 15 Grad dann eindeutig nicht mehr passt.
    temp_diff = abs(row["Erwartete Temperatur (°C)"] - wunsch_temp)
    temp_score = max(0, 1 - temp_diff / 15)

    # Budget: Wer das Budget komplett ausreizt, kriegt 0%.
    # Wer guenstig wegkommt, kriegt mehr Punkte. So werden auch
    # finanziell attraktive Ziele belohnt, nicht nur thematisch passende.
    budget_score = max(0, 1 - row["Geschätzte Gesamtkosten (CHF)"] / budget)

    # Sicherheit: in der CSV ist niedriger = sicherer (skaliert 0-5).
    # 0 -> 100%, 5 -> 0%.
    safety_score = max(0, 1 - row["Sicherheitsindex"] / 5)

    # Flugzeit: 0h = 100%, 5h = 0%.
    flight_score = max(0, 1 - row["Flugzeit (ab ZRH)"] / 5)

    # Gesamt-Score = einfacher Mittelwert. Alle Kriterien sind gleich
    # wichtig, weil wir uns gegen eine Gewichtung entschieden haben.
    gesamt = (temp_score + budget_score + safety_score + flight_score) / 4

    return {
        "Temperatur": round(temp_score * 100, 1),
        "Budget": round(budget_score * 100, 1),
        "Sicherheit": round(safety_score * 100, 1),
        "Flugzeit": round(flight_score * 100, 1),
        "Match-Score (%)": round(gesamt * 100, 1),
    }


# --- Tabs als "Seiten" ------------------------------------------------------
# Streamlit hat keine echte Multi-Page-Navigation eingebaut (ausser ueber
# einen pages/-Ordner), darum nutze ich tabs als pragmatische Loesung.
tab_input, tab_ergebnis = st.tabs(["Kriterien", "Auswertung"])


# ===========================================================================
# TAB 1: Eingabe-Seite
# ===========================================================================
with tab_input:
    st.title("FitMyTrip")
    st.header("Finde dein Traumreiseziel in Europa!")

    st.markdown(
        "Bist auch Du überwältigt von der Auswahl verschiedener Reiseziele? "
        "Kein Problem! Unsere App liefert dir ein **personalisiertes Reiseziel** "
        "basierend auf verschiedenen **Matchmaking Kriterien**."
    )

    st.subheader("Kriterien Input")
    st.write("Folgende Kriterien stehen zur Auswahl:")

    # Die Inputs werden in den Variablen category, temperature, safety,
    # flighttime, budget und trip_duration abgespeichert
    category = st.selectbox(
        "Bitte wähle deine gewünschte Kategorie von Reiseziel:",
        ["Berge", "Meer", "Stadt", "Natur"],
        index=None,
        placeholder="Bitte wählen",
    )

    temperature = st.slider(
        "Bitte gib deine gewünschte Temperatur am Reiseziel ein:",
        -30, 40, 0,
    )

    safety = st.slider(
        "Bitte gib dein gewünschtes Sicherheitsniveau am Reiseziel ein:",
        1, 5, 1,
    )

    flighttime_label = st.selectbox(
        "Bitte gib die maximal zulässige Flugzeit von Zürich ein:",
        ["weniger als 1.5 Stunden", "1.5 bis 3 Stunden", "mehr als 3 Stunden"],
        index=None,
        placeholder="Bitte wählen",
    )

    # Mapping vom Label zur Stundenzahl, damit damit gerechnet werden kann
    flighttime_mapping = {
        "weniger als 1.5 Stunden": 1.5,
        "1.5 bis 3 Stunden": 3.0,
        "mehr als 3 Stunden": float("inf"),
    }

    budget = st.number_input(
        "Bitte gib dein gewünschtes Budget für die Reise ein:",
        min_value=0, step=100,
    )

    trip_start = st.date_input("Bitte gib deinen gewünschten Startzeitpunkt ein:")
    trip_end = st.date_input("Bitte gib deinen gewünschten Endzeitpunkt ein:")
    trip_duration_days = (trip_end - trip_start).days

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
            # Erst die statischen Kriterien aus der Datenbank filtern.
            # Das Budget setze ich kuenstlich hoch, weil ich gleich mit
            # den echten Tageskosten aus der API neu rechne.
            ergebnis = filter_destinations(
                category=category,
                safety=safety,
                flighttime=flighttime_mapping[flighttime_label],
                budget=10**9,
                trip_duration=trip_duration_days,
            )

            if len(ergebnis) > 0:
                # Sicherstellen, dass die noetigen Spalten vorhanden sind.
                # Destination -> Wetter-API, Land -> Tageskosten-API.
                for col in ("Destination", "Land", "Flugpreise"):
                    if col not in ergebnis.columns:
                        st.error(f"Die Spalte '{col}' fehlt in der Datenbank.")
                        st.stop()

                ergebnis = ergebnis.copy()
                start_str = trip_start.strftime("%d.%m.%Y")
                end_str = trip_end.strftime("%d.%m.%Y")

                with st.spinner(f"Hole Daten für {len(ergebnis)} Reiseziele..."):
                    # Pro Zeile beide APIs aufrufen
                    temperaturen, tageskosten = [], []
                    for _, row in ergebnis.iterrows():
                        temperaturen.append(get_temperatur_cached(row["Destination"], start_str, end_str))
                        tageskosten.append(get_tageskosten_cached(row["Land"]))

                    ergebnis["Erwartete Temperatur (°C)"] = temperaturen
                    ergebnis["Tageskosten (CHF)"] = tageskosten

                    # Gesamtkosten = Flugpreise + Tageskosten * Reisedauer.
                    # Falls eine Quelle keinen Wert hat, lasse ich das Feld
                    # leer und filtere die Zeile gleich anschliessend raus.
                    ergebnis["Geschätzte Gesamtkosten (CHF)"] = ergebnis.apply(
                        lambda r: None
                        if pd.isna(r["Tageskosten (CHF)"]) or pd.isna(r["Flugpreise"])
                        else round(r["Flugpreise"] + r["Tageskosten (CHF)"] * trip_duration_days, 0),
                        axis=1,
                    )

                # Reiseziele ohne API-Daten fliegen raus
                ergebnis = ergebnis[
                    ergebnis["Erwartete Temperatur (°C)"].notna()
                    & ergebnis["Geschätzte Gesamtkosten (CHF)"].notna()
                ]
                # Temperatur-Match (innerhalb Toleranz)
                ergebnis = ergebnis[
                    (ergebnis["Erwartete Temperatur (°C)"] >= temperature - TEMP_TOLERANZ)
                    & (ergebnis["Erwartete Temperatur (°C)"] <= temperature + TEMP_TOLERANZ)
                ]
                # Budget-Match
                ergebnis = ergebnis[ergebnis["Geschätzte Gesamtkosten (CHF)"] <= budget]

                # Match-Scores berechnen und an DataFrame anhaengen
                if len(ergebnis) > 0:
                    scores_df = ergebnis.apply(
                        lambda r: pd.Series(berechne_scores(r, temperature, budget)),
                        axis=1,
                    )
                    ergebnis = pd.concat([ergebnis, scores_df], axis=1)
                    # Sortierung nach Match-Score, bestes Ziel zuerst
                    ergebnis = ergebnis.sort_values("Match-Score (%)", ascending=False).reset_index(drop=True)

            # Alles in den session_state legen, damit Tab 2 zugreifen kann.
            # Streamlit laedt die App bei jedem Klick neu - ohne session_state
            # waeren die Daten beim Tab-Wechsel weg.
            st.session_state["ergebnis"] = ergebnis
            st.session_state["wunsch_temp"] = temperature
            st.session_state["budget"] = budget
            st.session_state["trip_start_str"] = trip_start.strftime("%d.%m.%Y")
            st.session_state["trip_end_str"] = trip_end.strftime("%d.%m.%Y")

            if len(ergebnis) == 0:
                st.warning("Leider haben wir kein passendes Reiseziel gefunden. Versuche, deine Kriterien zu lockern.")
            else:
                st.success(f"{len(ergebnis)} passende Reiseziele gefunden. Wechsle jetzt oben auf den Tab **Auswertung**.")


# ===========================================================================
# TAB 2: Auswertungs-Seite mit den Charts
# ===========================================================================
with tab_ergebnis:
    # Wenn der User direkt auf Tab 2 klickt, ohne vorher gesucht zu haben
    if "ergebnis" not in st.session_state:
        st.info("Bitte zuerst im Tab **Kriterien** Reiseziele suchen.")
    elif len(st.session_state["ergebnis"]) == 0:
        st.warning("Es wurden keine Reiseziele gefunden, die zu deinen Kriterien passen.")
    else:
        # Daten aus dem session_state holen
        ergebnis = st.session_state["ergebnis"]
        wunsch_temp = st.session_state["wunsch_temp"]
        start_str = st.session_state["trip_start_str"]
        end_str = st.session_state["trip_end_str"]

        st.title("Reiseziel-Finder – Deine persönliche Auswertung")

        # Top-Empfehlung = erstes Element (oben absteigend sortiert)
        top = ergebnis.iloc[0]
        st.success(
            f"Dein bestes Match: **{top['Destination']}** ({top['Land']}) "
            f"mit {top['Match-Score (%)']}% Übereinstimmung"
        )

        # --- Charts nebeneinander -----------------------------------------
        col1, col2 = st.columns(2)

        # CHART 1: Bar-Chart Ranking
        with col1:
            st.subheader("Reiseziel-Ranking")

            # Farb-Mapping je nach Score-Stufe
            def farbe(score):
                if score >= 80:  return "#2d8a3e"   # sehr gut: dunkelgruen
                if score >= 65:  return "#7bbf6a"   # gut: hellgruen
                if score >= 50:  return "#e8b84a"   # mittel: gelb
                return "#d65555"                    # schwach: rot

            # Top 10 reicht, sonst wird der Chart unuebersichtlich
            top10 = ergebnis.head(10)
            fig_bar = px.bar(
                top10,
                x="Match-Score (%)",
                y="Destination",
                orientation="h",
                text="Match-Score (%)",
            )
            fig_bar.update_traces(
                marker_color=[farbe(s) for s in top10["Match-Score (%)"]],
                texttemplate="%{text:.1f}%",
                textposition="outside",
            )
            fig_bar.update_layout(
                yaxis={"categoryorder": "total ascending"},  # bestes Ziel oben
                xaxis_title="Übereinstimmung mit deinen Präferenzen (%)",
                yaxis_title="",
                showlegend=False,
                height=450,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        # CHART 2: Radar-Chart Du vs. bestes Match
        with col2:
            st.subheader(f"Profil-Vergleich: Du vs. {top['Destination']}")

            kategorien = ["Temperatur", "Budget", "Sicherheit", "Flugzeit"]
            # "Du" steht per Definition immer auf 100% pro Kriterium -
            # das ist quasi der ideale Match. Das Reiseziel zeigt seinen
            # jeweiligen Sub-Score und kann mit dem Ideal verglichen werden.
            deine_werte = [100, 100, 100, 100]
            ziel_werte = [top["Temperatur"], top["Budget"], top["Sicherheit"], top["Flugzeit"]]

            fig_radar = go.Figure()
            # Trick: erste Kategorie am Ende nochmal anhaengen,
            # damit das Polygon geschlossen wird
            fig_radar.add_trace(go.Scatterpolar(
                r=deine_werte + [deine_werte[0]],
                theta=kategorien + [kategorien[0]],
                fill="toself",
                name="Deine Präferenzen",
                line_color="#3b82f6",
            ))
            fig_radar.add_trace(go.Scatterpolar(
                r=ziel_werte + [ziel_werte[0]],
                theta=kategorien + [kategorien[0]],
                fill="toself",
                name=f"Bestes Match: {top['Destination']}",
                line_color="#2d8a3e",
            ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=True,
                height=450,
            )
            st.plotly_chart(fig_radar, use_container_width=True)

        # CHART 3: Liniendiagramm Temperaturentwicklung der Top-Empfehlung
        st.subheader(
            f"Temperaturentwicklung in {top['Destination']} "
            f"(gleicher Reisezeitraum, letzte Jahre)"
        )

        with st.spinner("Lade historische Temperaturdaten..."):
            temp_history = get_temperaturen_pro_jahr_cached(
                top["Destination"], start_str, end_str
            )

        if temp_history is None or len(temp_history) == 0:
            st.warning("Keine historischen Temperaturdaten verfügbar.")
        else:
            # Jahre aufsteigend sortieren (aelteste links, neueste rechts)
            jahre = sorted(temp_history.keys())
            werte = [temp_history[j] for j in jahre]

            fig_line = go.Figure()
            fig_line.add_trace(go.Scatter(
                x=jahre,
                y=werte,
                mode="lines+markers+text",
                text=[f"{w}°C" for w in werte],
                textposition="top center",
                line=dict(color="#3b82f6", width=3),
                marker=dict(size=10),
                name="Ø Temperatur",
            ))
            # Wunsch-Temperatur als horizontale Referenzlinie einzeichnen,
            # damit man auf einen Blick sieht ob die Werte passen
            fig_line.add_hline(
                y=wunsch_temp,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Dein Wunsch: {wunsch_temp}°C",
                annotation_position="right",
            )
            fig_line.update_layout(
                xaxis_title="Jahr",
                yaxis_title="Durchschnittstemperatur (°C)",
                height=400,
            )
            st.plotly_chart(fig_line, use_container_width=True)

        # Tabelle als Backup, falls jemand die Rohdaten sehen will
        with st.expander("Alle Reiseziele als Tabelle anzeigen"):
            st.dataframe(ergebnis, use_container_width=True)