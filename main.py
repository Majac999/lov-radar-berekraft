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
URL = "https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2"
HISTORIKK_FIL = "siste_sjekk.json"

# Legger til User-Agent så vi ikke blir blokkert
HEADERS = {
    "User-Agent": "LovRadar-Berekraft/1.0 (GitHub Action; +https://github.com/Majac999/lov-radar-berekraft)"
}

MINE_FORSKRIFTER = {
    "FOR-2008-05-30-516": "REACH-forskriften (Kjemikalier)",
    "FOR-2012-06-16-622": "CLP-forskriften (Merking)",
    "FOR-2004-06-01-930": "Avfallsforskriften",
    "FOR-2017-06-19-840": "TEK17 (Byggteknisk)",
    "FOR-2013-12-17-1579": "DOK-forskriften (Dokumentasjon)",
    "FOR-2004-06-01-922": "Produktforskriften"
}

def send_epost(endringer):
    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")
    mottaker = avsender

    if not avsender or not passord:
        print("⚠️ Mangler e-post-informasjon (Secrets). Kan ikke sende varsel.")
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
    print("🔍 Kobler til Lovdata...")
    # Bruker HEADERS for å identifisere oss
    response = requests.get(URL, headers=HEADERS, stream=True)
    
    if response.status_code != 200:
        print(f"❌ Feilkode fra Lovdata: {response.status_code}")
        return

    print("✅ Tilkobling vellykket! Laster ned data...")
    forrige_sjekk = last_historikk()
    denne_sjekk = {}
    endringer_liste = []
    
    fil_i_minnet = io.BytesIO(response.content)
    
    with tarfile.open(fileobj=fil_i_minnet, mode="r:bz2") as tar:
        for member in tar.getmembers():
            for min_id, navn in MINE_FORSKRIFTER.items():
                # Den viktige fiks: .lower() på begge sider
                if min_id.lower() in member.name.lower():
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
                            print(f"🆕 Første gang registrert: {navn}")

    lagre_historikk(denne_sjekk)

    if endringer_liste:
        print(f"🚨 Fant {len(endringer_liste)} endringer. Sender e-post...")
        send_epost(endringer_liste)
    elif not denne_sjekk:
        print("⚠️ ADVARSEL: Fant ingen av forskriftene i Lovdata-filen. Sjekk ID-er.")
    else:
        print("✅ Ingen endringer i natt.")

if __name__ == "__main__":
    sjekk_lovdata()
