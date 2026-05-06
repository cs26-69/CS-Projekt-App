# ============================================================
# Machine Learning Modul fuer FitMyTrip
# ============================================================
# Implementiert eine K-Nearest-Neighbors Regression (KNN) gemaess
# dem Vorlesungsstoff aus Woche 10 (Data Science III: Machine Learning).
#
# Ziel: Ersatz der manuellen Match-Score-Formel durch ein gelerntes
# Modell. Das Modell wird mit synthetischen Trainingsdaten trainiert
# und kann zusaetzlich durch echtes User-Feedback (Sterne-Bewertungen)
# nachtrainiert werden.
#
# Verwendete Konzepte (alle aus der Vorlesung):
#   - Supervised Learning, speziell Regression (Folie 28, 42, 77)
#   - K-Nearest Neighbors (Folie 67-75)
#   - MinMax-Skalierung (Folie 71)
#   - Train/Test-Split (Folie 55-56, 59)
#   - Hyperparameter-Tuning (Folie 75)
#   - Evaluation mit R^2 und MAE

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error

from Feature_Feedback import lade_feedback


CSV_PFAD = Path(__file__).parent / "Destinations_Database.csv"

RANDOM_SEED = 42
ANZAHL_TRAININGSBEISPIELE = 500

# Realistische Wertebereiche fuer User-Inputs (entsprechen genau
# dem, was in der App eingegeben werden kann).
WUNSCH_TEMP_MIN = -10
WUNSCH_TEMP_MAX = 35
BUDGET_MIN = 500
BUDGET_MAX = 5000
REISETAGE_MIN = 2
REISETAGE_MAX = 21


# ============================================================
# Hilfsfunktion: "wahrer" Match-Score (gleiche Formel wie zuvor)
# ============================================================
def _wahrer_score(wunsch_temp, budget, reisetage,
                  dest_temp, dest_tageskosten,
                  dest_sicherheit, dest_flugzeit):
    temp_diff = abs(dest_temp - wunsch_temp)
    temp_score = max(0, 1 - temp_diff / 15)

    erlaubtes_tagesbudget = budget / max(1, reisetage)
    verhaeltnis = dest_tageskosten / max(1, erlaubtes_tagesbudget)
    budget_score = max(0, min(1, 1 - verhaeltnis / 2))

    safety_score = max(0, 1 - dest_sicherheit / 5)
    flight_score = max(0, 1 - dest_flugzeit / 5)

    gesamt = (temp_score + budget_score + safety_score + flight_score) / 4
    return gesamt * 100


# ============================================================
# Schritt 1a: Synthetische Trainingsdaten generieren
# ============================================================
def generiere_synthetische_trainingsdaten(n=ANZAHL_TRAININGSBEISPIELE):
    rng = np.random.default_rng(RANDOM_SEED)
    df = pd.read_csv(CSV_PFAD, encoding="utf-8")

    laender_tageskosten = {
        "Schweiz": 170, "Norwegen": 145, "Island": 145, "Dänemark": 140,
        "Schweden": 130, "Finnland": 120, "Irland": 115, "UK": 115,
        "Frankreich": 110, "Belgien": 110, "Niederlande": 110,
        "Deutschland": 105, "Österreich": 105, "Italien": 100,
        "Spanien": 95, "Malta": 95, "Slowenien": 90, "Portugal": 90,
        "Griechenland": 85, "Tschechien": 75, "Kroatien": 80,
        "Slowakei": 70, "Polen": 70, "Ungarn": 70,
        "Rumänien": 65, "Bulgarien": 60, "Serbien": 60, "Albanien": 55,
    }

    daten = []
    for _ in range(n):
        wunsch_temp = rng.uniform(WUNSCH_TEMP_MIN, WUNSCH_TEMP_MAX)
        budget = rng.uniform(BUDGET_MIN, BUDGET_MAX)
        reisetage = rng.integers(REISETAGE_MIN, REISETAGE_MAX + 1)

        zeile = df.sample(n=1, random_state=int(rng.integers(0, 10**9))).iloc[0]
        dest_temp = rng.uniform(5, 30)
        dest_tageskosten = laender_tageskosten.get(zeile["Land"], 100)
        dest_sicherheit = float(zeile["Sicherheitsindex"])
        dest_flugzeit = float(zeile["Flugzeit (ab ZRH)"])

        score_clean = _wahrer_score(
            wunsch_temp, budget, reisetage,
            dest_temp, dest_tageskosten, dest_sicherheit, dest_flugzeit,
        )
        rauschen = rng.normal(0, 5)
        score_mit_rauschen = max(0, min(100, score_clean + rauschen))

        daten.append({
            "wunsch_temp": wunsch_temp,
            "budget": budget,
            "reisetage": reisetage,
            "dest_temp": dest_temp,
            "dest_tageskosten": dest_tageskosten,
            "dest_sicherheit": dest_sicherheit,
            "dest_flugzeit": dest_flugzeit,
            "match_score": score_mit_rauschen,
            "quelle": "synthetisch",
        })

    return pd.DataFrame(daten)


