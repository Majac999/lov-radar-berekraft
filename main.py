import requests
import tarfile
import io
import json
import smtplib
import os
import time
import re
import difflib
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path

# --- KONFIGURASJON ---
CACHE_MAPPE = "tekst_cache"   
TERSKEL_LIKHET = 0.995        # 99.5% likhet = ignoreres (Tillater litt mer støy)
TIMEOUT_SEKUNDER = 60 

HEADERS = {
    "User-Agent": "LovRadar-Berekraft/4.1-Fix (GitHub Action; +https://github.com/Majac999/lov-radar-berekraft)"
}

# KOMPLETT LISTE 
KILDER = {
    "forskrifter": {
        "url": "https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2",
        "dokumenter": {
            "20170619-0840": "TEK17 (Byggteknisk forskrift)",
            "20131217-1579": "DOK-forskriften (Byggevarer)",
            "20100326-0488": "SAK10 (Byggesaksforskriften)",
            "20080530-0516": "REACH-forskriften",
            "20120616-0622": "CLP-forskriften",
            "20040601-0930": "Avfallsforskriften",
            "20040601-0922": "Produktforskriften",
            "20150501-0406": "Tømmerforskriften",
            "20170418-0480": "Biocidforskriften",
            "20171010-1598": "FEU (Elektrisk utstyr)",
            "19961206-1127": "Internkontrollforskriften",
        }
    },
    "lover": {
        "url": "https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2",
        "dokumenter": {
            "20080627": "Plan- og bygningsloven",
            "20020621": "Forbrukerkjøpsloven",
            "19880513": "Kjøpsloven",
            "20090109": "Markedsføringsloven",
            "19760611": "Produktkontrolloven",
            "20210618": "Åpenhetsloven",
            "20211222": "Lov om bærekraftig finans",
            "19980717": "Regnskapsloven",
        }
    }
}

def rens_tekst(radata_bytes):
    try:
        tekst = radata_bytes.decode('utf-8', errors='ignore')
        tekst = re.sub(r'<[^>]+>', ' ', tekst) 
        tekst = re.sub(r'Sist endret.*', '', tekst, flags=re.IGNORECASE)
        tekst = re.sub(r'Dato.*', '', tekst, flags=re.IGNORECASE)
        tekst = re.sub(r'\s+', ' ', tekst) 
        return tekst.strip()
    except Exception:
        return str(radata_bytes)

def er_vesentlig_endring(filnavn, ny_tekst):
    filsti = Path(CACHE_MAPPE) / f"{filnavn}.txt"
    
    if not filsti.exists():
        return True, 0.0 

    with open(filsti, "r", encoding="utf-8") as f:
        gammel_tekst = f.read()

    matcher = difflib.SequenceMatcher(None, gammel_tekst, ny_tekst)
    likhet = matcher.ratio()

    if likhet < TERSKEL_LIKHET:
        endring_prosent = (1 - likhet) * 100
        return True, endring_prosent
    
    return False, 0.0

def lagre_til_cache(filnavn, tekst):
    if not os.path.exists(CACHE_MAPPE):
        os.makedirs(CACHE_MAPPE)
    
    filsti = Path(CACHE_MAPPE) / f"{filnavn}.txt"
    with open(filsti, "w", encoding="utf-8") as f:
        f.write(tekst)

def send_epost(endringer):
    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")
    mottaker = avsender

    if not avsender or not passord:
        print("⚠️ Mangler e-post-informasjon.")
        return

    emne = f"Lov-radar: {len(endringer)} VESENTLIGE endringer!"
    tekst = "Følgende endringer er over terskelverdien (filtrert for småfeil):\n\n"
    for navn, endring_p in endringer:
        tekst += f"- {navn} (Endring: {endring_p:.2f}%)\n"
    
    tekst += "\nTips: Kopier teksten fra Lovdata og spør din AI-bot om hva endringen betyr."
    tekst += "\nSjekk Lovdata: https://lovdata.no\n"

    msg = MIMEText(tekst, 'plain', 'utf-8')
    msg['Subject'] = Header(emne, 'utf-8')
    msg['From'] = avsender
    msg['To'] = mottaker

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(avsender, passord)
        server.send_message(msg)
        server.quit()
        print(f"📧 E-post sendt til {mottaker}!")
    except Exception as e:
        print(f"❌ Feil ved sending av e-post: {e}")

def sjekk_lovdata():
    start_tid = time.time()
    print(f"🤖 Lovradar v4.1 (Anti-Spam) starter...")
    
    if not os.path.exists(CACHE_MAPPE):
        os.makedirs(CACHE_MAPPE)

    vesentlige_endringer = []
    
    for kilde_navn, kilde_data in KILDER.items():
        print(f"\nSjekker {kilde_navn}...")
        
        # NYTT: Holder styr på hvilke lover vi allerede har sjekket i denne runden
        behandlede_ider = set() 
        
        try:
            response = requests.get(kilde_data["url"], headers=HEADERS, timeout=TIMEOUT_SEKUNDER)
            if response.status_code != 200:
                print(f"❌ HTTP {response.status_code}")
                continue
                
            fil_i_minnet = io.BytesIO(response.content)
            with tarfile.open(fileobj=fil_i_minnet, mode="r:bz2") as tar:
                for member in tar.getmembers():
                    for min_id, navn in kilde_data["dokumenter"].items():
                        
                        # SJEKK: Har vi allerede behandlet denne loven i dag?
                        if min_id in behandlede_ider:
                            continue # Hopp over dubletter!

                        if min_id in member.name:
                            f = tar.extractfile(member)
                            if f:
                                ra_data = f.read()
                                ny_tekst = rens_tekst(ra_data)
                                
                                endret, endring_p = er_vesentlig_endring(min_id, ny_tekst)
                                
                                if endret:
                                    if endring_p == 0.0:
                                        print(f"🆕 Første: {navn}")
                                    else:
                                        print(f"🚨 ENDRING ({endring_p:.2f}%): {navn}")
                                        vesentlige_endringer.append((navn, endring_p))
                                    
                                    # Oppdater cache
                                    lagre_til_cache(min_id, ny_tekst)
                                
                                # Marker at vi er ferdige med denne loven for i dag
                                behandlede_ider.add(min_id)
                                    
        except Exception as e:
            print(f"❌ Feil med {kilde_navn}: {e}")

    tid_brukt = time.time() - start_tid
    print(f"\n⏱️ Ferdig på {tid_brukt:.2f} sekunder.")

    reelle_endringer = [x for x in vesentlige_endringer if x[1] > 0.0]
    
    if reelle_endringer:
        send_epost(reelle_endringer)
    else:
        print("✅ Ingen vesentlige endringer.")

if __name__ == "__main__":
    sjekk_lovdata()
