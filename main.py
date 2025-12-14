import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
import difflib

# --- KONFIGURASJON (ALLE LOVER MED URL) ---
LOVER = {
    "Kjøpsloven": "https://lovdata.no/lov/1988-05-13-27",
    "Forbrukerkjøpsloven": "https://lovdata.no/lov/2002-06-21-34",
    "Avhendingslova": "https://lovdata.no/lov/1992-07-03-93",
    "Markedsføringsloven": "https://lovdata.no/lov/2009-01-09-2",
    "Angrerettloven": "https://lovdata.no/lov/2014-06-20-27",
    "E-handelsloven": "https://lovdata.no/lov/2003-05-23-35",
    "Finansavtaleloven": "https://lovdata.no/lov/2020-12-18-146",
    "Åpenhetsloven": "https://lovdata.no/lov/2021-06-18-99",
    "Arbeidsmiljøloven": "https://lovdata.no/lov/2005-06-17-62",
    "Likestillings- og diskrimineringsloven": "https://lovdata.no/lov/2017-06-16-51",
    "Plan- og bygningsloven": "https://lovdata.no/lov/2008-06-27-71",
    "Forurensningsloven": "https://lovdata.no/lov/1981-03-13-6",
    "Naturmangfoldloven": "https://lovdata.no/lov/2009-06-19-100",
    "Produktkontrolloven": "https://lovdata.no/lov/1976-06-11-79",
    "Regnskapsloven": "https://lovdata.no/lov/1998-07-17-56",
    "Bokføringsloven": "https://lovdata.no/lov/2004-11-19-73",
    "Lov om bærekraftig finans": "https://lovdata.no/lov/2021-12-17-148"
}

CACHE_DIR = "tekst_cache"

def hent_lovtekst(url):
    try:
        headers = {"User-Agent": "LovRadar/CoopOst"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text
    except Exception as e:
        print(f"Feil ved henting av {url}: {e}")
        return ""

def sjekk_endringer():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    endringer = []
    print("🤖 LovRadar (v5.2) starter...")

    for navn, url in LOVER.items():
        print(f"Sjekker {navn} …")
        ny_tekst = hent_lovtekst(url)
        if not ny_tekst:
            continue

        filnavn = os.path.join(CACHE_DIR, f"{navn}.txt")
        gammel_tekst = ""

        if os.path.exists(filnavn):
            with open(filnavn, "r", encoding="utf-8") as f:
                gammel_tekst = f.read()

        # Lagre ny versjon
        with open(filnavn, "w", encoding="utf-8") as f:
            f.write(ny_tekst)

        if not gammel_tekst:
            continue

        matcher = difflib.SequenceMatcher(None, gammel_tekst, ny_tekst)
        endring_prosent = (1 - matcher.ratio()) * 100

        # Terskel på 2%
        if endring_prosent > 2.0:
            endringer.append({
                "navn": navn,
                "prosent": round(endring_prosent, 2),
                "url": url
            })

    return endringer

def send_epost(endringer):
    if not endringer:
        print("Ingen store endringer funnet.")
        return

    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")

    if not avsender or not passord:
        print("Mangler e-postoppsett!")
        return

    # Sorterer listen: Størst endring øverst
    endringer = sorted(endringer, key=lambda x: x["prosent"], reverse=True)

    tekst = "LovRadar – oppdagede endringer (MED LENKER):\n\n"
    for e in endringer:
        tekst += (
            f"🔴 {e['navn']} ({e['prosent']} % endring)\n"
            f"URL: {e['url']}\n\n"
        )
    
    tekst += "-"*30 + "\nTips: Lim inn i din Gem for analyse."

    msg = MIMEText(tekst, "plain", "utf-8")
    # Jeg endrer emnet her også, så du ser at det er NY kode:
    msg["Subject"] = Header("LovRadar: Nye endringer med lenker", "utf-8")
    msg["From"] = avsender
    msg["To"] = avsender

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(avsender, passord)
        server.send_message(msg)
        server.quit()
        print("📧 E-post sendt OK")
    except Exception as e:
        print(f"Feil ved sending: {e}")

if __name__ == "__main__":
    funn = sjekk_endringer()
    send_epost(funn)
