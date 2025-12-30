import os, json, hashlib, smtplib, difflib, re, time, asyncio, aiohttp, logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# --- 1. STRATEGISK KONFIGURASJON ---
# RSS: Bredde-overvåking (Nye saker/forslag)
RSS_FEEDS = {
    "Stortinget: Nye Saker": "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/RSS/",
    "Regjeringen: Høringer": "https://www.regjeringen.no/no/id94/?type=rss",
    "Miljødirektoratet": "https://www.miljodirektoratet.no/rss/nyheter/"
}

# DEEP SCAN: Dybde-overvåking (Endringer i eksisterende tekst)
DEEP_LAWS = {
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "TEK17 Kap 9": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",
    "Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "Byggevareforskriften": "https://lovdata.no/dokument/SF/forskrift/2014-12-17-1714"
}

KEYWORDS = ["bærekraft", "emballasje", "produktpass", "omsetning", "bygg"]
CACHE_FILE = "lovradar_cache.json"
THRESHOLD = 0.5
USER_AGENT = "Mozilla/5.0 (compatible; LovRadar/12.0; Strategic Monitoring)"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- 2. ASYNKRON MOTOR ---

async def fetch_url(session, url):
    """Henter innhold asynkront for å unngå timeout"""
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                return await response.text()
    except Exception as e:
        logger.error(f"Feil ved henting av {url}: {e}")
    return None

def extract_text(html, url):
    """Renser HTML for juridisk analyse"""
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    
    # Lovdata-spesifikk rensing
    content = soup.find("div", class_="dokumentBeholder") or soup.find("article") or soup.body
    text = content.get_text(separator=" ")
    return re.sub(r'\s+', ' ', text).strip()

# --- 3. ANALYSE-LOGIKK ---

async def sjekk_alt():
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f: cache = json.load(f)

    findings = {"rss": [], "deep": []}
    
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        # Del A: Asynkron RSS (Bredde)
        for navn, url in RSS_FEEDS.items():
            html = await fetch_url(session, url)
            if html:
                # Enkel RSS-parsing (ser etter nøkkelord)
                for kw in KEYWORDS:
                    if kw.lower() in html.lower():
                        findings["rss"].append({"kilde": navn, "tema": kw, "url": url})
                        break

        # Del B: Asynkron Deep Scan (Dybde)
        for navn, url in DEEP_LAWS.items():
            html = await fetch_url(session, url)
            if html:
                text = extract_text(html, url)
                new_hash = hashlib.sha256(text.encode()).hexdigest()
                
                prev = cache.get(navn, {})
                if prev and new_hash != prev.get("hash"):
                    similarity = difflib.SequenceMatcher(None, prev.get("text", ""), text).ratio()
                    change = round((1 - similarity) * 100, 2)
                    if change >= THRESHOLD:
                        findings["deep"].append({"navn": navn, "prosent": change, "url": url})
                
                cache[navn] = {"hash": new_hash, "text": text[:5000]}

    with open(CACHE_FILE, 'w') as f: json.dump(cache, f, indent=2)
    return findings

# --- 4. RAPPORTERING ---

def send_rapport(findings):
    user, pw, to = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASS"), os.environ.get("EMAIL_RECIPIENT")
    if not (findings["rss"] or findings["deep"]) or not all([user, pw, to]): return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🛡️ LovRadar v12: Strategisk Rapport {datetime.now().strftime('%d.%m')}"
    
    html = f"""
    <html><body style="font-family: Arial, sans-serif;">
        <div style="background: #8b0000; color: white; padding: 20px; border-radius: 5px;">
            <h2>LovRadar Ultimate: Compliance & Nyheter</h2>
        </div>
        
        <h3>🔴 Endringer i eksisterende lovtekst:</h3>
        {"".join([f"<p><b>{d['navn']}</b>: {d['prosent']}% endring. <a href='{d['url']}'>Se lovdata</a></p>" for d in findings['deep']]) or "<p>Ingen endringer i dag.</p>"}
        
        <hr>
        
        <h3>📡 Nye treff i nyhetsstrømmer (Keywords):</h3>
        {"".join([f"<p>• {r['tema'].capitalize()} funnet i <i>{r['kilde']}</i>. <a href='{r['url']}'>Åpne kilde</a></p>" for r in findings['rss']]) or "<p>Ingen nye treff.</p>"}
    </body></html>
    """
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)
    logger.info("📧 Rapport sendt.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    resultater = loop.run_until_complete(sjekk_alt())
    send_rapport(resultater)
