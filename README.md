# Lov-radar Bærekraft & Handel 🌍⚖️

> Et Open Source-verktøy for overvåking av regelverk knyttet til miljø, byggevarer og handel.

## 🔨 Om prosjektet
Dette er et privat utviklingsprosjekt for å forenkle hverdagen til ansatte i byggevarebransjen. Målet er å fange opp endringer i et bredt spekter av lover og forskrifter raskere, for å sikre compliance, trygge produkter og korrekte kundesvar.

**Status:** 🟢 Live (V3.2 - Automatisert daglig sjekk)

## 🎯 Hva overvåker verktøyet?
Systemet gjør automatiske oppslag mot Lovdata hver morgen kl. 06:00 for å sjekke endringer innen fire hovedkategorier:

### 1. Miljø, Kjemikalier & Bærekraft
* **REACH-forskriften** (Kjemikalier og stoffer)
* **CLP-forskriften** (Klassifisering og merking)
* **Avfallsforskriften** (Håndtering og sortering)
* **Biocidforskriften** (Impregnering og skadedyr)
* **Lov om bærekraftig finans** (Taksonomi)

### 2. Bygg og Produktkrav
* **DOK-forskriften** (Dokumentasjon av byggevarer)
* **TEK17** (Byggteknisk forskrift)
* **Produktkontrolloven**
* **Tømmerforskriften** (Sporbarhet og import)
* **FEU** (Elektrisk utstyr)
* **Internkontrollforskriften** (HMS og rutiner)

### 3. Handel og Forbruker
* **Forbrukerkjøpsloven** (Reklamasjon og rettigheter)
* **Kjøpsloven** (Næringskjøp)
* **Markedsføringsloven** (Miljøpåstander/grønnvasking)
* **Åpenhetsloven** (Leverandørkjeder og menneskerettigheter)
* **Angrerettloven**

Når en endring oppdages i noen av disse, sender systemet et varsel på e-post med lenke til Lovdata.

## 🛠️ Teknisk
* **Språk:** Python 3.9
* **Kilde:** Lovdata (Åpne Data)
* **Automatisering:** GitHub Actions (Cron schedule)
* **Personvern:** Ingen data lagres eller brukes til trening av språkmodeller. Kun direkte oppslag.

## 📜 Lisens
Dette prosjektet er lisensiert under MIT-lisensen. Du står fritt til å bruke, kopiere og endre koden.
