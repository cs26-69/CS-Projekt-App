import pandas as pd

# Datei wird als UTF-8 gelesen (so liegt sie aktuell vor)
df = pd.read_csv("Destinations_Database.csv", encoding="utf-8")

# Jeden String "rückwärts" durchs falsche Encoding schicken:
# UTF-8 -> Bytes -> als Mac-Roman interpretieren = Original
def fix(text):
    if isinstance(text, str):
        try:
            return text.encode("mac-roman").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text

# Auf alle String-Spalten und Spaltennamen anwenden
df = df.map(fix)
df.columns = [fix(col) for col in df.columns]

# Sauber als UTF-8 speichern
df.to_csv("Destinations_Database.csv", index=False, encoding="utf-8")

print("Repariert! Spalten:", df.columns.tolist())
print(df.head())