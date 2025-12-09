import requests
import tarfile
import io
import json
import hashlib
import smtplib
import os
import re
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path

HISTORIKK_FIL = "siste_sjekk.json"

HEADERS = {
    "User-Agent": "LovRadar-Berekraft/2.0"
}

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
        }
    },
    "lover": {
        "url": "https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2",
        "dokumenter": {
            "nl-20080627-071": "Plan- og bygningsloven",
            "nl-20020621-034": "Forbrukerkjopsloven",
            "nl-19880513-027": "Kjopsloven",
            "nl-20090109-002": "Markedsforingsloven",
            "nl-19760611-079": "Produktkontrolloven",
            "nl-20210618-099": "Apenhetsloven",
            "nl-20210604-065": "Lov om barekraftig finans",
            "nl-19980717-056": "Regnskapsloven",
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

    emne = f"Lovradar: {len(endringer)} endring(er)!"
    tekst = "Endrede dokumenter:\n\n"
    for navn in endringer:
        tekst += f"- {navn}\n"
    tekst += "\nhttps://lovdata.no\n\n- Lovradar"

    msg = MIMEText(tekst, "plain", "utf-8")
    msg["Subject"] = Header(emne, "utf-8")
    msg["From"] = avsender
    msg["To"] = mottaker

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(avsender, passord)
        server.send_message(msg)
        server.quit()
        print(f"E-post sendt til {mottaker}")
    except Exception as e:
        print(f"E-post feilet: {e}")

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
    print(f"\nLaster ned {navn}...")
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=600)
    except Exception as e:
        print(f"Nettverksfeil: {e}")
        return {}, []

    if r.status_code != 200:
        print(f"Feilkode {r.status_code}")
        return {}, []

    print(f"Lastet ned {len(r.content)/1024/1024:.1f} MB")

    denne_sjekk = {}
    endringer = []

    try:
        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:bz2") as tar:
            alle = tar.getnames()
            print(f"{len(alle)} filer i pakken")

            for dok_id, dok_navn in dokumenter.items():
                funnet = False
                for member in tar.getmembers():
                    if dok_id in member.name:
                        f = tar.extractfile(member)
                        if not f:
                            continue
                        
                        innhold = f.read()
                        ny_hash = beregn_hash(innhold)
                        nokkel = f"{navn}:{dok_id}"
                        denne_sjekk[nokkel] = ny_hash

                        gammel = forrige_sjekk.get(nokkel)
                        if gammel and gammel != ny_hash:
                            print(f"ENDRET: {dok_navn}")
                            endringer.append(dok_navn)
                        elif not gammel:
                            print(f"NY: {dok_navn}")
                        else:
                            print(f"OK: {dok_navn}")
                        
                        funnet = True
                        break

                if not funnet:
                    print(f"IKKE FUNNET: {dok_navn} ({dok_id})")

    except Exception as e:
        print(f"Feil: {e}")
        return {}, []

    return denne_sjekk, endringer

def sjekk_lovdata():
    print("Lovradar starter...")
    total = sum(len(v["dokumenter"]) for v in KILDER.values())
    print(f"Sjekker {total} dokumenter")

    forrige = last_historikk()
    ny_historikk = {}
    alle_endringer = []

    for kilde, info in KILDER.items():
        ny, endringer = sjekk_kilde(kilde, info["url"], info["dokumenter"], forrige)
        ny_historikk.update(ny)
        alle_endringer.extend(endringer)

    lagre_historikk(ny_historikk)

    print("\n" + "="*50)
    print(f"RESULTAT: Fant {len(ny_historikk)} av {total} dokumenter")
    
    if alle_endringer:
        print(f"{len(alle_endringer)} ENDRINGER!")
        send_epost(alle_endringer)
    else:
        print("Ingen endringer.")

if __name__ == "__main__":
    sjekk_lovdata()
