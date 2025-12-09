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

HEADERS = {
    "User-Agent": "LovRadar-Berekraft/1.0 (GitHub Action)"
}

# Søkeord vi leter etter (vi finner riktig format)
MINE_FORSKRIFTER = {
    "2008-05-30-516": "REACH-forskriften (Kjemikalier)",
    "2012-06-16-622": "CLP-forskriften (Merking)",
    "2004-06-01-930": "Avfallsforskriften",
    "2017-06-19-840": "TEK17 (Byggteknisk)",
    "2013-12-17-1579": "DOK-forskriften (Dokumentasjon)",
    "2004-06-01-922": "Produktforskriften"
}

def send_epost(endringer):
    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")
    mottaker = avsender

    if not avsender or not passord:
        print("⚠️ Mangler e-post-informasjon. Kan ikke sende varsel.")
        return

    emne = f"Lov-radar: {len(endringer)} endring(er) oppdaget!"
    tekst = "Følgende endringer ble oppdaget:\n\n"
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
    
    try:
        response = requests.get(URL, headers=HEADERS, timeout=300)
    except Exception as e:
        print(f"❌ Nettverksfeil: {e}")
        return
    
    if response.status_code != 200:
        print(f"❌ Feilkode: {response.status_code}")
        return

    print(f"✅ Lastet ned {len(response.content) / 1024 / 1024:.1f} MB")
    
    forrige_sjekk = last_historikk()
    denne_sjekk = {}
    endringer_liste = []
    
    fil_i_minnet = io.BytesIO(response.content)
    
    with tarfile.open(fileobj=fil_i_minnet, mode="r:bz2") as tar:
        alle_filer = tar.getnames()
        print(f"📁 Totalt {len(alle_filer)} filer i pakken")
        
        # DEBUG: Vis 10 eksempler på filnavn
        print("\n📄 Eksempler på filnavn:")
        for navn in alle_filer[:10]:
            print(f"   {navn}")
        
        # DEBUG: Søk etter "forskrift" i filnavn for å se mønsteret
        print("\n🔎 Leter etter forskrifter som inneholder '2008-05-30':")
        for navn in alle_filer:
            if "2008-05-30" in navn:
                print(f"   TREFF: {navn}")
                break
        else:
            print("   Ingen treff på '2008-05-30'")
        
        # Nå søker vi etter våre forskrifter
        for member in tar.getmembers():
            filnavn = member.name.lower()
            
            for min_id, navn in MINE_FORSKRIFTER.items():
                if min_id in filnavn:
                    print(f"✅ Fant: {navn} -> {member.name}")
                    
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
                            print(f"🆕 Første gang: {navn}")
                        else:
                            print(f"   Uendret: {navn}")
                    break

    lagre_historikk(denne_sjekk)
    
    print(f"\n📊 Fant {len(denne_sjekk)} av {len(MINE_FORSKRIFTER)} forskrifter")

    if endringer_liste:
        print(f"🚨 {len(endringer_liste)} endringer! Sender e-post...")
        send_epost(endringer_liste)
    elif len(denne_sjekk) == 0:
        print("⚠️ ADVARSEL: Fant INGEN forskrifter! Sjekk filnavnene over.")
    else:
        print("✅ Ingen endringer siden sist.")

if __name__ == "__main__":
    sjekk_lovdata()
