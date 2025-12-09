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

# ---------------------------------------------------------
# KONFIG
# ---------------------------------------------------------

HISTORIKK_FIL = "siste_sjekk.json"

HEADERS = {
    "User-Agent": "LovRadar-Berekraft/1.0 (GitHub Action)"
}

# Kilder og dokumenter du ønsker å følge
# Dette er uendret – ID-ene her brukes som "søkestrenger"
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
            "nl-20020621-034": "Forbrukerkjøpsloven",
            "nl-19880513-027": "Kjøpsloven",
            "nl-20090109-002": "Markedsføringsloven",
            "nl-19760611-079": "Produktkontrolloven",
            "nl-20210618-099": "Åpenhetsloven",
            "nl-20210604-065": "Lov om bærekraftig finans",
            "nl-19980717-056": "Regnskapsloven",
        }
    }
}


# ---------------------------------------------------------
# EPOST
# ---------------------------------------------------------

def send_epost(endringer):
    avsender = os.environ.get("EMAIL_USER")
    passord = os.environ.get("EMAIL_PASS")
    mottaker = avsender

    if not avsender or not passord:
        print("⚠️ Mangler e-post-informasjon i secrets.")
        return

    emne = f"Lovradar: {len(endringer)} endringer oppdaget!"
    tekst = "Følgende lover/forskrifter ble endret:\n\n"
    for navn in endringer:
        tekst += f"- {navn}\n"
    tekst += "\nSjekk endringene på Lovdata.no\n\nMvh\nLovradar"

    msg = MIMEText(tekst, "plain", "utf-8")
    msg["Subject"] = Header(emne, "utf-8")
    msg["From"] = avsender
    msg["To"] = mottaker

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(avsender, passord)
        server.send_message(msg)
        server.quit()
        print(f"📬 E-post sendt til {mottaker}")
    except Exception as e:
        print(f"❌ Klarte ikke sende e-post: {e}")


# ---------------------------------------------------------
# HISTORIKK
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# ROBUST FILMATCHING – viktig forbedring
# ---------------------------------------------------------

def filnavn_matcher(member_name, dok_id):
    """
    Lovdata har ofte inkonsekvent navngiving:
    - noen ganger inkluderer full ID
    - noen ganger bare dato
    - noen ganger ekstra suffiks
    """

    # eksakt substring (best case)
    if dok_id.lower() in member_name.lower():
        return True

    # match dato-delen som 8 tall
    m = re.search(r"(\d{8})", dok_id)
    if m and m.group(1) in member_name:
        return True

    # match ID uten prefiks (nl-, f-, k- osv.)
    stripped = dok_id.split("-", 1)[-1]
    if stripped in member_name:
        return True

    return False


# ---------------------------------------------------------
# HOVED SJEKK
# ---------------------------------------------------------

def sjekk_kilde(navn, url, dokumenter, forrige_sjekk):
    print(f"\n===============================================")
    print(f"📥 Laster ned {navn}...")

    try:
        response = requests.get(url, headers=HEADERS, timeout=600)
    except Exception as e:
        print(f"❌ Nettverksfeil: {e}")
        return {}, []

    if response.status_code != 200:
        print(f"❌ Feilkode {response.status_code}")
        return {}, []

    print(f"✔️ Lastet ned {(len(response.content) / 1024 / 1024):.1f} MB")

    fil_i_minnet = io.BytesIO(response.content)
    denne_sjekk = {}
    endringer_liste = []

    try:
        with tarfile.open(fileobj=fil_i_minnet, mode="r:bz2") as tar:
            alle_filer = tar.getnames()
            print(f"📦 Arkivet inneholder {len(alle_filer)} filer")

            for dok_id, dok_navn in dokumenter.items():
                fant_fil = False

                for member in tar.getmembers():
                    if filnavn_matcher(member.name, dok_id):
                        fant_fil = True
                        f = tar.extractfile(member)
                        if not f:
                            continue

                        innhold = f.read()
                        ny_hash = beregn_hash(innhold)

                        nokkel = f"{navn}:{dok_id}"
                        denne_sjekk[nokkel] = ny_hash

                        gammel_hash = forrige_sjekk.get(nokkel)

                        if gammel_hash and gammel_hash != ny_hash:
                            print(f"🟡 ENDRET: {dok_navn}")
                            endringer_liste.append(dok_navn)
                        elif gammel_hash is None:
                            print(f"🆕 Ny fil: {dok_navn}")
                        else:
                            print(f"🟢 Uendret: {dok_navn}")

                        break

                if not fant_fil:
                    print(f"❓ Fant ikke fil for: {dok_navn} ({dok_id})")

    except Exception as e:
        print(f"❌ Feil ved lesing av arkiv: {e}")
        return {}, []

    return denne_sjekk, endringer_liste


# ---------------------------------------------------------
# RUNNER
# ---------------------------------------------------------

def sjekk_lovdata():
    print("🚀 Lovradar starter...")
    total_dok = sum(len(k["dokumenter"]) for k in KILDER.values())
    print(f"📚 Sjekker totalt {total_dok} dokumenter")

    forrige_sjekk = last_historikk()
    samlet_sjekk = {}
    alle_endringer = []

    for kilde_navn, kilde_info in KILDER.items():
        denne_sjekk, endringer = sjekk_kilde(
            kilde_navn,
            kilde_info["url"],
            kilde_info["dokumenter"],
            forrige_sjekk
        )
        samlet_sjekk.update(denne_sjekk)
        alle_endringer.extend(endringer)

    lagre_historikk(samlet_sjekk)

    print("\n===============================================")
    print(f"🔎 RESULTAT: {len(samlet_sjekk)} dokumenter funnet")

    if alle_endringer:
        print(f"⚠️ {len(alle_endringer)} ENDRINGER FUNNET!")
        for e in alle_endringer:
            print(f" - {e}")
        send_epost(alle_endringer)
    else:
        print("✔️ Ingen endringer siden sist.")


if __name__ == "__main__":
    sjekk_lovdata()
