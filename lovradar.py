import os, json, hashlib, smtplib, difflib, re, time, asyncio, aiohttp, logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# --- 1. STRATEGISK KONFIGURASJON ---
# BREDDE: Fanger opp nye forslag og høringer
RSS_FEEDS = {
    "Stortinget: Nye Saker": "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/RSS/",
    "Regjeringen: Høringer": "https://www.regjeringen.no/no/id94/?type=rss",
    "Miljødirektoratet": "https://www.miljodirektoratet.no/rss/nyheter/"
}

# DYBDE: Overvåker endringer i eksisterende lovtekst
DEEP_LAWS = {
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 Kap 9": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",
    "Byggevareforskriften": "https://lovdata.no/dokument/SF/forskrift/2014-12-17-1714",
    "Arbeidsmiljøloven": "https://lovdata.no/dokument/NL/lov/2005-06-17-62"
}

# Strategiske nøkkelord for Obs BYGG
KEYWORDS = ["bærekraft", "emballasje", "produktpass", "omsetning", "bygg", "miljø", "Stortinget"]

CACHE_FILE = "lovradar_cache.json"
THRESHOLD = 0.5
USER_AGENT = "Mozilla/5.0 (compatible; LovRadar/12.1)"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- 2. ASYNKRON INFRASTRUKTUR ---

async def fetch_url(session, url):
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                return await response.text()
    except Exception as e:
        logger.error(f"Feil ved henting: {e}")
    return None

def extract_text(html):
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    content = soup.find("div", class_="dokumentBeholder") or soup.find("article") or soup.find("main") or soup.body
    return re.sub(r'\s+', ' ', content.get_text()).strip()

# --- 3. ANALYSE-MOTOR ---

async def sjekk_alt():
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: cache = json.load(f)
        except: cache = {}

    findings = {"rss": [], "deep": []}
    
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        # Del A: RSS (Bredde)
        tasks_rss = [fetch_url(session, url) for url in RSS_FEEDS.values()]
        rss_results = await asyncio.gather(*tasks_rss)
        
        for (navn, url), html in zip(RSS_FEEDS.items(), rss_results):
            if html:
                for kw in KEYWORDS:
                    if kw.lower() in html.lower():
                        findings["rss"].append({"kilde": navn, "tema": kw, "url": url})
                        break

        # Del B: Deep Scan (Dybde)
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
        logger.info("Ingen nye endringer detektert.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🛡️ LovRadar v12.1: Strategisk Rapport {datetime.now().strftime('%d.%m.%Y')}"
    msg["From"], msg["To"] = user, to
    
    html = f"""
    <html><body style="font-family: Arial, sans-serif;">
        <div style="background: #1a5f7a; color: white; padding: 20px; border-radius: 8px;">
            <h2 style="margin:0;">LovRadar: Bærekraft & Compliance</h2>
            <p>Automatisk overvåkning for Obs BYGG</p>
        </div>
        <h3>🔴 Endringer i eksisterende lovtekst:</h3>
        {"".join([f"<p><b>{d['navn']}</b>: {d['prosent']}% endring. <a href='{d['url']}'>Se kilde</a></p>" for d in findings['deep']]) or "<p>Ingen endringer.</p>"}
        <hr>
        <h3>📡 Nye treff i nyhetsstrømmer:</h3>
        {"".join([f"<p>• Tema <b>'{r['tema']}'</b> funnet hos <i>{r['kilde']}</i>. <a href='{r['url']}'>Åpne</a></p>" for r in findings['rss']]) or "<p>Ingen treff.</p>"}
    </body></html>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pw)
            s.send_message(msg)
        logger.info("📧 Rapport sendt!")
    except Exception as e: logger.error(f"E-postfeil: {e}")

if __name__ == "__main__":
    resultater = asyncio.run(sjekk_alt())
    send_rapport(resultater)
