# ============================================================
# FitMyTrip - Streamlit-App
# ============================================================
# Das ist die Hauptdatei der App. Hier ist die ganze Streamlit-
# Oberflaeche drin: die zwei Tabs (Kriterien-Eingabe und
# Auswertung), die Charts, die Feedback-Funktion und der ganze
# Ablauf, wie aus den User-Inputs am Schluss eine Empfehlung wird.
# Alle Module aus den anderen Feature-Dateien werden hier
# zusammengefuehrt.
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import base64
from datetime import date
from pathlib import Path

from Feature_Database import filter_destinations
from Feature_Temperatur_API import (
    hole_durchschnittstemperatur,
    hole_temperaturen_pro_jahr,
     hole_temperaturen_batch_pro_jahr,
)
from Feature_Tagespreise_API import hole_tageskosten

from Feature_KNN_ML import trainiere_und_evaluiere, vorhersage_match_score
from Feature_Feedback_ML import speichere_feedback, anzahl_feedback

TEMP_TOLERANZ_STANDARD = 5
LOGO_PATH = "logo.png"

# Pfad zur CSV - die brauchen wir auch hier, um die Beschreibung der
# empfohlenen Destination auf der Auswertungs-Seite anzeigen zu koennen.
CSV_PFAD = Path(__file__).parent / "Destinations_Database.csv"

# Mapping fuer die Monatsnamen auf der x-Achse beim Liniendiagramm
MONATSNAMEN = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

# Farben - zentral definiert, damit das Layout konsistent bleibt
FARBE_TOP = "#2d8a3e"          # Gruen fuer das beste Match
FARBE_REST = "#555555"         # Dunkelgrau fuer alle anderen Eintraege
FARBE_WUNSCH = "#2d8a3e"       # Wunschprofil im Radar (gruen)
FARBE_DESTINATION = "#555555"  # Destination im Radar (dunkelgrau)

# Mindestanzahl Ergebnisse, bevor wir Constraints lockern (Fallback-Modus)
MIN_ERGEBNISSE = 3

# Wide-Layout, damit die zwei Charts auf der Auswertungs-Seite
# nebeneinander Platz haben
st.set_page_config(page_title="FitMyTrip", layout="wide", page_icon=LOGO_PATH)

# --- ML-Modell Training pro Session (neues Feedback von User löscht Cahce und ML-Modell wird neu trainiert) ----------------
@st.cache_resource(show_spinner="Trainiere ML-Modell...")
def lade_ml_modell():
    return trainiere_und_evaluiere()

