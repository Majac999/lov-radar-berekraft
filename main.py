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
            "forskrift-2017-06-19-840": "TEK17 (Byggteknisk forskrift)",
            "forskrift-2013-12-17-1579": "DOK-forskriften (Byggevarer)",
            "forskrift-2010-03-26-488": "SAK10 (Byggesaksforskriften)",
            "forskrift-2008-05-30-516": "REACH-forskriften",
            "forskrift-2012-06-16-622": "CLP-forskriften",
            "forskrift-2004-06-01-930": "Avfallsforskriften",
            "forskrift-2004-06-01-922": "Produktforskriften",
        }
    },
    "lover": {
        "url": "https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2",
        "dokumenter": {
            "lov-2008-06-27-71": "Plan- og bygningsloven",
            "lov-2002-06-21-34": "Forbrukerkjopsloven",
            "lov-1988-05-13-27": "Kjopsloven",
            "lov-2009-01-09-2": "Markedsforingsloven",
            "lov-1976-06-11-79": "Produktkontrolloven",
            "lov-2021-06-18-99": "Apenhetsloven",
            "lov-2021-06-04-65": "Lov om barekraftig finans",
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

def filnavn_matcher(member_name, dok_id):
    """
    Matcher flere mulige filnavnformater:
    - Grok-format: lov-2008-06-27-71 eller forskrift-2017-06-19-840
    - Gammelt format: nl-20080627-071 eller sf-20170619-0840
    - Bare dato+nummer: 20080627-71 eller 20080627-071
    """
    name_lower = member_name.lower()
    id_lower = dok_id.lower()
    
    # Direkte match
    if id_lower in name_lower:
        return True
    
    # Konverter Grok-format til gammelt format
    # lov-2008-06-27-71 -> 20080627-071
    match = re.match(r"(lov|forskrift)-(\d{4})-(\d{2})-(\d{2})-(\d+)", id_lower)
    if match:
        dato = match.group(2) + match.group(3) + match.group(4)
        nummer = match.group(5).zfill(3)
        alternativ_id = f"{dato}-{nummer}"
        
        if alternativ_id in name_lower:
            return True
        
        # Prøv også nl- prefix for lover
        if match.group(1) == "lov":
            nl_id = f"nl-{alternativ_id}"
            if nl_id in name_lower:
                return True
        
        # Prøv sf- prefix for forskrifter
        if match.group(1) == "forskrift":
            sf_id = f"sf-{dato}-{nummer.zfill(4)}"
            if sf_id in name_lower:
                return True
    
    # Ekstraher bare tall og match
    bare_tall = re.sub(r"[^\d]", "", dok_id)
    if len(bare_tall) >= 10:
        if bare_tall in name_lower.replace("-", ""):
            return True
    
    return False

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
            
            # Debug: vis 5 første filnavn
            print("Eksempel-filer:")
            for f in alle[:5]:
                print(f"  {f}")

            for dok_id, dok_navn in dokumenter.items():
                funnet = False
                for member in tar.getmembers():
                    if filnavn_matcher(member.name, dok_id):
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
    print("Lovradar v2.0 starter...")
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
