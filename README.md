# Lov-radar Bærekraft & Handel 🌍⚖️

Et Open Source-verktøy for overvåking av regelverk knyttet til miljø, byggevarer og handel.

## 🔨 Om prosjektet
Dette er et privat utviklingsprosjekt for å forenkle hverdagen til ansatte i byggevarebransjen. Målet er å fange opp endringer i et bredt spekter av lover og forskrifter raskere, for å sikre compliance, trygge produkter og korrekte kundesvar.

**Status:** Under utvikling (Prototype-fase)

## 🎯 Hva overvåker verktøyet?
Systemet gjør periodiske oppslag mot Lovdata for å sjekke endringsdato på regelverk innen tre hovedkategorier:

### 1. Miljø og Kjemikalier (Bærekraft)
* **REACH-forskriften** (Kjemikalier og stoffer)
* **CLP-forskriften** (Klassifisering og merking)
* **Avfallsforskriften** (Håndtering og sortering)
* **Emballasjeforskriften**

### 2. Bygg og Produktkrav
* **DOK-forskriften** (Dokumentasjon av byggevarer)
* **Byggteknisk forskrift (TEK17/TEK20)**
* **Produktkontrolloven**

### 3. Handel og Forbruker (Butikkdrift)
* **Forbrukerkjøpsloven** (Reklamasjon og rettigheter)
* **Markedsføringsloven** (Med fokus på miljøpåstander/grønnvasking)
* **Angrerettloven**

Når en endring oppdages i noen av disse, sender systemet et varsel på e-post med lenke til endringen.

## 🛠️ Teknisk
* **Språk:** Python
* **Kilde:** Lovdata API (Åpne data)
* **Lisens:** MIT (Open Source)
* **AI:** Ingen data lagres eller brukes til trening av språkmodeller. Kun oppslag.

## 📜 Lisens
Dette prosjektet er lisensiert under MIT-lisensen. Se `LICENSE` for detaljer.
