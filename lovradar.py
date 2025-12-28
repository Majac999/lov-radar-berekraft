import os, json, hashlib, smtplib, requests, difflib, re, datetime, time
from email.mime.text import MIMEText
from email.header import Header
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# --- DIN STRATEGISKE KILDELISTE ---
LOVER = {
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Avfallsforskriften (Emballasje)": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 (Ytre miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",
    "Svanemerket: Høringer": "https://svanemerket.no/horinger/",
    "Miljødirektoratet: Høringer": "https://www.miljodirektoratet.no/hoeringer/"
}

CACHE_FILE = "lovradar_baerekraft_cache.json"
THRESHOLD = 0.8  # Justert for å fange viktige endringer, men ignorere småplukk
USER_AGENT = "LovRadar-Strategic/10.0 (Compliance Monitoring for Obs BYGG)"

# --- HJELPEFUNKSJONER ---

def make_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    # Inkluderer Brotli (br) for moderne komprimering
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate, br"})
    return session

def clean_html(html_content: str) -> str:
    if not html_content: return ""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # STØYFILTRERING: Finn selve innholdet først
    content = soup.find("article") or soup.find("main") or soup.find(id="main") or soup.find(id="content")
    if content: soup = content
    
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        element.decompose()
        
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n\s*\n+", "\n\n", text) # Komprimerer tomme linjer
    text = re.sub(r"[ \t]+", " ", text) # Fjerner doble mellomrom
    return text.strip()

# 

# --- KJERNEFUNKSJONER ---

def sjekk_endringer():
    cache = load_cache()
    sess = make_session()
    funn = []

    for navn, url in LOVER.items():
        try:
            prev_entry = cache.get(navn, {})
            headers = {"If-None-Match": prev_entry.get("etag")} if prev_entry.get("etag") else {}
            
            r = sess.get(url, headers=headers, timeout=(10, 30))
            if r.status_code == 304:
                print(f" ✅ {navn}: Uendret"); continue
            
            r.raise_for_status()
            print(f" 📡 Sjekker {navn} (Status: {r.status_code})")
            
            clean_text = clean_html(r.text)
            current_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
            
            if current_hash != prev_entry.get("hash"):
                likhet = difflib.SequenceMatcher(None, prev_entry.get("text", ""), clean_text).ratio()
                endring_pct = (1 - likhet) * 100
                
                if endring_pct >= THRESHOLD:
                    diff_txt = "\n".join(difflib.unified_diff(
                        prev_entry.get("text", "").splitlines(), 
                        clean_text.splitlines(), n=3, lineterm=""
                    ))
                    funn.append({"navn": navn, "url": url, "prosent": endring_pct, "diff": diff_txt})
            
            cache[navn] = {"hash": current_hash, "text": clean_text, "url": url, "etag": r.headers.get("ETag")}
            time.sleep(1.5) # Skånsom pause mellom hver kilde
            
        except Exception as e:
            print(f" ⚠️ Feil ved {navn}: {e}")

    save_cache(cache)
    return funn

# ... (send_epost funksjonen forblir lik din v9.0) ...
