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
    # Hard Law
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Avfallsforskriften (Emballasje)": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 (Miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",

    # Soft Law / Veiledere
    "Forbrukertilsynet: Bærekraftveileder": "https://www.forbrukertilsynet.no/lov-og-rett/veiledninger-og-retningslinjer/forbrukertilsynets-veiledning-om-bruk-av-baerekraftpastander-markedsforing",
    "Miljødirektoratet: REACH": "https://www.miljodirektoratet.no/ansvarsomrader/kjemikalier/reach/",
    "DFØ: Miljøkrav anskaffelser": "https://www.anskaffelser.no/berekraftige-anskaffingar/klima-og-miljo-i-offentlige-anskaffelser",
    "Svanemerket: Høringer": "https://svanemerket.no/horinger/",

    # Fremtid / Strategi
    "Regjeringen: EØS-notater (Miljø)": "https://www.regjeringen.no/no/tema/europapolitikk/eos-notatbasen/id686653/?topic=klima-og-miljo",
    "Miljødirektoratet: Høringer": "https://www.miljodirektoratet.no/hoeringer/"
}

CACHE_FILE = "lovradar_baerekraft_cache.json"
THRESHOLD = float(os.environ.get("THRESHOLD", "2.0")) # Justert til 2% for mindre støy
USER_AGENT = "LovRadar-Complete/9.0 (Internal Compliance Tool; +https://github.com/Majac999)" 

# E-post
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_RECIPIENT", EMAIL_USER)

def make_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session

def clean_html(html_content: str) -> str:
    if not html_content: return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        main = soup.find("main") or soup.find(id="content") or soup.find(id="main") or soup.find("article")
        if main: soup = main
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "meta", "button", "aside", "form"]):
            element.decompose() 
        noisy = re.compile(r'(share|social|print|tool|toc|breadcrumb|menu|newsletter|cookie|popup|banner|filter)', re.I)
        for div in soup.find_all(class_=noisy): div.decompose()
        for div in soup.find_all(id=noisy): div.decompose()
        text = soup.get_text(separator=" ")
        text = re.sub(r"", "", text, flags=re.DOTALL)
        return re.sub(r"\s+", " ", text).strip()
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

def sjekk_endringer():
    cache = load_cache()
    sess, funn = make_session(), []
    print(f"🔍 Starter sjekk (Terskel: {THRESHOLD}%)...")

    for navn, url in LOVER.items():
        try:
            prev_entry = cache.get(navn, {})
            r = sess.get(url, headers={"If-None-Match": prev_entry.get("etag")} if prev_entry.get("etag") else {}, timeout=(10, 30))
            if r.status_code == 304:
                print(f" ✅ {navn}: Uendret (304)"); continue
            r.raise_for_status()
        except Exception as e:
            # Håndterer 404 og andre feil uten å krasje
            print(f" ⚠️  ADVARSEL ved {navn}: {e}"); continue

        clean_text = clean_html(r.text)
        current_hash = sha256(clean_text)
        prev_hash, prev_text = prev_entry.get("hash"), prev_entry.get("text", "")

        cache[navn] = {"hash": current_hash, "text": clean_text, "url": url, "etag": r.headers.get("ETag"), 
                       "sist_sjekket": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}

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
    
    linjer = [f"# 🌍 LovRadar: Strategisk Bærekraftsvarsel\nOppdaget {len(funn)} endringer for Obs Bygg/Coop.\n"]
    for f in funn:
        linjer.extend([f"## 🔴 {f['navn']}", f"- Omfang: {f['prosent']:.2f}%", f"- Lenke: {f['url']}", "\n```diff", f['diff'], "```\n---"])
    
    linjer.append("\n### 🤖 AI-ANALYSE: Fokus på Markedsføring (Grønnvasking), Innkjøp (REACH) og Strategi (EU/EØS).")
    
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