# ============================================================
# Schritt 1b: Echtes User-Feedback in Trainingsdaten umwandeln
# ============================================================
def feedback_zu_trainingsdaten():
    # Liest die gespeicherten Sterne-Bewertungen und macht daraus
    # Trainingsdaten im gleichen Format wie die synthetischen Daten.
    # 1 Stern -> 20% Match, 2 -> 40%, ..., 5 -> 100%
    feedback = lade_feedback()
    if not feedback:
        return pd.DataFrame()

    rows = []
    for eintrag in feedback:
        try:
            ui = eintrag["user_inputs"]
            df_feat = eintrag["destination_features"]
            sterne = eintrag["rating_stars"]

            rows.append({
                "wunsch_temp": ui["wunsch_temp"],
                "budget": ui["budget"],
                "reisetage": ui["reisetage"],
                "dest_temp": df_feat["dest_temp"],
                "dest_tageskosten": df_feat["dest_tageskosten"],
                "dest_sicherheit": df_feat["dest_sicherheit"],
                "dest_flugzeit": df_feat["dest_flugzeit"],
                "match_score": sterne * 20,  # 1 Stern -> 20%, 5 -> 100%
                "quelle": "feedback",
            })
        except (KeyError, TypeError):
            # Defekte Eintraege ueberspringen, statt zu crashen
            continue

    return pd.DataFrame(rows)


# ============================================================
# Schritt 2: Modell trainieren und evaluieren
# ============================================================
def trainiere_und_evaluiere(k_zum_testen=(1, 3, 5, 7, 9, 11)):
    # Synthetische Trainingsdaten generieren
    df_synth = generiere_synthetische_trainingsdaten()

    # Echtes Feedback laden (kann leer sein)
    df_feedback = feedback_zu_trainingsdaten()
    anzahl_feedback = len(df_feedback)

    # Beide Quellen kombinieren. Falls Feedback vorhanden ist, geben
    # wir ihm extra Gewicht, indem wir es 3x duplizieren - so haben
    # echte User-Bewertungen mehr Einfluss als die kuenstlichen Daten.
    if anzahl_feedback > 0:
        df_feedback_gewichtet = pd.concat(
            [df_feedback] * 3, ignore_index=True
        )
        df = pd.concat([df_synth, df_feedback_gewichtet], ignore_index=True)
    else:
        df = df_synth

    # Features (X) und Target (y) trennen
    feature_spalten = [
        "wunsch_temp", "budget", "reisetage",
        "dest_temp", "dest_tageskosten", "dest_sicherheit", "dest_flugzeit",
    ]
    X = df[feature_spalten].values
    y = df["match_score"].values

    # Skalierung (Folie 71)
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    # Train/Test-Split 70/30 (Folie 56, 59)
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.30, random_state=RANDOM_SEED
    )

    # Hyperparameter-Tuning: bestes k finden (Folie 75)
    tuning_ergebnisse = []
    for k in k_zum_testen:
        modell = KNeighborsRegressor(n_neighbors=k)
        modell.fit(X_train, y_train)
        y_pred_test = modell.predict(X_test)
        r2 = r2_score(y_test, y_pred_test)
        mae = mean_absolute_error(y_test, y_pred_test)
        tuning_ergebnisse.append({
            "k": k,
            "r2": round(r2, 4),
            "mae": round(mae, 2),
        })

    bestes_k = max(tuning_ergebnisse, key=lambda x: x["r2"])["k"]

    # Finales Modell trainieren
    finales_modell = KNeighborsRegressor(n_neighbors=bestes_k)
    finales_modell.fit(X_train, y_train)

    y_pred_final = finales_modell.predict(X_test)
    r2_final = r2_score(y_test, y_pred_final)
    mae_final = mean_absolute_error(y_test, y_pred_final)

    return {
        "modell": finales_modell,
        "scaler": scaler,
        "feature_spalten": feature_spalten,
        "bestes_k": bestes_k,
        "r2_final": round(r2_final, 4),
        "mae_final": round(mae_final, 2),
        "tuning_ergebnisse": tuning_ergebnisse,
        "y_test": y_test.tolist(),
        "y_pred_test": y_pred_final.tolist(),
        "anzahl_trainingsdaten": len(X_train),
        "anzahl_testdaten": len(X_test),
        "anzahl_feedback_eintraege": anzahl_feedback,
    }


# ============================================================
# Schritt 3: Mit dem trainierten Modell Vorhersagen machen
# ============================================================
def vorhersage_match_score(modell, scaler, feature_spalten,
                            wunsch_temp, budget, reisetage,
                            dest_temp, dest_tageskosten,
                            dest_sicherheit, dest_flugzeit):
    feature_vektor = np.array([[
        wunsch_temp, budget, reisetage,
        dest_temp, dest_tageskosten, dest_sicherheit, dest_flugzeit,
    ]])
    feature_skaliert = scaler.transform(feature_vektor)
    score = float(modell.predict(feature_skaliert)[0])
    score = max(0, min(100, score))
    return round(score, 1)


# ============================================================
# Testblock
# ============================================================
if __name__ == "__main__":
    print("Trainiere KNN-Regressor...")
    ergebnis = trainiere_und_evaluiere()

    print(f"\nTrainingsdaten: {ergebnis['anzahl_trainingsdaten']} Beispiele")
    print(f"Testdaten:      {ergebnis['anzahl_testdaten']} Beispiele")
    print(f"Feedback-Eintraege:  {ergebnis['anzahl_feedback_eintraege']}")
    print(f"\nBestes k: {ergebnis['bestes_k']}")
    print(f"R^2 (Test): {ergebnis['r2_final']}")
    print(f"MAE (Test): {ergebnis['mae_final']}")