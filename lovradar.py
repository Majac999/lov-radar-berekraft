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
    # ✅ RIKTIG URL (hoeringer):
    "Miljødirektoratet: Høringer og konsultasjoner": "https://www.miljodirektoratet.no/hoeringer/"
}

CACHE_FILE = "lovradar_baerekraft_cache.json"
THRESHOLD = float(os.environ.get("THRESHOLD", "1.0")) # Satt til 1% for å balansere nøyaktighet/støy
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
    session.headers.update({"User-Agent": USER_AGENT})
    return session

def get_company_context():
    return "Byggevarehandel (Obs Bygg/Coop). Fokus: Sirkulærøkonomi, kjemikalier, emballasje, åpenhetsloven og unngå grønnvasking."

def get_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def clean_html(html_content: str) -> str:
    if not html_content: return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        main_content = soup.find("main") or soup.find(id="content") or soup.find(id="main") or soup.find("article")
        if main_content: soup = main_content
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "meta", "button", "aside", "form"]):
            element.decompose() 
        text = soup.get_text(separator=" ")
        text = re.sub(r"", "", text, flags=re.DOTALL)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        print(f"⚠️ Feil i clean_html: {e}")
        return html_content 

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_cache():
    if not os.path.exists(CACHE_FILE): return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def unified_diff(old: str, new: str, context=3) -> str:
    old_words, new_words = old.split(" "), new.split(" ")
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    diff = []
    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        if opcode == 'equal':
            if a1 - a0 > context * 2:
                diff.append(" ".join(old_words[a0:a0+context]) + " ... [...] ... " + " ".join(old_words[a1-context:a1]))
            else: diff.append(" ".join(old_words[a0:a1]))
        elif opcode == 'insert': diff.append(f"🟢 [NYTT]: {' '.join(new_words[b0:b1])}")
        elif opcode == 'delete': diff.append(f"🔴 [SLETTET]: {' '.join(old_words[a0:a1])}")
        elif opcode == 'replace': diff.append(f"✏️ [ENDRET]: {' '.join(old_words[a0:a1])} -> {' '.join(new_words[b0:b1])}")
    return "\n".join(diff)[:5000]

# --- KJERNEFUNKSJONER ---

def sjekk_endringer():
    cache = load_cache()
    sess, funn = make_session(), []
    print(f"🔍 Starter sjekk av {len(LOVER)} kilder (Terskel: {THRESHOLD}%)...")

    for navn, url in LOVER.items():
        try:
            prev_entry = cache.get(navn, {})
            r = sess.get(url, headers={"If-None-Match": prev_entry.get("etag")} if prev_entry.get("etag") else {}, timeout=(10, 30))
            if r.status_code == 304:
                print(f" ✅ {navn}: Uendret (304)"); continue
            r.raise_for_status()
        except Exception as e:
            # ✅ SILENT FAIL: Logger feilen, men fortsetter kjøringen så de andre kildene fungerer
            print(f" ⚠️  ADVARSEL ved {navn}: {e}"); continue

        clean_text = clean_html(r.text)
        current_hash = sha256(clean_text)
        prev_hash, prev_text = prev_entry.get("hash"), prev_entry.get("text", "")

        cache[navn] = {"hash": current_hash, "text": clean_text, "url": url, "etag": r.headers.get("ETag"), "sist_sjekket": get_timestamp()}

        if not prev_hash:
            print(f" 🆕 {navn}: Lagret."); continue
        if current_hash == prev_hash:
            print(f" ✅ {navn}: Ingen tekstendring."); continue

        likhet = difflib.SequenceMatcher(None, prev_text, clean_text).ratio()
        endring_pct = (1 - likhet) * 100

        if endring_pct >= THRESHOLD:
            print(f" 🚨 ENDRING: {navn} ({endring_pct:.2f}%)")
            funn.append({"navn": navn, "url": url, "prosent": endring_pct, "diff": unified_diff(prev_text, clean_text)})
        else:
            print(f" ⚪ {navn}: Ubetydelig ({endring_pct:.2f}%)")

    save_cache(cache)
    return funn

def send_epost(funn):
    if not funn or not (EMAIL_USER and EMAIL_PASS):
        if funn: [print(f"\n--- {f['navn']} ---\n{f['diff']}") for f in funn]
        return
    
    linjer = [f"# 🌍 LovRadar: Bærekraftsvarsel\nOppdaget {len(funn)} endringer.\n"]
    for f in funn:
        linjer.extend([f"## 🔴 {f['navn']}", f"- Omfang: {f['prosent']:.2f}%", f"- Lenke: {f['url']}", "\n**Endring:**", "```diff", f['diff'], "```\n---"])
    
    msg = MIMEText("\n".join(linjer), "plain", "utf-8")
    msg["Subject"] = Header(f"🌍 Strategivarsel: {funn[0]['navn']}", "utf-8")
    msg["From"], msg["To"] = EMAIL_USER, EMAIL_TO

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print("✅ E-post sendt.")
    except Exception as e: print(f"❌ Feil ved sending: {e}")

if __name__ == "__main__":
    send_epost(sjekk_endringer())
