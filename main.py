import requests
import tarfile
import io
import json
import hashlib
import smtplib
import os
import time
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path

# --- KONFIGURASJON ---
HISTORIKK_FIL = "siste_sjekk.json"
TIMEOUT_SEKUNDER = 60 

HEADERS = {
    "User-Agent": "LovRadar-Berekraft/3.2 (GitHub Action; +https://github.com/Majac999/lov-radar-berekraft)"
}

# KOMPLETT LISTE (Bærekraft, Bygg & Handel)
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

def send_epost(endringer):
    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")
    mottaker = avsender

    if not avsender or not passord:
        print("⚠️ Mangler e-post-informasjon. Kan ikke sende varsel.")
        return

    emne = f"Lov-radar: {len(endringer)} endring(er) oppdaget!"
    tekst = "Følgende endringer ble oppdaget i natt:\n\n"
    for navn in endringer:
        tekst += f"- {navn}\n"
    tekst += "\nSjekk Lovdata for detaljer: https://lovdata.no\n"
    tekst += "\nMvh\nDin Lov-radar"

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

def last_historikk():
    if Path(HISTORIKK_FIL).exists():
        with open(HISTORIKK_FIL, "r") as f:
            return json.load(f)
    return {}

def lagre_historikk(data):
    with open(HISTORIKK_FIL, "w") as f:
        json.dump(data, f, indent=2)

def beregn_hash(innhold):
    return hashlib.sha256(innhold).hexdigest()

def sjekk_lovdata():
    start_tid = time.time()
    print("🤖 Lovradar v3.2 (Final) starter...")
    
    # Sjekker om dette er aller første gang vi kjører (ingen historikk-fil)
    forste_gang = not Path(HISTORIKK_FIL).exists()
    
    forrige_sjekk = last_historikk()
    denne_sjekk = {}
    endringer_liste = []
    
    for kilde_navn, kilde_data in KILDER.items():
        print(f"\nSjekker {kilde_navn}...")
        url = kilde_data["url"]
        dokumenter = kilde_data["dokumenter"]
        
        try:
            # Fjernet stream=True for ryddigere kode, la til timeout
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEKUNDER)
            
            if response.status_code != 200:
                print(f"❌ Feil ved nedlasting av {kilde_navn}: {response.status_code}")
                continue
                
            fil_i_minnet = io.BytesIO(response.content)
            
            with tarfile.open(fileobj=fil_i_minnet, mode="r:bz2") as tar:
                for member in tar.getmembers():
                    for min_id, navn in dokumenter.items():
                        if min_id in member.name:
                            f = tar.extractfile(member)
                            if f:
                                innhold = f.read()
                                ny_hash = beregn_hash(innhold)
                                denne_sjekk[min_id] = ny_hash
                                
                                gammel_hash = forrige_sjekk.get(min_id)
                                
                                if gammel_hash and gammel_hash != ny_hash:
                                    print(f"🔔 ENDRET: {navn}")
                                    endringer_liste.append(navn)
                                elif gammel_hash is None:
                                    print(f"🆕 NY (Funnet): {navn}")
                                    
        except Exception as e:
            print(f"❌ En feil oppstod med {kilde_navn}: {e}")

    # Sikkerhet: Beholder data for lover vi kanskje ikke fant i dag
    for k, v in forrige_sjekk.items():
        if k not in denne_sjekk:
            denne_sjekk[k] = v

    lagre_historikk(denne_sjekk)

    tid_brukt = time.time() - start_tid
    print(f"\n⏱️ Ferdig på {tid_brukt:.2f} sekunder.")

    if endringer_liste:
        if forste_gang:
            print(f"ℹ️ Første kjøring: Fant {len(endringer_liste)} lover/forskrifter. Oppretter 'fasit' uten å sende e-post.")
        else:
            print(f"🚨 Fant {len(endringer_liste)} faktiske endringer. Sender e-post...")
            send_epost(endringer_liste)
    else:
        print("✅ Ingen endringer funnet.")

if __name__ == "__main__":
    sjekk_lovdata()
