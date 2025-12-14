# Lov-radar Bærekraft & Handel 🌍⚖️

Et Open Source-verktøy for overvåking av regelverk knyttet til miljø, byggevarer og handel.

## 🔨 Om prosjektet
Dette er et privat utviklingsprosjekt for å forenkle hverdagen til ansatte i byggevarebransjen. Målet er å fange opp endringer i et bredt spekter av lover og forskrifter raskere, for å sikre compliance, trygge produkter og korrekte kundesvar.

Status: 🟢 Live (V5.6 - Med Lenker og Fikset Cache)

## 🎯 Hva overvåker verktøyet?
Systemet gjør automatiske oppslag mot Lovdata **hver mandag morgen kl. 06:00**.

Det sjekker om det har skjedd **vesentlige endringer** i lovteksten (ignorerer formatering, datoer og småfeil) innen fire hovedkategorier:

### 1. Miljø, Kjemikalier & Bærekraft
* REACH-forskriften (Kjemikalier og stoffer)
* CLP-forskriften (Klassifisering og merking)
* Avfallsforskriften (Håndtering og sortering)
* Biocidforskriften (Impregnering og skadedyr)
* Lov om bærekraftig finans (Taksonomi)

### 2. Bygg og Produktkrav
* DOK-forskriften (Dokumentasjon av byggevarer)
* TEK17 (Byggteknisk forskrift)
* Produktkontrolloven
* Tømmerforskriften (Sporbarhet og import)
* FEU (Elektrisk utstyr)
* Internkontrollforskriften (HMS og rutiner)

### 3. Handel og Forbruker
* Forbrukerkjøpsloven (Reklamasjon og rettigheter)
* Kjøpsloven (Næringskjøp)
* Markedsføringsloven (Miljøpåstander/grønnvasking)
* Åpenhetsloven (Leverandørkjeder og menneskerettigheter)
* Regnskapsloven (Bærekraftsrapportering/CSRD)

---

## 🤖 Hvordan det virker (V4.0)
Når radaren kjører på mandager:
1. **Laster ned** siste versjon av alle lover fra Lovdata.
2. **Vasker teksten:** Fjerner "støy" som HTML-koder, datoer for sist endret, og formatering.
3. **Sammenligner:** Sjekker den vaskede teksten