# --- Logo als Base64 einlesen (fuer die Animation gebraucht) ----------------
@st.cache_data
def get_logo_base64():
    if not Path(LOGO_PATH).exists():
        return None
    with open(LOGO_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_b64 = get_logo_base64()


# --- Beschreibungen aus der CSV laden ---------------------------------------
@st.cache_data
def lade_beschreibungen():
    if not CSV_PFAD.exists():
        return {}
    df = pd.read_csv(CSV_PFAD, sep="\t", encoding="utf-8")
    if "Beschreibung" not in df.columns:
        return {}
    return dict(zip(df["Destination"], df["Beschreibung"]))


# --- Cached API-Wrapper -----------------------------------------------------
@st.cache_data(show_spinner=False)
def get_temperaturen_batch_cached(destinationen_tuple, start_str, end_str):
    return hole_temperaturen_batch_pro_jahr(
        list(destinationen_tuple), start_str, end_str
    )

@st.cache_data(show_spinner=False)
def get_tageskosten_cached(land):
    return hole_tageskosten(land)

@st.cache_data(show_spinner=False)
def get_temperaturen_pro_jahr_cached(destination, start_str, end_str):
    return hole_temperaturen_pro_jahr(destination, start_str, end_str)


# --- Match-Score-Logik ------------------------------------------------------
def berechne_sub_scores(row, wunsch_temp, budget, trip_duration_days):
    # Berechnet pro Reiseziel vier Einzelscores (jeweils 0-100%) und
    # daraus einen gleichgewichteten Gesamt-Match-Score.

    # Temperatur: bei 0 Grad Abweichung 100%, bei 15 Grad Abweichung 0%
    temp_diff = abs(row["Erwartete Temperatur (°C)"] - wunsch_temp)
    temp_score = max(0, 1 - temp_diff / 15)

    # Tagespreise vs. erlaubtes Tagesbudget
    erlaubtes_tagesbudget = budget / trip_duration_days
    verhaeltnis = row["Tageskosten (CHF)"] / erlaubtes_tagesbudget
    budget_score = max(0, min(1, 1 - verhaeltnis / 2))

    # Sicherheit: in der CSV ist niedriger = sicherer (skaliert 0-5)
    safety_score = max(0, 1 - row["Sicherheitsindex"] / 5)

    # Flugzeit: 0h = 100%, 5h = 0%
    flight_score = max(0, 1 - row["Flugzeit (ab ZRH)"] / 5)

    # Gesamt-Score = einfacher Mittelwert (alle Kriterien gleich gewichtet)
    gesamt = (temp_score + budget_score + safety_score + flight_score) / 4

    return {
        "Temperatur": round(temp_score * 100, 1),
        "Tagespreise": round(budget_score * 100, 1),
        "Sicherheit": round(safety_score * 100, 1),
        "Flugzeit": round(flight_score * 100, 1),
    }

def _lockerung_war_noetig(df_treffer, wunsch_temp, budget):
    # Prueft, ob die Lockerung in den tatsaechlichen Treffern auch greift.
    # Liefert True, sobald mind. ein Treffer ausserhalb der Stufe-0-Grenzen
    # liegt (Temp ausserhalb wunsch_temp ±5 °C oder Kosten > budget).
    # Wenn alle Treffer eh in den Stufe-0-Grenzen liegen, ist keine
    # Fallback-Meldung noetig - die Lockerung diente dann nur dazu,
    # MIN_ERGEBNISSE aufzufuellen.
    max_temp_abw = (df_treffer["Erwartete Temperatur (°C)"] - wunsch_temp).abs().max()
    if max_temp_abw > TEMP_TOLERANZ_STANDARD:
        return True
    if df_treffer["Geschätzte Gesamtkosten (CHF)"].max() > budget:
        return True
    return False


# Hard-Constraint-Fallback
def filtere_mit_fallback(df, wunsch_temp, budget):
    # Versucht zuerst die Original-Filter (Temp +/- 5, Budget exakt).
    # Wenn weniger als MIN_ERGEBNISSE uebrig sind, lockert die App
    # schrittweise: erst die Temperatur-Toleranz, dann das Budget.
    # Eine Stufen-Meldung wird nur dann zurueckgegeben, wenn die Lockerung
    # in den tatsaechlichen Treffern auch greift (mind. ein Treffer
    # ausserhalb der Stufe-0-Grenzen).
    fallback_meldung = None

    # Stufe 0: Original-Constraints
    df_filtered = df[
        (df["Erwartete Temperatur (°C)"] >= wunsch_temp - TEMP_TOLERANZ_STANDARD)
        & (df["Erwartete Temperatur (°C)"] <= wunsch_temp + TEMP_TOLERANZ_STANDARD)
        & (df["Geschätzte Gesamtkosten (CHF)"] <= budget)
    ]
    if len(df_filtered) >= MIN_ERGEBNISSE:
        return df_filtered, fallback_meldung

    # Stufe 1: Temperatur-Toleranz auf +/-10
    df_filtered = df[
        (df["Erwartete Temperatur (°C)"] >= wunsch_temp - 10)
        & (df["Erwartete Temperatur (°C)"] <= wunsch_temp + 10)
        & (df["Geschätzte Gesamtkosten (CHF)"] <= budget)
    ]
    if len(df_filtered) >= MIN_ERGEBNISSE:
        if _lockerung_war_noetig(df_filtered, wunsch_temp, budget):
            return df_filtered, "Temperatur-Toleranz auf ±10 °C erweitert"
        return df_filtered, None

    # Stufe 2: Budget +20%, Temperatur wie in Stufe 1
    df_filtered = df[
        (df["Erwartete Temperatur (°C)"] >= wunsch_temp - 10)
        & (df["Erwartete Temperatur (°C)"] <= wunsch_temp + 10)
        & (df["Geschätzte Gesamtkosten (CHF)"] <= budget * 1.2)
    ]
    if len(df_filtered) >= MIN_ERGEBNISSE:
        if _lockerung_war_noetig(df_filtered, wunsch_temp, budget):
            return df_filtered, "Budget um 20 % gelockert"
        return df_filtered, None

    # Stufe 3: Temperatur-Toleranz auf ±15 °C erweitert, Budget weiterhin +20%
    df_filtered = df[
        (df["Erwartete Temperatur (°C)"] >= wunsch_temp - 15)
        & (df["Erwartete Temperatur (°C)"] <= wunsch_temp + 15)
        & (df["Geschätzte Gesamtkosten (CHF)"] <= budget * 1.2)
    ]
    if len(df_filtered) >= MIN_ERGEBNISSE:
        if _lockerung_war_noetig(df_filtered, wunsch_temp, budget):
            return df_filtered, (
                "Temperatur-Toleranz auf ±15 °C erweitert und Budget um 20 % gelockert"
            )
        return df_filtered, None

    # Stufe 4: Temperatur wie Stufe 3 (±15 °C), aber Budget +50 %
    df_filtered = df[
        (df["Erwartete Temperatur (°C)"] >= wunsch_temp - 15)
        & (df["Erwartete Temperatur (°C)"] <= wunsch_temp + 15)
        & (df["Geschätzte Gesamtkosten (CHF)"] <= budget * 1.5)
    ]
    if len(df_filtered) >= MIN_ERGEBNISSE:
        if _lockerung_war_noetig(df_filtered, wunsch_temp, budget):
            return df_filtered, "Budget um 50 % gelockert"
        return df_filtered, None

    # Stufe 5: Letzte Reserve – Temperatur ignoriert (Budget bleibt +50 %)
    df_filtered = df[df["Geschätzte Gesamtkosten (CHF)"] <= budget * 1.5]
    if len(df_filtered) >= 1:
        if _lockerung_war_noetig(df_filtered, wunsch_temp, budget):
            return df_filtered, (
                "Temperatur-Limit ignoriert (deine Kriterien waren sehr streng)"
            )
        return df_filtered, None

    return df_filtered, "Selbst mit gelockerten Kriterien wenig gefunden"

# --- Lade-Animation mit Logo ------------------------------------------------
def zeige_lade_animation(platzhalter, text="Suche passende Reiseziele..."):
    if logo_b64 is None:
        platzhalter.info(text)
        return

    html = f"""
    <div style="display: flex; flex-direction: column; align-items: center;
                justify-content: center; padding: 60px 0;">
        <img src="data:image/png;base64,{logo_b64}"
             style="width: 180px; height: 180px;
                    animation: pulse 1.5s ease-in-out infinite;" />
        <p style="margin-top: 20px; font-size: 18px; color: #555;">{text}</p>
    </div>
    <style>
        @keyframes pulse {{
            0%   {{ transform: scale(1);    opacity: 1;   }}
            50%  {{ transform: scale(1.1);  opacity: 0.7; }}
            100% {{ transform: scale(1);    opacity: 1;   }}
        }}
    </style>
    """
    platzhalter.markdown(html, unsafe_allow_html=True)


# --- Logo-Header (kommt auf beiden Seiten) ----------------------------------
def zeige_logo_header():
    col_text, col_logo = st.columns([5, 1])
    with col_logo:
        if Path(LOGO_PATH).exists():
            st.image(LOGO_PATH, width=120)

# --- Tabs als "Seiten" ------------------------------------------------------
tab_input, tab_ergebnis = st.tabs(["Kriterien", "Auswertung"])


# ===========================================================================
# TAB 1: Eingabe-Seite
# ===========================================================================
with tab_input:
    zeige_logo_header()

    st.title("FitMyTrip")
    st.header("Finde dein Traumreiseziel in Europa!")

    st.markdown(
        "Bist auch Du überwältigt von der Auswahl verschiedener Reiseziele? "
        "Kein Problem! Unsere App liefert dir ein **personalisiertes Reiseziel** "
        "basierend auf verschiedenen **Matchmaking Kriterien**."
    )

    st.subheader("Kriterien Input")
    st.write("Folgende Kriterien stehen zur Auswahl:")

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
        "Bitte gib dein gewünschtes Sicherheitsniveau am Reiseziel ein: (von 1 tiefe Sicherheit bis 5 höchste Sicherheit)",
        1, 5, 1,
    )

    flighttime_label = st.selectbox(
        "Bitte gib die maximal zulässige Flugzeit von Zürich ein:",
        ["weniger als 1.5 Stunden", "1.5 bis 3 Stunden", "mehr als 3 Stunden"],
        index=None,
        placeholder="Bitte wählen",
    )

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
    trip_end = st.date_input("Bitte gib deinen gewünschten Endzeitpunkt ein: (Reisedauer von 2-21 Tagen möglich)")
    trip_duration_days = (trip_end - trip_start).days

    # Platzhalter fuer die Lade-Animation
    lade_platzhalter = st.empty()

    if st.button("Reiseziele finden"):
        # Validierung der Inputs
        if category is None:
            st.error("Bitte wähle eine Kategorie aus.")
        elif flighttime_label is None:
            st.error("Bitte wähle eine maximale Flugzeit aus.")
        elif trip_duration_days <= 0:
            st.error("Das Enddatum muss nach dem Startdatum liegen.")
        elif trip_duration_days < 2:
            st.error(
            f"Die Reisedauer muss mindestens 2 Tage betragen. "
            f"Aktuell sind es {trip_duration_days} Tag(e)."
          )
        elif trip_duration_days > 21:
             st.error(
             f"Die Reisedauer darf maximal 21 Tage betragen. "
              f"Aktuell sind es {trip_duration_days} Tage. "
             f"Bitte wähle einen kürzeren Zeitraum."
           )
        elif budget <= 0:
            st.error("Bitte gib ein Budget grösser als 0 ein.")
        else:
            zeige_lade_animation(lade_platzhalter, "Suche passende Reiseziele...")
            ml_data = lade_ml_modell() 

            ergebnis = filter_destinations(
                category=category,
                safety=safety,
                flighttime=flighttime_mapping[flighttime_label],
                budget=budget,
                trip_duration=trip_duration_days,
            )

            if len(ergebnis) > 0:
                for col in ("Destination", "Land", "Flugpreise"):
                    if col not in ergebnis.columns:
                        lade_platzhalter.empty()
                        st.error(f"Die Spalte '{col}' fehlt in der Datenbank.")
                        st.stop()

                ergebnis = ergebnis.copy()
                start_str = trip_start.strftime("%d.%m.%Y")
                end_str = trip_end.strftime("%d.%m.%Y")

                # Wetter-API im Batch: 5 API-Calls insgesamt statt 5 pro
                # Destination. Open-Meteo akzeptiert mehrere Koordinaten
                # in einem Request, wenn man sie kommagetrennt schickt.
                destinationen = tuple(ergebnis["Destination"].tolist())
                temp_data = get_temperaturen_batch_cached(
                    destinationen, start_str, end_str
                )
                temp_durchschnitt = temp_data["durchschnitt"]
 
                temperaturen, tageskosten = [], []
                for _, row in ergebnis.iterrows():
                    temperaturen.append(temp_durchschnitt.get(row["Destination"]))
                    tageskosten.append(get_tageskosten_cached(row["Land"]))
 
                ergebnis["Erwartete Temperatur (°C)"] = temperaturen
                ergebnis["Tageskosten (CHF)"] = tageskosten
 
                ergebnis["Geschätzte Gesamtkosten (CHF)"] = ergebnis.apply(
                    lambda r: None
                    if pd.isna(r["Tageskosten (CHF)"]) or pd.isna(r["Flugpreise"])
                    else round(r["Flugpreise"] + r["Tageskosten (CHF)"] * trip_duration_days, 0),
                    axis=1,
                )

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

                # Soft-Filter mit Fallback
                ergebnis, fallback_msg = filtere_mit_fallback(
                    ergebnis, temperature, budget
                )

                # ML-Score berechnen
                if len(ergebnis) > 0:
                    ml_scores = []
                    sub_scores_list = []
                    for _, row in ergebnis.iterrows():
                        score = vorhersage_match_score(
                            modell=ml_data["modell"],
                            scaler=ml_data["scaler"],
                            feature_spalten=ml_data["feature_spalten"],
                            wunsch_temp=temperature,
                            budget=budget,
                            reisetage=trip_duration_days,
                            dest_temp=row["Erwartete Temperatur (°C)"],
                            dest_tageskosten=row["Tageskosten (CHF)"],
                            dest_sicherheit=row["Sicherheitsindex"],
                            dest_flugzeit=row["Flugzeit (ab ZRH)"],
                        )
                        ml_scores.append(score)
                        sub_scores_list.append(
                            berechne_sub_scores(row, temperature, budget, trip_duration_days)
                        )
 
                    ergebnis["Match-Score (%)"] = ml_scores
                    sub_df = pd.DataFrame(sub_scores_list, index=ergebnis.index)
                    ergebnis = pd.concat([ergebnis, sub_df], axis=1)
                    ergebnis = ergebnis.sort_values("Match-Score (%)", ascending=False).reset_index(drop=True)
 
            else:
                fallback_msg = None

            lade_platzhalter.empty()

            # Alles in den session_state legen
            st.session_state["ergebnis"] = ergebnis
            st.session_state["wunsch_temp"] = temperature
            st.session_state["budget"] = budget
            st.session_state["trip_start"] = trip_start
            st.session_state["trip_start_str"] = trip_start.strftime("%d.%m.%Y")
            st.session_state["trip_end_str"] = trip_end.strftime("%d.%m.%Y")
            st.session_state["trip_duration_days"] = trip_duration_days
            st.session_state["ml_data"] = ml_data
            st.session_state["fallback_msg"] = fallback_msg

            if len(ergebnis) == 0:
                st.warning("Leider haben wir kein passendes Reiseziel gefunden. Versuche, deine Kriterien zu lockern.")
            else:
                if fallback_msg:
                    st.info(
                        f"Hinweis: Die Kriterien waren sehr streng. "
                        f"Wir haben diese etwas gelockert, "
                        f"damit wir trotzdem Empfehlungen zeigen können."
                    )
                st.success(
                    f"{len(ergebnis)} passende Reiseziele gefunden. "
                    f"Wechsle jetzt oben auf den Tab **Auswertung**."
                    )


