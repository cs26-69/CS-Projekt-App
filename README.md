# CS-Projekt-App
This is the repository for our CS Project.
# FitMyTrip

Das ist unser CS-Projekt. FitMyTrip ist eine Web-App, die dir dabei hilft, in Europa ein passendes Reiseziel zu finden.

## Worum geht's?

Wenn man verreisen will, hat man oft einfach zu viel Auswahl. Welches Land, welche Stadt, passt das zum Budget, zur Reisezeit, zum Wetter, das man sich vorstellt? Genau diese Recherche nimmt unsere App ab. Du sagst ihr, was dir wichtig ist, und sie schlägt dir das Reiseziel vor, das am besten dazu passt.

## Wie funktioniert das?

Du gibst im ersten Tab deine Kriterien an: Kategorie (Berge, Meer, Stadt oder Natur), gewünschte Temperatur, Sicherheitsniveau, maximale Flugzeit ab Zürich, Budget und Reisedauer.

Die App filtert dann unsere Destinations-Datenbank nach den harten Kriterien. Für jede übriggebliebene Destination werden zwei APIs angefragt: Open-Meteo liefert die durchschnittliche Temperatur im gewünschten Reisezeitraum (gemittelt über die letzten 5 Jahre), Eurostat liefert die typischen Tageskosten für Restaurants und Hotels.

Aus all diesen Daten berechnet ein KNN-Regressor einen Match-Score in Prozent. Im zweiten Tab siehst du dann das Ranking, einen Radar-Chart mit dem Profilvergleich und die Temperaturentwicklung der letzten Jahre.

Wenn die Empfehlung passt (oder eben nicht), kannst du sie mit 1-5 Sternen bewerten. Das Feedback fliesst beim nächsten Suchvorgang ins Modell ein.

## App starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Aufbau

- `app.py` – die Streamlit-App, alles was der User sieht
- `Feature_Database.py` – filtert Destinationen nach den harten Kriterien
- `Feature_Temperatur_API.py` – holt Temperaturdaten über Open-Meteo (mit Batch-Request)
- `Feature_API.py` – eine ältere Version der Wetter-API, die wir später zur Batch-Version weiterentwickelt haben
- `Feature_Tagespreise_API.py` – holt Preisdaten über Eurostat
- `Feature_KNN_ML.py` – das Machine-Learning-Modul
- `Feature_Feedback_ML.py` – speichert User-Bewertungen in einer JSON
- `Destinations_Database.csv` – unsere Datenbank mit allen Reisezielen

## Verwendete Tools

Wir haben Claude (Anthropic) verwendet, um die Beschreibungen oben in den Code-Dateien sprachlich zu vereinheitlichen, damit der Stil über alle Module hinweg konsistent ist. Die Logik und Struktur des Codes haben wir selbst geschrieben.

Beim Machine-Learning-Teil haben wir Claude zusätzlich als eine Art Coach genutzt: Auf Basis unserer Vorlesungs-Folien haben wir uns schrittweise Anleitungen erstellen lassen und diese als Leitfaden für unsere eigene Umsetzung verwendet.