import pandas as pd

#User Input von Safety muss invertiert werden und wird anhand der Index-Werte in Quartile unterteilt
safety_schwellen = {
    1: float("inf"),
    2: 3.1,
    3: 2.7,
    4: 1.7,
    5: 1.1,
}

csv_pfad = "/Users/benjaminduscio/Documents/HSG/BBWL/S6/Informatik/Projekt/Database CSV.csv"

def filter_destinations(category, safety, flighttime, budget, trip_duration, flight_cost):

    """
    Filtert Destinationen nach den User-Parametern.
    
    Args:
        category (str): "Berge", "Meer", "Stadt", "Natur"
        safety (int): 1 (egal) bis 5 (Sicherheit sehr wichtig)
        flighttime (float): maximale Flugzeit in Stunden
        budget (float): Gesamtbudget in CHF
        trip_duration (int): Reisedauer in Tagen
        flight_cost (float): Flugkosten in CHF (von API)
    
    Returns:
        pd.DataFrame: Gefilterte Destinationen
    """

    daily_budget = (budget - flight_cost) / trip_duration

    df = pd.read_csv(csv_pfad, encoding="mac-roman")
    df_copy = df.copy()

    #Filterung der CSV Datei gemäss User-Inputs
    df_filtered = df_copy[(df_copy["Kategorie (Primär)"].str.contains(category)) 
                        & (df_copy["Sicherheitsindex"] <= safety_schwellen[safety]) 
                        & (df_copy["Tageskosten (Ø CHF)"] <= daily_budget)
                        & (df_copy["Flugzeit (ab ZRH)"] <= flighttime)]
    return df_filtered

# Test-Block: läuft nur, wenn diese Datei direkt ausgeführt wird
if __name__ == "__main__":
    ergebnis = filter_destinations(
        category="Meer",
        safety=3,
        flighttime=2.7,
        budget=2500,
        trip_duration=3,
        flight_cost=200,
    )
    print(ergebnis)