# ===========================================================================
# TAB 2: Auswertungs-Seite mit den Charts
# ===========================================================================
with tab_ergebnis:
    zeige_logo_header()

    if "ergebnis" not in st.session_state:
        st.info("Bitte zuerst im Tab **Kriterien** Reiseziele suchen.")
    elif len(st.session_state["ergebnis"]) == 0:
        st.warning("Es wurden keine Reiseziele gefunden, die zu deinen Kriterien passen.")
    else:
        ergebnis = st.session_state["ergebnis"]
        wunsch_temp = st.session_state["wunsch_temp"]
        trip_start = st.session_state["trip_start"]
        start_str = st.session_state["trip_start_str"]
        end_str = st.session_state["trip_end_str"]
        trip_duration_days = st.session_state["trip_duration_days"]
        ml_data = st.session_state["ml_data"]
        fallback_msg = st.session_state.get("fallback_msg")

        st.title("Reiseziel-Finder – Deine persönliche Auswertung")

        # Top-Reiseziel = erste Zeile (oben absteigend nach Score sortiert)
        top = ergebnis.iloc[0]

        # Erfolgs-Banner mit Top-Match
        st.success(
            f"Dein bestes Match: **{top['Destination']}** ({top['Land']}) "
            f"mit {top['Match-Score (%)']}% Übereinstimmung"
        )

        if fallback_msg:
            st.warning(
                f"Hinweis: Wir haben die Kriterien gelockert, um Empfehlungen zu zeigen. "
                f"Konkret: {fallback_msg}."
            )

        # --- Beschreibung der Top-Destination -----------------------------
        beschreibung_top = top.get("Beschreibungen")
        if not beschreibung_top or (isinstance(beschreibung_top, float) and pd.isna(beschreibung_top)):
            beschreibungen_dict = lade_beschreibungen()
            beschreibung_top = beschreibungen_dict.get(top["Destination"])
            st.markdown(
                f"<div style='background-color:#f5f5f5; padding:18px 22px; "
                f"border-left:4px solid {FARBE_TOP}; border-radius:4px; "
                f"margin:14px 0 22px 0; font-size:15px; line-height:1.55;'>"
                f"<strong>Über {top['Destination']}:</strong><br>"
                f"{beschreibung_top}</div>",
                unsafe_allow_html=True,
            )

        # --- Charts nebeneinander -----------------------------------------
        col1, col2 = st.columns(2)

        # CHART 1: Bar-Chart Ranking
        # Top-Match in Gruen, alle anderen in Dunkelgrau
        with col1:
            st.subheader("Reiseziel-Ranking")

            top10 = ergebnis.head(10).copy()

            # Farb-Liste: erstes Element (Top-Match) gruen, Rest dunkelgrau.
            # Index 0 ist der Top-Treffer, weil das DataFrame absteigend
            # nach Match-Score sortiert ist.
            farben = [FARBE_REST] * len(top10)
            farben[0] = FARBE_TOP

            fig_bar = px.bar(
                top10,
                x="Match-Score (%)",
                y="Destination",
                orientation="h",
                text="Match-Score (%)",
            )
            fig_bar.update_traces(
                marker_color=farben,
                texttemplate="%{text:.1f}%",
                textposition="outside",
                textfont=dict(size=11, color="#333"),
                # Sehr duenne Balken (0.125 = halb so dick wie zuvor)
                width=0.125,
                # cliponaxis=False sorgt dafuer, dass die Beschriftung am
                # Rand nicht abgeschnitten wird
                cliponaxis=False,
            )

            fig_bar.update_layout(
                yaxis={
                    "categoryorder": "total ascending",
                    "title": dict(text="Reiseziel", font=dict(size=12)),
                },
                xaxis={
                    "title": dict(
                        text="Match-Score (%) – Übereinstimmung mit deinen Präferenzen",
                        font=dict(size=12),
                    ),
                    "range": [0, 115],
                },
                showlegend=False,
                height=450,
                bargap=0.55,
                margin=dict(t=20, b=50, l=10, r=30),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Beschreibung unter dem Chart
            st.caption(
                "Diese Grafik zeigt die top Reiseziele mit der höchsten Übereinstimmung "
                "zu deinen Kriterien. Der grüne Balken markiert dein Top-Match, die anderen "
                "Reiseziele sind grau dargestellt. Die Prozentzahl gibt an, wie gut das jeweilige "
                "Reiseziel insgesamt zu deinen Wünschen passt (100% = perfekter Match)."
            )

        # CHART 2: Radar-Chart - Profilvergleich
        with col2:
            st.subheader(f"Profilvergleich: Wunsch vs. {top['Destination']}")

            # Achsen-Labels mit Original-Skala in der zweiten Zeile.
            # Plotly unterstuetzt <br> fuer Zeilenumbrueche in Achsen-Labels.
            kategorien = [
                "Temperatur<br>(0–15°C Δ)",
                "Tagespreise<br>(0–2× Budget)",
                "Sicherheit<br>(Index 0–5)",
                "Flugzeit<br>(0–5 Std.)",
            ]
            wunsch_werte = [100, 100, 100, 100]
            ziel_werte = [
                top["Temperatur"],
                top["Tagespreise"],
                top["Sicherheit"],
                top["Flugzeit"],
            ]

            fig_radar = go.Figure()

            # Wunsch-Profil (gruen)
            fig_radar.add_trace(go.Scatterpolar(
                r=wunsch_werte + [wunsch_werte[0]],
                theta=kategorien + [kategorien[0]],
                fill="toself",
                name="Dein Wunsch",
                line=dict(color=FARBE_WUNSCH, width=2),
                fillcolor="rgba(45, 138, 62, 0.25)",
            ))

            # Empfohlene Destination (dunkelgrau)
            fig_radar.add_trace(go.Scatterpolar(
                r=ziel_werte + [ziel_werte[0]],
                theta=kategorien + [kategorien[0]],
                fill="toself",
                name=top["Destination"],
                line=dict(color=FARBE_DESTINATION, width=2),
                fillcolor="rgba(85, 85, 85, 0.35)",
            ))

            # Domain einschraenken, damit die Achsen-Labels drumherum
            # genug Platz haben und nicht abgeschnitten werden.
            # Tickvals 0/25/50/75/100 sorgen fuer eine klare Skala.
            fig_radar.update_layout(
                polar=dict(
                    domain=dict(x=[0.05, 0.95], y=[0.18, 0.92]),
                    radialaxis=dict(
                        visible=True,
                        range=[0, 100],
                        tickvals=[0, 25, 50, 75, 100],
                        ticktext=["0%", "25%", "50%", "75%", "100%"],
                        tickfont=dict(size=9, color="#777"),
                        gridcolor="#ddd",
                    ),
                    angularaxis=dict(
                        tickfont=dict(size=11),
                        rotation=90,
                        direction="clockwise",
                    ),
                ),
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom", y=-0.05,
                    xanchor="center", x=0.5,
                    font=dict(size=11),
                ),
                height=420,
                margin=dict(t=30, b=20, l=20, r=20),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

            # Echte Werte der Destination als kleine Datenbox darunter.
            # So sieht man neben dem Radar (Match-Score in %) auch die
            # tatsaechlichen Zahlen, auf denen das Scoring basiert.
            trip_dauer = (
                pd.to_datetime(st.session_state["trip_end_str"], format="%d.%m.%Y")
                - pd.to_datetime(st.session_state["trip_start_str"], format="%d.%m.%Y")
            ).days
            tagesbudget = round(st.session_state["budget"] / max(1, trip_dauer))

            st.markdown(
                f"<div style='background-color:#fafafa; padding:12px 16px; "
                f"border-radius:4px; font-size:13px; margin-top:8px;'>"
                f"<strong>Echte Werte in {top['Destination']}:</strong><br>"
                f"&bull; Erwartete Temperatur: <strong>{top['Erwartete Temperatur (°C)']}°C</strong> "
                f"(dein Wunsch: {wunsch_temp}°C)<br>"
                f"&bull; Tageskosten: <strong>{top['Tageskosten (CHF)']} CHF</strong> "
                f"(dein Tagesbudget: {tagesbudget} CHF)<br>"
                f"&bull; Sicherheitsindex: <strong>{top['Sicherheitsindex']} / 5</strong> "
                f"(0 = sehr sicher, 5 = unsicher)<br>"
                f"&bull; Flugzeit ab Zürich: <strong>{top['Flugzeit (ab ZRH)']} Std.</strong>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Beschreibung unter dem Chart
            st.caption(
                "Der Radar vergleicht dein Wunschprofil (grün, immer 100% pro Achse) mit der "
                "empfohlenen Destination (grau). Je näher die graue Fläche an der grünen liegt, "
                "desto besser passt das Reiseziel zu deinen Wünschen. Die Achsen zeigen je einen "
                "Match-Score von 0% bis 100%."
            )

        # CHART 3: Liniendiagramm Temperaturentwicklung der Top-Empfehlung
        st.markdown("---")
        reise_monat_name = MONATSNAMEN[trip_start.month]
        st.subheader(
            f"Temperaturentwicklung in {top['Destination']} im {reise_monat_name}"
        )

        with st.spinner("Lade historische Temperaturdaten..."):
            temp_history = get_temperaturen_pro_jahr_cached(
                top["Destination"], start_str, end_str
            )

        if temp_history is None or len(temp_history) == 0:
            st.warning("Keine historischen Temperaturdaten verfügbar.")
        else:
            jahre = sorted(temp_history.keys())
            werte = [temp_history[j] for j in jahre]
            labels = [f"{reise_monat_name} {j}" for j in jahre]

            fig_line = go.Figure()
            fig_line.add_trace(go.Scatter(
                x=labels,
                y=werte,
                mode="lines+markers+text",
                text=[f"{w}°C" for w in werte],
                textposition="top center",
                textfont=dict(size=12, color="#333"),
                line=dict(color=FARBE_TOP, width=2.5),
                marker=dict(size=8, color=FARBE_TOP),
                name="Ø Temperatur",
            ))
            fig_line.add_hline(
                y=wunsch_temp,
                line_dash="dash",
                line_color="#d65555",
                annotation_text=f"Dein Wunsch: {wunsch_temp}°C",
                annotation_position="right",
                annotation_font=dict(size=10),
            )

            # Y-Achsen-Bereich mit Puffer
            alle_y_werte = werte + [wunsch_temp]
            y_min = min(alle_y_werte) - 3
            y_max = max(alle_y_werte) + 4

            fig_line.update_layout(
                xaxis_title="Reisemonat (letzte Jahre)",
                yaxis_title="Ø Temperatur (°C)",
                height=260,
                yaxis=dict(range=[y_min, y_max], tickfont=dict(size=10)),
                xaxis=dict(tickfont=dict(size=10)),
                margin=dict(t=30, b=40, l=50, r=40),
            )

            # Linie in eine schmalere Spalte packen
            col_links, col_rechts = st.columns([3, 2])
            with col_links:
                st.plotly_chart(fig_line, use_container_width=True)
                st.caption(
                    f"Diese Grafik zeigt die Durchschnittstemperatur in {top['Destination']} "
                    f"im {reise_monat_name} über die letzten fünf Jahre. Die rote gestrichelte "
                    f"Linie markiert deine Wunschtemperatur ({wunsch_temp}°C). So siehst du, "
                    f"wie zuverlässig die Temperaturen in diesem Reisezeitraum waren und wie "
                    f"gross die jährlichen Schwankungen sind."
                )

        # ====================================================================
        # FEEDBACK-SEKTION
        # ====================================================================
        st.markdown("---")
        st.subheader("Wie gut passt diese Empfehlung zu dir?")
        st.markdown(
            "Deine Bewertung hilft, das Modell zu verbessern. Beim nächsten Suchvorgang "
            "fliessen alle bisherigen Bewertungen in die Empfehlungen ein."
        )
 
        col_fb1, col_fb2 = st.columns([2, 3])
        with col_fb1:
            sterne = st.slider(
                f"Bewertung für {top['Destination']}",
                min_value=1, max_value=5, value=3,
                help="1 = passt nicht, 5 = perfekter Match",
                key="feedback_sterne",
            )
            st.markdown(
                f"<div style='font-size:24px; color:{FARBE_TOP}; "
                f"letter-spacing: 4px; margin-top: -8px;'>"
                f"{'★' * sterne}{'☆' * (5 - sterne)}</div>",
                unsafe_allow_html=True,
            )
 
        with col_fb2:
            st.write("")
            if st.button("Bewertung speichern", key="speichere_feedback"):
                eintrag = {
                    "user_inputs": {
                        "wunsch_temp": float(wunsch_temp),
                        "budget": float(st.session_state["budget"]),
                        "reisetage": int(trip_duration_days),
                    },
                    "destination": top["Destination"],
                    "destination_features": {
                        "dest_temp": float(top["Erwartete Temperatur (°C)"]),
                        "dest_tageskosten": float(top["Tageskosten (CHF)"]),
                        "dest_sicherheit": float(top["Sicherheitsindex"]),
                        "dest_flugzeit": float(top["Flugzeit (ab ZRH)"]),
                    },
                    "rating_stars": int(sterne),
                }
                gesamt = speichere_feedback(eintrag)
 
                # ML-Cache leeren -> Modell wird beim naechsten Suchvorgang
                # mit dem neuen Feedback neu trainiert
                lade_ml_modell.clear()
 
                st.success(
                    f"Bewertung gespeichert ({gesamt} Bewertungen insgesamt). "
                    f"Beim nächsten Suchvorgang wird das Modell mit deinem Feedback "
                    f"neu trainiert."
                )
 
        st.caption(
            f"Bisher wurden insgesamt **{anzahl_feedback()}** Bewertungen gesammelt. "
            f"Je mehr Feedback, desto besser werden die Empfehlungen."
        )
 
        # ====================================================================
        # ML-PERFORMANCE-SEKTION (im Expander)
        # ====================================================================
        with st.expander("Technische Details: Performance unseres ML-Modells"):
            st.markdown(
                f"Unser KNN-Regressor (k = **{ml_data['bestes_k']}**) wurde auf "
                f"**{ml_data['anzahl_trainingsdaten']} Trainings-** und "
                f"**{ml_data['anzahl_testdaten']} Testbeispielen** evaluiert. "
                f"Auf den Testdaten erreicht das Modell ein **R² von {ml_data['r2_final']}** "
                f"und einen mittleren absoluten Fehler von **{ml_data['mae_final']} Prozentpunkten**. "
                f"Davon sind **{ml_data['anzahl_feedback_eintraege']} echte User-Bewertungen** "
                f"in das Training eingeflossen."
            )
 
            col_ml1, col_ml2 = st.columns(2)
 
            with col_ml1:
                st.markdown("**Hyperparameter-Tuning: bestes k finden**")
 
                tuning = ml_data["tuning_ergebnisse"]
                ks = [t["k"] for t in tuning]
                r2s = [t["r2"] for t in tuning]
                farben_k = [FARBE_TOP if k == ml_data["bestes_k"] else FARBE_REST for k in ks]
 
                fig_tuning = go.Figure()
                fig_tuning.add_trace(go.Scatter(
                    x=ks, y=r2s,
                    mode="lines",
                    line=dict(color="#bbb", width=2),
                    showlegend=False,
                    hoverinfo="skip",
                ))
                fig_tuning.add_trace(go.Scatter(
                    x=ks, y=r2s,
                    mode="markers+text",
                    marker=dict(size=14, color=farben_k,
                                line=dict(color="white", width=2)),
                    text=[f"{r:.3f}" for r in r2s],
                    textposition="top center",
                    textfont=dict(size=10, color="#333"),
                    showlegend=False,
                ))
                fig_tuning.update_layout(
                    xaxis=dict(
                        title=dict(text="k (Anzahl Nachbarn)", font=dict(size=12)),
                        tickvals=ks,
                        tickfont=dict(size=10),
                    ),
                    yaxis=dict(
                        title=dict(text="R² (auf Testdaten)", font=dict(size=12)),
                        tickfont=dict(size=10),
                    ),
                    height=320,
                    margin=dict(t=20, b=40, l=50, r=20),
                )
                st.plotly_chart(fig_tuning, use_container_width=True)
 
                st.caption(
                    f"Wir haben das Modell für verschiedene Werte von k trainiert "
                    f"und R² auf dem Testset gemessen. Das beste k ist **{ml_data['bestes_k']}** "
                    f"(grün hervorgehoben)."
                )
 
            with col_ml2:
                st.markdown("**Vorhersagegenauigkeit: Vorhergesagt vs. Tatsächlich**")
 
                y_test = ml_data["y_test"]
                y_pred = ml_data["y_pred_test"]
 
                fig_scatter = go.Figure()
                fig_scatter.add_trace(go.Scatter(
                    x=y_test, y=y_pred,
                    mode="markers",
                    marker=dict(
                        size=8,
                        color=FARBE_TOP,
                        opacity=0.6,
                        line=dict(color="white", width=1),
                    ),
                    name="Testbeispiele",
                    showlegend=False,
                ))
                min_val = min(min(y_test), min(y_pred))
                max_val = max(max(y_test), max(y_pred))
                fig_scatter.add_trace(go.Scatter(
                    x=[min_val, max_val], y=[min_val, max_val],
                    mode="lines",
                    line=dict(color="#d65555", dash="dash", width=2),
                    name="Perfekte Vorhersage",
                    showlegend=False,
                ))
                fig_scatter.update_layout(
                    xaxis=dict(
                        title=dict(text="Tatsächlicher Score (%)", font=dict(size=12)),
                        tickfont=dict(size=10),
                    ),
                    yaxis=dict(
                        title=dict(text="Vorhergesagter Score (%)", font=dict(size=12)),
                        tickfont=dict(size=10),
                    ),
                    height=320,
                    margin=dict(t=20, b=40, l=50, r=20),
                )
                st.plotly_chart(fig_scatter, use_container_width=True)
 
                st.caption(
                    "Jeder Punkt ist ein Testbeispiel. Die rote Linie zeigt, "
                    "wo eine perfekte Vorhersage liegen würde."
                )


        # Tabelle als Backup, falls jemand die Rohdaten sehen will
        with st.expander("Alle Reiseziele als Tabelle anzeigen"):
            anzeige_df = ergebnis.drop(columns=["Beschreibung"], errors="ignore")
            st.dataframe(anzeige_df, use_container_width=True)