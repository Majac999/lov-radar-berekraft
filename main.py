import requests
import tarfile
import io
import json
import hashlib
import smtplib
import os
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path

# --- KONFIGURASJON ---
HISTORIKK_FIL = "siste_sjekk.json"
HEADERS = {
    "User-Agent": "LovRadar-Berekraft/2.0 (GitHub Action; +https://github.com/Majac999/lov-radar-berekraft)"
}

# Din oppdaterte struktur (med korrigerte ID-er for lover)
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
            # Tilleggsanbefalinger for komplett radar:
            "20150501-0406": "Tømmerforskriften",
            "20170418-0480": "Biocidforskriften",
        }
    },
    "lover": {
        "url": "https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2",
        "dokumenter": {
            # Her har jeg fjernet "LOV-" og bindestreker for at den skal finne filene
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
    return hashlib.md5(innhold).hexdigest()

def sjekk_lovdata():
    print("🤖 Lovradar v3.0 starter...")
    forrige_sjekk = last_historikk()
    denne_sjekk = {}
    endringer_liste = []
    
    # Vi går nå gjennom BÅDE forskrifter og lover
    for kilde_navn, kilde_data in KILDER.items():
        print(f"\nSjekker {kilde_navn}...")
        url = kilde_data["url"]
        dokumenter = kilde_data["dokumenter"]
        
        try:
            response = requests.get(url, headers=HEADERS, stream=True)
            if response.status_code != 200:
                print(f"❌ Feil ved nedlasting av {kilde_navn}: {response.status_code}")
                continue
                
            fil_i_minnet = io.BytesIO(response.content)
            
            with tarfile.open(fileobj=fil_i_minnet, mode="r:bz2") as tar:
                for member in tar.getmembers():
                    for min_id, navn in dokumenter.items():
                        # Sjekker om ID-en finnes i filnavnet (f.eks. "20080627" i "nl-20080627...")
                        if min_id in member.name:
                            f = tar.extractfile(member)
                            if f:
                                innhold = f.read()
                                ny_hash = beregn_hash(innhold)
                                denne_sjekk[min_id] = ny_hash # Lagrer ny hash
                                
                                gammel_hash = forrige_sjekk.get(min_id)
                                
                                if gammel_hash and gammel_hash != ny_hash:
                                    print(f"🔔 ENDRET: {navn}")
                                    endringer_liste.append(navn)
                                elif gammel_hash is None:
                                    print(f"🆕 NY (Funnet): {navn}")
                                else:
                                    print(f"✅ OK: {navn}")
                                    
        except Exception as e:
            print(f"❌ En feil oppstod med {kilde_navn}: {e}")

    # Sjekk om vi har mistet noen (lå i gammel sjekk, men ikke funnet nå)
    # Dette beholder gamle hash-verdier for lover vi ikke sjekket i dag, for sikkerhets skyld
    for k, v in forrige_sjekk.items():
        if k not in denne_sjekk:
            denne_sjekk[k] = v

    lagre_historikk(denne_sjekk)

    if endringer_liste:
        print(f"\n🚨 Fant {len(endringer_liste)} endringer. Sender e-post...")
        send_epost(endringer_liste)
    else:
        print("\n✅ Ingen endringer funnet i noen lister.")

if __name__ == "__main__":
    sjekk_lovdata()
