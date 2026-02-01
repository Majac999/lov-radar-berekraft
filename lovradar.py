import os
import json
import hashlib
import smtplib
import difflib
import re
import asyncio
import aiohttp
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field, asdict
from typing import Optional
from bs4 import BeautifulSoup
import feedparser

# --- KONFIGURASJON ---

@dataclass
class LovKilde:
    """Representerer en lovkilde med metadata."""
    navn: str
    url: str
    kategori: str
    beskrivelse: str = ""

@dataclass
class RSSKilde:
    """Representerer en RSS-kilde."""
    navn: str
    url: str
    kategori: str

# Strategisk Område 1: Miljø, Kjemikalier & Bærekraft
MILJO_LOVER = [
    LovKilde("REACH-forskriften", "https://lovdata.no/dokument/SF/forskrift/2008-05-30-516", "miljø", "Kjemikalier og stoffer"),
    LovKilde("CLP-forskriften", "https://lovdata.no/dokument/SF/forskrift/2012-06-16-622", "miljø", "Klassifisering og merking"),
    LovKilde("Avfallsforskriften", "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930", "miljø", "Håndtering og sortering"),
    LovKilde("Biocidforskriften", "https://lovdata.no/dokument/SF/forskrift/2014-04-10-548", "miljø", "Impregnering og skadedyr"),
    LovKilde("Lov om bærekraftig finans", "https://lovdata.no/dokument/NL/lov/2021-12-22-161", "miljø", "Taksonomi"),
    LovKilde("Produktforskriften", "https://lovdata.no/dokument/SF/forskrift/2004-06-01-922", "miljø", "Farlige stoffer i produkter"),
]

# Strategisk Område 2: Bygg og Produktkrav
BYGG_LOVER = [
    LovKilde("DOK-forskriften", "https://lovdata.no/dokument/SF/forskrift/2014-12-17-1714", "bygg", "Dokumentasjon av byggevarer"),
    LovKilde("TEK17", "https://lovdata.no/dokument/SF/forskrift/2017-06-19-840", "bygg", "Byggteknisk forskrift"),
    LovKilde("TEK17 Kap 9 (Miljø)", "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1", "bygg", "Miljøkrav i bygg"),
    LovKilde("Produktkontrolloven", "https://lovdata.no/dokument/NL/lov/1976-06-11-79", "bygg", "Produktsikkerhet"),
    LovKilde("Tømmerforskriften", "https://lovdata.no/dokument/SF/forskrift/2015-04-24-406", "bygg", "Sporbarhet og import"),
    LovKilde("FEU-forskriften", "https://lovdata.no/dokument/SF/forskrift/2011-01-14-36", "bygg", "Elektrisk utstyr"),
    LovKilde("Internkontrollforskriften", "https://lovdata.no/dokument/SF/forskrift/1996-12-06-1127", "bygg", "HMS og rutiner"),
    LovKilde("Plan- og bygningsloven", "https://lovdata.no/dokument/NL/lov/2008-06-27-71", "bygg", "Hovedlov for bygging"),
]

# Strategisk Område 3: Handel og Forbruker
HANDEL_LOVER = [
    LovKilde("Forbrukerkjøpsloven", "https://lovdata.no/dokument/NL/lov/2002-06-21-34", "handel", "Reklamasjon og rettigheter"),
    LovKilde("Kjøpsloven", "https://lovdata.no/dokument/NL/lov/1988-05-13-27", "handel", "Næringskjøp"),
    LovKilde("Markedsføringsloven", "https://lovdata.no/dokument/NL/lov/2009-01-09-2", "handel", "Miljøpåstander/grønnvasking"),
    LovKilde("Åpenhetsloven", "https://lovdata.no/dokument/NL/lov/2021-06-18-99", "handel", "Leverandørkjeder"),
    LovKilde("Regnskapsloven", "https://lovdata.no/dokument/NL/lov/1998-07-17-56", "handel", "Bærekraftsrapportering/CSRD"),
    LovKilde("Angrerettloven", "https://lovdata.no/dokument/NL/lov/2014-06-20-27", "handel", "Fjernsalg"),
    LovKilde("Ehandelsloven", "https://lovdata.no/dokument/NL/lov/2003-05-23-35", "handel", "Elektronisk handel"),
]

ALLE_LOVER = MILJO_LOVER + BYGG_LOVER + HANDEL_LOVER

