import os
import json
import hashlib
import smtplib
import requests
import difflib
import re
import datetime
from email.mime.text import MIMEText
from email.header import Header
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# --- DEN KOMPLETTE RADAREN (Compliance + Strategi) ---
LOVER = {
    # === 1. HARD LAW (Må følges i dag) ===
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Avfallsforskriften (Kap 6-7 Emballasje)": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    "Åpenhetsloven (Leverandørkjeder)": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Markedsføringsloven (Grønnvasking)": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 (Kap 9 Ytre miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",

    # === 2. SOFT LAW (Tolkning & Markedsføring) ===
    "Forbrukertilsynet: Bærekraftveileder": "https://www.forbrukertilsynet.no/lov-og-rett/veiledninger-og-retningslinjer/forbrukertilsynets-veiledning-om-bruk-av-baerekraftpastander-markedsforing",
    "Miljødirektoratet: Kjemikalienyheter": "https://www.miljodirektoratet.no/ansvarsomrader/kjemikalier/reach/",
    "DFØ: Miljøkrav i offentlige innkjøp": "https://www.anskaffelser.no/berekraftige-anskaffingar/klima-og-miljo-i-offentlige-anskaffelser",
    "Svanemerket: Nye krav (Høringer)": "https://svanemerket.no/horinger/",

    # === 3. FREMTID & STRATEGI (EØS/EU) ===
    "Regjeringen: EØS-notater (Klima/Miljø)": "https://www.regjeringen.no/no/tema/europapolitikk/eos-notatbasen/id686653/?topic=klima-og-miljo",
    "Miljødirektoratet: Høringer og konsultasjoner": "https://www.miljodirektoratet.no/hoeringer/"
}

CACHE_FILE = "lovradar_baerekraft_cache.json"
THRESHOLD = float(os.environ.get("THRESHOLD", "1.0"))  # Endringsterskel i prosent
USER_AGENT = "LovRadar-Complete/9.0 (Internal Compliance Tool; +https://github.com/Majac999)"

# E-post innstillinger
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_RECIPIENT", EMAIL_USER)

# --- HJELPEFUNKSJONER ---

def make_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    return session

def get_company_context():
    return (
        "Bransje: Byggevarehandel (Obs Bygg / Coop)\n"
        "Fokus: Sirkulærøkonomi, kjemikalier (REACH/produktkontroll), emballasje, "
        "åpenhetsloven (leverandørkjeder) og unngå grønnvasking."
    )

def get_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def clean_html(html_content: str) -> str:
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        main_content = (
            soup.find("main")
            or soup.find(id="content")
            or soup.find(id="main")
            or soup.find("article")
            or soup
        )
        soup = main_content
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "meta", "button", "aside", "form"]):
            element.decompose()
        text = soup.get_text(separator="\n")
        # FJERNET den farlige regex-linjen
        text = re.sub(r"\n\s*\n+", "\n\n", text)  # komprimer tomme linjer
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()
    except Exception as e:
        print(f"⚠️ Feil i clean_html: {e}")
        return html_content

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def unified_diff_lines(old: str, new: str, context: int = 5, max_chars: int = 8000) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    diff = difflib.unified_diff(old_lines, new_lines, lineterm="", n=context, fromfile="forrige", tofile="ny")
    out = "\n".join(diff)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n... [diff trunkert]"
    return out

# --- KJERNEFUNKSJONER ---

def sjekk_endringer():
    cache = load_cache()
    sess = make_session()
    funn = []

    print(f"🔍 Starter sjekk av {len(LOVER)} kilder (terskel: {THRESHOLD:.2f}%)...")

    for navn, url in LOVER.items():
        try:
            prev_entry = cache.get(navn, {})
            headers = {"If-None-Match": prev_entry.get("etag")} if prev_entry.get("etag") else {}
            r = sess.get(url, headers=headers, timeout=(10, 30))
            if r.status_code == 304:
                print(f" ✅ {navn}: Uendret (304)")
                continue
            r.raise_for_status()
        except Exception as e:
            print(f" ⚠️ ADVARSEL ved {navn}: {e}")
            continue

        clean_text = clean_html(r.text)
        current_hash = sha256(clean_text)
        prev_hash = prev_entry.get("hash")
        prev_text = prev_entry.get("text", "")

        cache[navn] = {
            "hash": current_hash,
            "text": clean_text,
            "url": url,
            "etag": r.headers.get("ETag"),
            "sist_sjekket": get_timestamp(),
        }

        if not prev_hash:
            print(f" 🆕 {navn}: Lagret første gang.")
            continue
        if current_hash == prev_hash:
            print(f" ✅ {navn}: Ingen tekstendring (hash lik).")
            continue

        likhet = difflib.SequenceMatcher(None, prev_text, clean_text).ratio()
        endring_pct = (1 - likhet) * 100

        if endring_pct >= THRESHOLD:
            print(f" 🚨 ENDRING: {navn} ({endring_pct:.2f}%)")
            diff_txt = unified_diff_lines(prev_text, clean_text)
            funn.append({"navn": navn, "url": url, "prosent": endring_pct, "diff": diff_txt})
        else:
            print(f" ⚪ {navn}: Ubetydelig ({endring_pct:.2f}%)")

    save_cache(cache)
    return funn

def send_epost(funn):
    if not funn:
        print("Ingen relevante endringer.")
        return

    company_ctx = get_company_context()
    linjer = [
        "# 🌍 LovRadar: Bærekraftsvarsel",
        f"Tidspunkt: {get_timestamp()}",
        f"Endringer oppdaget: {len(funn)}",
        f"Terskel: {THRESHOLD:.2f} %",
        "",
        "## Bedriftskontekst",
        company_ctx,
        "",
    ]

    for f in funn:
        linjer.extend([
            f"## 🔴 {f['navn']}",
            f"- Omfang: {f['prosent']:.2f} %",
            f"- Lenke: {f['url']}",
            "",
            "**Endring (unified diff, linjenivå):**",
            "```diff",
            f["diff"],
            "```",
            "---",
            "",
        ])

    body = "\n".join(linjer)

    if not (EMAIL_USER and EMAIL_PASS):
        # Fallback: skriv til stdout om e-post ikke er satt opp
        print(body)
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(f"🌍 Strategivarsel: {funn[0]['navn']}", "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print("✅ E-post sendt.")
    except Exception as e:
        print(f"❌ Feil ved sending: {e}")
        print("Sender til stdout som fallback:\n")
        print(body)

if __name__ == "__main__":
    funn = sjekk_endringer()
    send_epost(funn)
