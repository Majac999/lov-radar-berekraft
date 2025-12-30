import os, json, hashlib, smtplib, requests, difflib, re, datetime, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# --- 1. KONFIGURASJON ---
LOVER = {
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 (Ytre miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",
    "Miljødirektoratet: Høringer": "https://www.miljodirektoratet.no/hoeringer/"
}

CACHE_FILE = "lovradar_cache.json"
THRESHOLD = 0.5 # Prosent endring før varsling
# Helt nøytral User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LovRadar/10.1"

# --- 2. HJELPEFUNKSJONER (FIKSET) ---

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def make_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    # Fjernet 'br' for å unngå bibliotek-konflikt
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    return session

def clean_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    # Finn hovedinnhold for å unngå falske treff på menyer/reklame
    content = soup.find("article") or soup.find("main") or soup.body
    if not content: return ""
    
    for tag in content(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    
    text = content.get_text(separator=" ")
    return re.sub(r'\s+', ' ', text).strip()

# --- 3. KJERNEFUNKSJONER ---

def sjekk_endringer():
    cache = load_cache()
    sess = make_session()
    funn = []

    for navn, url in LOVER.items():
        try:
            print(f"📡 Skanner: {navn}")
            r = sess.get(url, timeout=20)
            r.raise_for_status()
            
            clean_text = clean_html(r.text)
            current_hash = hashlib.sha256(clean_text.encode()).hexdigest()
            
            prev = cache.get(navn, {})
            if prev and current_hash != prev.get("hash"):
                likhet = difflib.SequenceMatcher(None, prev.get("text", ""), clean_text).ratio()
                endring = (1 - likhet) * 100
                
                if endring >= THRESHOLD:
                    funn.append({"navn": navn, "url": url, "prosent": endring})
            
            cache[navn] = {"hash": current_hash, "text": clean_text}
            time.sleep(2) # Vær ekstra skånsom mot Lovdata
        except Exception as e:
            print(f"⚠️ Feil: {navn} - {e}")

    save_cache(cache)
    return funn

if __name__ == "__main__":
    resultater = sjekk_endringer()
    print(f"✅ Ferdig. Fant {len(resultater)} endringer.")
