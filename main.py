 
import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
import difflib

# --- KONFIGURASJON ---
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
        headers = {'User-Agent': 'Mozilla/5.0 (LovRadar Bot)'}
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'utf-8'
        return r.text
    except Exception as e:
        print(f"Feil: {e}")
        return ""

def sjekk_endringer():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    
    endringer = []
    print("🤖 LovRadar v5.5 (URL Edition) starter...")
    
    for navn, url in LOVER.items():
        print(f"Sjekker {navn}...")
        ny_tekst = hent_lovtekst(url)
        if not ny_tekst: continue
            
        filnavn = os.path.join(CACHE_DIR, f"{navn}.txt")
        gammel_tekst = ""
        
        if os.path.exists(filnavn):
            with open(filnavn, "r", encoding="utf-8") as f:
                gammel_tekst = f.read()
        
        # Lagre ALLTID ny tekst
        with open(filnavn, "w", encoding="utf-8") as f:
            f.write(ny_tekst)
            
        if not gammel_tekst: continue
            
        matcher = difflib.SequenceMatcher(None, gammel_tekst, ny_tekst)
        likhet = matcher.ratio()
        endring_prosent = (1 - likhet) * 100
        
        if endring_prosent > 2.0:
            endringer.append({"navn": navn, "prosent": endring_prosent, "url": url})
            
    return endringer

def send_epost(endringer):
    if not endringer:
        print("Ingen endringer funnet.")
        return

    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")
    
    if not avsender or not passord:
        print("Mangler e-post passord!")
        return

    endringer_sortert = sorted(endringer, key=lambda x: x['prosent'], reverse=True)
    antall = len(endringer)
    
    # Her bygger vi e-posten MED lenker
    tekst = "Følgende lovendringer er oppdaget (NÅ MED LENKER):\n\n"
    for item in endringer_sortert:
        tekst += f"🔴 {item['navn']} (Endring: {item['prosent']:.1f}%)\n"
        tekst += f"   Lenke: {item['url']}\n\n"
    
    tekst += "-"*30 + "\nTips: Kopier til din 'Lov-radar Bærekraft & Handel' Gem."

    msg = MIMEText(tekst, "plain", "utf-8")
    msg["Subject"] = Header(f"LovRadar: {antall} endringer m/lenker", "utf-8")
    msg["From"] = avsender
    msg["To"] = avsender

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(avsender, passord)
        server.send_message(msg)
        server.quit()
        print(f"📧 E-post sendt!")
    except Exception as e:
        print(f"Feil: {e}")

if __name__ == "__main__":
    funn = sjekk_endringer()
    send_epost(funn)