RSS_KILDER = [
    RSSKilde("Regjeringen: Klima & Miljø", "https://www.regjeringen.no/no/tema/klima-og-miljo/id1309/?type=rss", "miljø"),
    RSSKilde("Regjeringen: Næringsliv", "https://www.regjeringen.no/no/tema/naringsliv/id945/?type=rss", "handel"),
    RSSKilde("Regjeringen: Bygg & Bolig", "https://www.regjeringen.no/no/tema/plan-bygg-og-eiendom/id922/?type=rss", "bygg"),
    RSSKilde("Miljødirektoratet", "https://www.miljodirektoratet.no/rss/nyheter/", "miljø"),
    RSSKilde("Forbrukertilsynet", "https://www.forbrukertilsynet.no/feed", "handel"),
    RSSKilde("DiBK", "https://dibk.no/rss", "bygg"),
    RSSKilde("Stortinget: Saker", "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/RSS/", "alle"),
    RSSKilde("Arbeidstilsynet", "https://www.arbeidstilsynet.no/rss/nyheter/", "bygg"),
]

KEYWORDS = {
    "miljø": ["bærekraft", "sirkulær", "grønnvasking", "miljøkrav", "klimagass", "utslipp", "resirkulering", "gjenvinning", "avfall", "kjemikalier", "reach", "svhc", "miljødeklarasjon", "epd", "livssyklus", "karbonavtrykk", "taksonomi", "biocid", "clp", "faremerking", "miljøgift"],
    "bygg": ["byggevare", "ce-merking", "dokumentasjon", "produktpass", "tek17", "energikrav", "u-verdi", "brannkrav", "sikkerhet", "kvalitet", "treverk", "import", "eutr", "sporbarhet", "internkontroll", "elektrisk", "installasjon", "byggeplass", "hms"],
    "handel": ["emballasje", "reklamasjon", "garanti", "forbruker", "markedsføring", "miljøpåstand", "åpenhet", "leverandørkjede", "menneskerettigheter", "aktsomhet", "rapportering", "csrd", "esg", "compliance", "bærekraftsrapport", "verdikjede"]
}

ALLE_KEYWORDS = list(set(KEYWORDS["miljø"] + KEYWORDS["bygg"] + KEYWORDS["handel"]))

CONFIG = {
    "cache_file": "lovradar_cache.json",
    "change_threshold_percent": 0.3,
    "request_timeout": 30,
    "retry_attempts": 3,
    "retry_delay": 2,
    "rate_limit_delay": 0.5,
    "max_rss_entries": 15,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("LovRadar")

def normaliser_tekst(tekst: str) -> str:
    if not tekst: return ""
    tekst = re.sub(r'\d{1,2}\.\d{1,2}\.\d{2,4}', '', tekst)
    tekst = re.sub(r'\d{4}-\d{2}-\d{2}', '', tekst)
    tekst = re.sub(r'[Vv]ersjon\s*\d+(\.\d+)*', '', tekst)
    tekst = re.sub(r'Sist\s+endret.*?(?=\s{2}|\n|$)', '', tekst, flags=re.IGNORECASE)
    tekst = re.sub(r'\s+', ' ', tekst)
    tekst = re.sub(r'[§\-–—•·]', ' ', tekst)
    return tekst.strip().lower()

def ekstraher_lovtekst(html: str) -> str:
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "button", "form", "input", "select", "meta", "link", "noscript", "iframe"]):
        tag.decompose()
    for selector in [".breadcrumb", ".navigation", ".sidebar", ".footer", ".header", ".menu", ".pagination", ".share", ".print", "[class*='meta']", "[class*='date']", "[class*='version']"]:
        for elem in soup.select(selector): elem.decompose()
    content = soup.find("div", class_="LovdataParagraf") or soup.find("div", class_="LovdataLov") or soup.find("div", class_="dokumentBeholder") or soup.find("div", id="LovdataDokument")
    if not content: content = soup.find("article") or soup.find("main") or soup.find("div", {"role": "main"}) or soup.find("div", class_="content") or soup.body
    if not content: return ""
    return normaliser_tekst(content.get_text(separator=" "))

def beregn_endring(gammel: str, ny: str) -> tuple[float, list[str]]:
    if not gammel or not ny: return 0.0, []
    gammel_norm = normaliser_tekst(gammel)
    ny_norm = normaliser_tekst(ny)
    matcher = difflib.SequenceMatcher(None, gammel_norm, ny_norm)
    likhet = matcher.ratio()
    endring_prosent = round((1 - likhet) * 100, 2)
    endringer = []
    if endring_prosent > 0:
        differ = difflib.unified_diff(gammel_norm.split('. '), ny_norm.split('. '), lineterm='')
        for line in differ:
            if line.startswith('+') and not line.startswith('+++'):
                endring = line[1:].strip()
                if len(endring) > 20: endringer.append(f"Nytt: {endring[:200]}...")
            elif line.startswith('-') and not line.startswith('---'):
                endring = line[1:].strip()
                if len(endring) > 20: endringer.append(f"Fjernet: {endring[:200]}...")
    return endring_prosent, endringer[:5]

