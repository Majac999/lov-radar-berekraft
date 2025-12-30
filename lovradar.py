import os, json, hashlib, smtplib, difflib, re, time, asyncio, aiohttp, logging, feedparser
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# --- 1. KONFIGURASJON ---
RSS_FEEDS = {
    "Regjeringen: Klima & Miljø": "https://www.regjeringen.no/no/id94/?type=rss",
    "Miljødirektoratet: Nyheter": "https://www.miljodirektoratet.no/rss/nyheter/",
    "Forbrukertilsynet: Markedsføring": "https://www.forbrukertilsynet.no/feed",
    "DiBK: Nyheter om byggeregler": "https://dibk.no/rss",
    "Stortinget: Nye Saker": "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/RSS/"
}

DEEP_LAWS = {
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Byggevareforskriften (DOK)": "https://lovdata.no/dokument/SF/forskrift/2014-12-17-1714",
    "Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 Kap 9 (Miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",
    "Avfallsforskriften": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    "Arbeidsmiljøloven": "https://lovdata.no/dokument/NL/lov/2005-06-17-62"
}

KEYWORDS = ["bærekraft", "emballasje", "produktpass", "sirkulær", "dokumentasjon", "grønnvasking", "miljøkrav"]
CACHE_FILE = "lovradar_cache.json"
THRESHOLD = 0.5

# NY ANONYM USER-AGENT: Ser ut som en helt vanlig Chrome-nettleser
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- 2. MOTOR ---
async def fetch_url(session, url):
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200: return await response.text()
    except Exception as e: logger.error(f"Feil ved {url}: {e}")
    return None

def extract_text(html):
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]): tag.decompose()
    content = soup.find("div", class_="dokumentBeholder") or soup.find("article") or soup.find("main") or soup.body
    return re.sub(r'\s+', ' ', content.get_text()).strip()

async def sjekk_alt():
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f: cache = json.load(f)

    findings = {"rss": [], "deep": []}
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        # RSS skanning
        tasks = [fetch_url(session, url) for url in RSS_FEEDS.values()]
        results = await asyncio.gather(*tasks)
        for (navn, url), html in zip(RSS_FEEDS.items(), results):
            if html:
                feed = feedparser.parse(html)
                for entry in feed.entries[:10]:
                    text = f"{entry.title} {getattr(entry, 'summary', '')}".lower()
                    for kw in KEYWORDS:
                        if kw in text:
                            findings["rss"].append({"kilde": navn, "tema": kw, "tittel": entry.title, "url": entry.link})
                            break
        # Lovendring skanning
        tasks_deep = [fetch_url(session, url) for url in DEEP_LAWS.values()]
        results_deep = await asyncio.gather(*tasks_deep)
        for (navn, url), html in zip(DEEP_LAWS.items(), results_deep):
            if html:
                text = extract_text(html)
                h = hashlib.sha256(text.encode()).hexdigest()
                if navn in cache and h != cache[navn]["hash"]:
                    sim = difflib.SequenceMatcher(None, cache[navn]["text"], text).ratio()
                    change = round((1-sim)*100, 2)
                    if change >= THRESHOLD: findings["deep"].append({"navn": navn, "prosent": change, "url": url})
                cache[navn] = {"hash": h, "text": text[:5000]}

    with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(cache, f, indent=2)
    return findings

def send_rapport(f):
    user = os.environ.get("EMAIL_USER", "").strip()
    pw = os.environ.get("EMAIL_PASS", "").strip()
    to = os.environ.get("EMAIL_RECIPIENT", "").strip()
    if not to: to = user
    if not (f["rss"] or f["deep"]) or not all([user, pw, to]): return
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🛡️ LovRadar v13.3: Strategisk Rapport {datetime.now().strftime('%d.%m')}"
    msg["From"] = user
    msg["To"] = to
    
    html = f"""<html><body style="font-family: Arial, sans-serif;">
        <div style="background: #1a5f7a; color: white; padding: 20px; border-radius: 8px;">
            <h2 style="margin:0;">LovRadar v13.3: Bærekraft & Compliance</h2>
            <p>Strategisk overvåkning - Konfidensiell Rapport</p>
        </div>
        <h3 style="color: #d9534f;">🔴 Lovendringer detektert:</h3>
        {"".join([f"<p><b>{d['navn']}</b>: {d['prosent']}% endring. <a href='{d['url']}'>Se kilde</a></p>" for d in f['deep']]) or "<p>Ingen endringer detektert.</p>"}
        <h3 style="color: #5bc0de;">📡 Relevante Nyheter & Høringer:</h3>
        {"".join([f"<p>• <b>{r['tittel']}</b> ({r['tema']}) hos <i>{r['kilde']}</i>. <a href='{r['url']}'>Link</a></p>" for r in f['rss']]) or "<p>Ingen treff i dag.</p>"}
    </body></html>"""
    
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pw)
            s.sendmail(user, [to], msg.as_string())
        logger.info(f"📧 Strategisk rapport sendt anonymt!")
    except Exception as e: logger.error(f"E-postfeil: {e}")

if __name__ == "__main__":
    res = asyncio.run(sjekk_alt())
    send_rapport(res)
