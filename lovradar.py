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
    "TEK17 Kap 9 (Miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",
    "Byggevareforskriften (DOK)": "https://lovdata.no/dokument/SF/forskrift/2014-12-17-1714",
    "Arbeidsmiljøloven": "https://lovdata.no/dokument/NL/lov/2005-06-17-62"
}

KEYWORDS = ["Stortinget", "Norge", "2025"]
CACHE_FILE = "lovradar_cache.json"
THRESHOLD = 0.5
USER_AGENT = "Mozilla/5.0 (compatible; LovRadar/12.0; Strategic Monitoring)"

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

def extract_text(html, url):
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    
    # Prøver å finne selve dokumentinnholdet
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
        # Del A: RSS-skanning (Bredde)
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
                text = extract_text(html, url)
                new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                
                prev = cache.get(navn, {})
                if prev and new_hash != prev.get("hash"):
                    similarity = difflib.SequenceMatcher(None, prev.get("text", ""), text).ratio()
                    change = round((1 - similarity) * 100, 2)
                    if change >= THRESHOLD:
                        findings["deep"].append({"navn": navn, "prosent": change, "url": url})
                
                # Oppdaterer hukommelsen (begrenser tekst til 5000 tegn for å spare plass)
                cache[navn] = {"hash": new_hash, "text": text[:5000]}

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    return findings

# --- 4. RAPPORTERING ---

def send_rapport(findings):
    user = os.environ.get("EMAIL_USER")
    pw = os.environ.get("EMAIL_PASS")
    to = os.environ.get("EMAIL_RECIPIENT")

    if not (findings["rss"] or findings["deep"]) or not all([user, pw, to]):
        logger.info("Ingen endringer funnet eller manglende e-postkonfigurasjon.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🛡️ LovRadar v12: Strategisk Rapport {datetime.now().strftime('%d.%m.%Y')}"
    msg["From"], msg["To"] = user, to
    
    html = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333;">
        <div style="background: #1a5f7a; color: white; padding: 20px; border-radius: 8px;">
            <h2 style="margin:0;">Regulatorisk Radar v12</h2>
            <p>Overvåkning for byggevarehandel og bærekraft</p>
        </div>
        
        <h3 style="color: #d9534f;">🔴 Endringer i eksisterende lovtekst:</h3>
        {"".join([f"<div style='border-left:4px solid #d9534f; padding-left:10px;'><p><b>{d['navn']}</b>: {d['prosent']}% endring detektert.<br><a href='{d['url']}'>Gå til kilde</a></p></div>" for d in findings['deep']]) or "<p>Ingen endringer i lovtekst i dag.</p>"}
        
        <hr style="border:0; border-top:1px solid #eee; margin:20px 0;">
        
        <h3 style="color: #5bc0de;">📡 Nye treff i nyhetsstrømmer (Keywords):</h3>
        {"".join([f"<p>• Tema <b>'{r['tema']}'</b> identifisert hos <i>{r['kilde']}</i>.<br><a href='{r['url']}'>Åpne nyhetsstrøm</a></p>" for r in findings['rss']]) or "<p>Ingen nye nøkkelord funnet i dag.</p>"}
        
        <p style="font-size: 11px; color: #999; margin-top:30px;">Anonymisert overvåkning generert for Obs BYGG / Coop-kontekst.</p>
    </body></html>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pw)
            s.send_message(msg)
        logger.info("📧 Strategisk rapport sendt!")
    except Exception as e:
        logger.error(f"Kunne ikke sende e-post: {e}")

if __name__ == "__main__":
    resultater = asyncio.run(sjekk_alt())
    send_rapport(resultater)
