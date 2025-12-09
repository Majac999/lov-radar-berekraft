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

HISTORIKK_FIL = "siste_sjekk.json"

HEADERS = {
    "User-Agent": "LovRadar-Berekraft/1.0 (GitHub Action)"
}

KILDER = {
    "forskrifter": {
        "url": "https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2",
        "dokumenter": {
            "20170619-0840": "TEK17 (Byggteknisk forskrift)",
            "20131217-1579": "DOK-forskriften (Byggevarer)",
            "20100326-0488": "SAK10 (Byggesaksforskriften)",
            "20080530-0516": "REACH-forskriften (Kjemikalier)",
            "20120616-0622": "CLP-forskriften (Merking)",
            "20040601-0930": "Avfallsforskriften",
            "20040601-0922": "Produktforskriften (Miljoefarlige stoffer)",
        }
    },
    "lover": {
        "url": "https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2",
        "dokumenter": {
            "lov-2008-06-27-71": "Plan- og bygningsloven",
            "lov-2002-06-21-34": "Forbrukerkjoepsloven",
            "lov-1988-05-13-27": "Kjoepsloven",
            "lov-2009-01-09-2": "Markedsforingsloven",
            "lov-1976-06-11-79": "Produktkontrolloven",
            "lov-2021-06-18-99": "Aapenhetsloven",
            "lov-2021-06-04-65": "Lov om baerekraftig finans",
            "lov-1998-07-17-56": "Regnskapsloven",
        }
    }
}

def send_epost(endringer):
    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")
    mottaker = avsender

    if not avsender or not passord:
        print("Mangler e-post-informasjon.")
        return

    emne = f"Lov-radar: {len(endringer)} endring(er) oppdaget!"
    tekst = "Foelgende lover/forskrifter ble endret:\n\n"
    for navn in endringer:
        tekst += f"- {navn}\n"
    tekst += "\nSjekk Lovdata: https://lovdata.no\n"
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
        print(f"E-post sendt til {mottaker}!")
    except Exception as e:
        print(f"Feil ved e-post: {e}")

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

def sjekk_kilde(navn, url, dokumenter, forrige_sjekk):
    print(f"\n==================================================")
    print(f"Laster ned {navn}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=600)
    except Exception as e:
        print(f"Nettverksfeil: {e}")
        return {}, []
    
    if response.status_code != 200:
        print(f"Feilkode {response.status_code}")
        return {}, []

    print(f"Lastet ned {len(response.content) / 1024 / 1024:.1f} MB")
    
    denne_sjekk = {}
    endringer_liste = []
    
    fil_i_minnet = io.BytesIO(response.content)
    
    try:
        with tarfile.open(fileobj=fil_i_minnet, mode="r:bz2") as tar:
            alle_filer = tar.getnames()
            print(f"{len(alle_filer)} filer i pakken")
            
            # DEBUG - skriv ut 5 eksempler
            print("Eksempler paa filnavn:")
            for i, fn in enumerate(alle_filer):
                if i < 5:
                    print(f"  {fn}")
            
            funnet_i_denne = 0
            for member in tar.getmembers():
                filnavn = member.name
                
                for dok_id, dok_navn in dokumenter.items():
                    if dok_id in filnavn:
                        f = tar.extractfile(member)
                        if f:
                            innhold = f.read()
                            ny_hash = beregn_hash(innhold)
                            
                            nokkel = f"{navn}:{dok_id}"
                            denne_sjekk[nokkel] = ny_hash
                            funnet_i_denne += 1
                            
                            gammel_hash = forrige_sjekk.get(nokkel)
                            
                            if gammel_hash and gammel_hash != ny_hash:
                                print(f"  ENDRET: {dok_navn}")
                                endringer_liste.append(dok_navn)
                            elif gammel_hash is None:
                                print(f"  Ny: {dok_navn}")
                            else:
                                print(f"  OK: {dok_navn}")
                        break
            
            print(f"Fant {funnet_i_denne} av {len(dokumenter)} i {navn}")
                        
    except Exception as e:
        print(f"Feil: {e}")
        return {}, []
    
    return denne_sjekk, endringer_liste

def sjekk_lovdata():
    print("Lov-radar Berekraft starter...")
    total_dok = sum(len(k['dokumenter']) for k in KILDER.values())
    print(f"Sjekker {total_dok} dokumenter")
    
    forrige_sjekk = last_historikk()
    samlet_sjekk = {}
    alle_endringer = []
    total_funnet = 0
    total_forventet = 0
    
    for kilde_navn, kilde_info in KILDER.items():
        total_forventet += len(kilde_info["dokumenter"])
        
        denne_sjekk, endringer = sjekk_kilde(
            kilde_navn,
            kilde_info["url"],
            kilde_info["dokumenter"],
            forrige_sjekk
        )
        
        samlet_sjekk.update(denne_sjekk)
        alle_endringer.extend(endringer)
        total_funnet += len(denne_sjekk)

    lagre_historikk(samlet_sjekk)
    
    print(f"\n==================================================")
    print(f"RESULTAT: Fant {total_funnet} av {total_forventet} dokumenter")

    if alle_endringer:
        print(f"{len(alle_endringer)} ENDRINGER!")
        for e in alle_endringer:
            print(f"  -> {e}")
        send_epost(alle_endringer)
    elif total_funnet == 0:
        print("ADVARSEL: Fant ingen!")
    else:
        print("Ingen endringer siden sist.")

if __name__ == "__main__":
    sjekk_lovdata()
