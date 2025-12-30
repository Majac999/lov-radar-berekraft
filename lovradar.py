import os, json, hashlib, smtplib, requests, difflib, re, time
from datetime import datetime
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
THRESHOLD = 0.5 
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LovRadar/10.1"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def clean_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    content = soup.find("article") or soup.find("main") or soup.body
    if not content: return ""
    for tag in content(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return re.sub(r'\s+', ' ', content.get_text()).strip()

def sjekk_endringer():
    cache = load_cache()
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    funn = []

    for navn, url in LOVER.items():
        try:
            print(f"📡 Skanner: {navn}")
            r = sess.get(url, timeout=20)
            r.raise_for_status()
            text = clean_html(r.text)
            h = hashlib.sha256(text.encode()).hexdigest()
            
            if navn in cache and h != cache[navn]["hash"]:
                likhet = difflib.SequenceMatcher(None, cache[navn]["text"], text).ratio()
                if (1 - likhet) * 100 >= THRESHOLD:
                    funn.append({"navn": navn, "url": url, "prosent": round((1-likhet)*100, 2)})
            
            cache[navn] = {"hash": h, "text": text}
            time.sleep(2)
        except Exception as e: print(f"⚠️ Feil: {navn} - {e}")
    
    save_cache(cache)
    return funn

def send_epost(funn):
    user, pw, to = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASS"), os.environ.get("EMAIL_RECIPIENT")
    if not funn or not all([user, pw, to]): return
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🛡️ LovRadar: {len(funn)} regulatoriske endringer"
    msg["From"], msg["To"] = user, to
    
    html = f"<html><body><h2>Regulatorisk Radar: Bærekraft</h2>"
    for f in funn:
        html += f"<p><b>{f['navn']}</b>: {f['prosent']}% endring detektert. <a href='{f['url']}'>Se kilden her</a></p>"
    
    msg.attach(MIMEText(html + "</body></html>", "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)

if __name__ == "__main__":
    funn = sjekk_endringer()
    send_epost(funn)
    print("✅ LovRadar fullført.")
