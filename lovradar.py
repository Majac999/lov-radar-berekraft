import os, json, hashlib, smtplib, difflib, re, time, asyncio, aiohttp, logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# --- 1. STRATEGISK KONFIGURASJON ---

# BREDDE: Overvåker nyheter og kommende krav (Høringer og trender)
RSS_FEEDS = {
    "Regjeringen: Klima & Miljø": "https://www.regjeringen.no/no/id94/?type=rss",
    "Miljødirektoratet: Nyheter": "https://www.miljodirektoratet.no/rss/nyheter/",
    "Forbrukertilsynet: Markedsføring": "https://www.forbrukertilsynet.no/feed",
    "DiBK: Nyheter om byggeregler": "https://dibk.no/rss"
}

# DYBDE: Overvåker endringer i selve lovteksten (Compliance)
DEEP_LAWS = {
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Byggevareforskriften (DOK)": "https://lovdata.no/dokument/SF/forskrift/2014-12-17-1714",
    "Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 Kap 9 (Ytre Miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",
    "Avfallsforskriften (Emballasje)": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    "Arbeidsmiljøloven": "https://lovdata.no/dokument/NL/lov/2005-06-17-62"
}

# Operative nøkkelord for Obs BYGG / Bærekraft
KEYWORDS = [
    "bærekraft", "emballasje", "produktpass", "sirkulær", 
    "dokumentasjon", "klima", "grønnvasking", "miljøkrav", "byggevarer"
]

CACHE_FILE = "lovradar_cache.json"
THRESHOLD = 0.5
USER_AGENT = "Mozilla/5.0 (compatible; LovRadar/12.2; Strategic Monitoring)"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- 2. ASYNKRON INFRASTRUKTUR ---

async def fetch_url(session, url):
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                return await response.text()
    except Exception as e:
        logger.error(f"Feil ved henting av {url}: {e}")
    return None

def extract_text(html):
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    # Prøver å isolere hovedinnholdet for å unngå falske varsler fra menyer
    content = soup.find("div", class_="dokumentBeholder") or soup.find("article") or soup.find("main") or soup.body
    text = content.get_text(separator=" ")
    return re.sub(r'\s+', ' ', text).strip()

# --- 3. ANALYSE-MOTOR ---

async def sjekk_alt():
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: cache = json.load(f)
        except: cache = {}

    findings = {"rss": [], "deep": []}
    
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        # Del A: RSS-skanning
        tasks_rss = [fetch_url(session, url) for url in RSS_FEEDS.values()]
        rss_results = await asyncio.gather(*tasks_rss)
        
        for (navn, url), html in zip(RSS_FEEDS.items(), rss_results):
            if html:
                for kw in KEYWORDS:
                    if kw.lower() in html.lower():
                        findings["rss"].append({"kilde": navn, "tema": kw, "url": url})
                        break

        # Del B: Deep Scan (Lovendringer)
        tasks_deep = [fetch_url(session, url) for url in DEEP_LAWS.values()]
        deep_results = await asyncio.gather(*tasks_deep)
        
        for (navn, url), html in zip(DEEP_LAWS.items(), deep_results):
            if html:
                text = extract_text(html)
                new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                prev = cache.get(navn, {})
                
                if prev and new_hash != prev.get("hash"):
                    similarity = difflib.SequenceMatcher(None, prev.get("text", ""), text).ratio()
                    change = round((1 - similarity) * 100, 2)
                    if change >= THRESHOLD:
                        findings["deep"].append({"navn": navn, "prosent": change, "url": url})
                
                cache[navn] = {"hash": new_hash, "text": text[:5000]}

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    return findings

# --- 4. RAPPORTERING ---

def send_rapport(findings):
    user, pw, to = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASS"), os.environ.get("EMAIL_RECIPIENT")
    if not (findings["rss"] or findings["deep"]) or not all([user, pw, to]):
        logger.info("Ingen nye endringer å rapportere i dag.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🛡️ LovRadar: Strategisk Rapport for Obs BYGG {datetime.now().strftime('%d.%m.%Y')}"
    msg["From"], msg["To"] = user, to
    
    html = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="background: #1a5f7a; color: white; padding: 25px; border-radius: 10px;">
            <h2 style="margin:0;">Regulatorisk Radar v12.2</h2>
            <p style="margin:5px 0 0;">Strategisk monitorering: Bærekraft & Compliance</p>
        </div>
        
        <h3 style="color: #d9534f; border-bottom: 2px solid #eee; padding-bottom: 5px;">🔴 Lovendringer (Endring i paragraftekst)</h3>
        {"".join([f"<p><b>{d['navn']}</b> har endret seg med {d['prosent']}%.<br><a href='{d['url']}'>Gå til Lovdata</a></p>" for d in findings['deep']]) or "<p>Ingen endringer i overvåkede lover i dag.</p>"}
        
        <h3 style="color: #5bc0de; border-bottom: 2px solid #eee; padding-bottom: 5px;">📡 Relevante Nyheter & Høringer</h3>
        {"".join([f"<p>• Nøkkelordet <b>'{r['tema']}'</b> ble identifisert hos <i>{r['kilde']}</i>.<br><a href='{r['url']}'>Åpne kilden</a></p>" for r in findings['rss']]) or "<p>Ingen relevante nyhetstreff i dag.</p>"}
        
        <div style="margin-top: 40px; padding: 15px; background: #f9f9f9; font-size: 12px; color: #666; border-radius: 5px;">
            Dette er en automatisert tjeneste utviklet for intern beslutningsstøtte i Obs BYGG / Coop. 
            Kildene inkluderer Lovdata, Regjeringen og Miljødirektoratet.
        </div>
    </body></html>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pw)
            s.send_message(msg)
        logger.info("📧 Strategisk rapport sendt!")
    except Exception as e: logger.error(f"E-postfeil: {e}")

if __name__ == "__main__":
    resultater = asyncio.run(sjekk_alt())
    send_rapport(resultater)
