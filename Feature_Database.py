import pandas as pd
from pathlib import Path

#User Input von Safety muss invertiert werden und wird anhand der Index-Werte in Quartile unterteilt
safety_schwellen = {
    1: float("inf"),
    2: 3.1,
    3: 2.7,
    4: 1.7,
    5: 1.1,
}

csv_pfad = Path(__file__).parent / "Destinations_Database.csv"

def filter_destinations(category, safety, flighttime, budget, trip_duration):

    """
    Filtert Destinationen nach den User-Parametern.
    
    Args:
        category (str): "Berge", "Meer", "Stadt", "Natur"
        safety (int): 1 (egal) bis 5 (Sicherheit sehr wichtig)
        flighttime (float): maximale Flugzeit in Stunden
        budget (float): Gesamtbudget in CHF
        trip_duration (int): Reisedauer in Tagen
    
    Returns:
        pd.DataFrame: Gefilterte Destinationen
    """

    df = pd.read_csv(csv_pfad, encoding="utf-8")
    df_copy = df.copy()

    df_copy["daily_budget"] = (budget - df_copy["Flugpreise"]) / trip_duration

    #Filterung der CSV Datei gemäss User-Inputs
    df_filtered = df_copy[(df_copy["Kategorie (Primär)"].str.contains(category)) 
                        & (df_copy["Sicherheitsindex"] <= safety_schwellen[safety]) 
                        & (df_copy["Flugzeit (ab ZRH)"] <= flighttime)
                        & (df_copy["daily_budget"] >= 0)]

    return df_filtered

# Test-Block: läuft nur, wenn diese Datei direkt ausgeführt wird
if __name__ == "__main__":
    ergebnis = filter_destinations(
        category="Meer",
        safety=3,
        flighttime=2.7,
        budget=2500,
        trip_duration=3,
    )
    print(ergebnis)