@dataclass
class Funn:
    type: str
    kilde: str
    kategori: str
    tittel: str
    url: str
    beskrivelse: str = ""
    endring_prosent: float = 0.0
    endringer: list = field(default_factory=list)
    keywords: list = field(default_factory=list)

class LovRadar:
    def __init__(self):
        self.cache = self._last_cache()
        self.funn: list[Funn] = []
        self.feil: list[str] = []

    def _last_cache(self) -> dict:
        if os.path.exists(CONFIG["cache_file"]):
            try:
                with open(CONFIG["cache_file"], 'r', encoding='utf-8') as f: return json.load(f)
            except Exception as e: logger.warning(f"Kunne ikke laste cache: {e}")
        return {"lover": {}, "siste_kjoring": None}

    def _lagre_cache(self):
        self.cache["siste_kjoring"] = datetime.now().isoformat()
        try:
            with open(CONFIG["cache_file"], 'w', encoding='utf-8') as f: json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e: logger.error(f"Kunne ikke lagre cache: {e}")

    async def _fetch_med_retry(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        for attempt in range(CONFIG["retry_attempts"]):
            try:
                async with session.get(url, timeout=CONFIG["request_timeout"]) as response:
                    if response.status == 200: return await response.text()
                    elif response.status == 429: await asyncio.sleep(CONFIG["retry_delay"] * (attempt + 1))
                    else: logger.warning(f"HTTP {response.status} for {url}"); return None
            except Exception as e: logger.error(f"Feil ved {url}: {e}")
            if attempt < CONFIG["retry_attempts"] - 1: await asyncio.sleep(CONFIG["retry_delay"])
        return None

    async def _skann_lover(self, session: aiohttp.ClientSession):
        for lov in ALLE_LOVER:
            await asyncio.sleep(CONFIG["rate_limit_delay"])
            html = await self._fetch_med_retry(session, lov.url)
            if not html: self.feil.append(f"Kunne ikke hente: {lov.navn}"); continue
            tekst = ekstraher_lovtekst(html)
            if not tekst: continue
            ny_hash = hashlib.sha256(tekst.encode()).hexdigest()
            if lov.navn in self.cache["lover"]:
                gammel = self.cache["lover"][lov.navn]
                if ny_hash != gammel.get("hash"):
                    endring_prosent, endringer = beregn_endring(gammel.get("tekst", ""), tekst)
                    if endring_prosent >= CONFIG["change_threshold_percent"]:
                        self.funn.append(Funn(type="lov", kilde=lov.navn, kategori=lov.kategori, tittel=f"{lov.navn} - {lov.beskrivelse}", url=lov.url, beskrivelse=lov.beskrivelse, endring_prosent=endring_prosent, endringer=endringer))
                        logger.info(f"⚠️ Endring detektert: {lov.navn} ({endring_prosent}%)")
            self.cache["lover"][lov.navn] = {"hash": ny_hash, "tekst": tekst[:10000], "sist_sjekket": datetime.now().isoformat(), "kategori": lov.kategori}

    async def _skann_rss(self, session: aiohttp.ClientSession):
        for rss in RSS_KILDER:
            await asyncio.sleep(CONFIG["rate_limit_delay"])
            html = await self._fetch_med_retry(session, rss.url)
            if not html: continue
            try:
                feed = feedparser.parse(html)
                for entry in feed.entries[:CONFIG["max_rss_entries"]]:
                    tittel, sammendrag, link = getattr(entry, 'title', ''), getattr(entry, 'summary', ''), getattr(entry, 'link', '')
                    tekst = f"{tittel} {sammendrag}".lower()
                    matchende_keywords = [kw for kw in ALLE_KEYWORDS if kw in tekst]
                    if matchende_keywords:
                        eksisterende_urls = [f.url for f in self.funn if f.type == "rss"]
                        if link not in eksisterende_urls:
                            self.funn.append(Funn(type="rss", kilde=rss.navn, kategori=rss.kategori, tittel=tittel, url=link, keywords=matchende_keywords[:5]))
            except Exception as e: logger.error(f"Feil ved parsing av {rss.navn}: {e}")

    async def kjor_skanning(self) -> dict:
        headers = {"User-Agent": CONFIG["user_agent"]}
        async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(limit=5)) as session:
            await self._skann_lover(session); await self._skann_rss(session)
        self._lagre_cache()
        return {"tidspunkt": datetime.now().isoformat(), "lovendringer": [asdict(f) for f in self.funn if f.type == "lov"], "nyheter": [asdict(f) for f in self.funn if f.type == "rss"], "feil
