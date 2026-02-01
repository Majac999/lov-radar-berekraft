+   1 #!/usr/bin/env python3
+   2 """
+   3 LovRadar v14.0 - Strategisk Regulatorisk Overvåkning
+   4 Bærekraft & Handel for Byggevarebransjen
+   5 
+   6 Forbedringer fra v13.3:
+   7 - Komplett dekning av alle tre strategiske områder
+   8 - Bedre tekstekstraksjon som ignorerer metadata/formatering
+   9 - Robust feilhåndtering med retry-logikk
+  10 - Strukturert konfigurasjon
+  11 - Forbedret endringsdeteksjon med kontekst
+  12 - Rate limiting for å unngå blokkering
+  13 - Validering av kilder
+  14 """
+  15 
+  16 import os
+  17 import json
+  18 import hashlib
+  19 import smtplib
+  20 import difflib
+  21 import re
+  22 import asyncio
+  23 import aiohttp
+  24 import logging
+  25 from datetime import datetime
+  26 from email.mime.text import MIMEText
+  27 from email.mime.multipart import MIMEMultipart
+  28 from dataclasses import dataclass, field, asdict
+  29 from typing import Optional
+  30 from bs4 import BeautifulSoup
+  31 import feedparser
+  32 
+  33 # --- KONFIGURASJON ---
+  34 
+  35 @dataclass
+  36 class LovKilde:
+  37     """Representerer en lovkilde med metadata."""
+  38     navn: str
+  39     url: str
+  40     kategori: str
+  41     beskrivelse: str = ""
+  42 
+  43 @dataclass
+  44 class RSSKilde:
+  45     """Representerer en RSS-kilde."""
+  46     navn: str
+  47     url: str
+  48     kategori: str
+  49 
+  50 # Strategisk Område 1: Miljø, Kjemikalier & Bærekraft
+  51 MILJO_LOVER = [
+  52     LovKilde("REACH-forskriften", "https://lovdata.no/dokument/SF/forskrift/2008-05-30-516", "miljø", "Kjemikalier og stoffer"),
+  53     LovKilde("CLP-forskriften", "https://lovdata.no/dokument/SF/forskrift/2012-06-16-622", "miljø", "Klassifisering og merking"),
+  54     LovKilde("Avfallsforskriften", "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930", "miljø", "Håndtering og sortering"),
+  55     LovKilde("Biocidforskriften", "https://lovdata.no/dokument/SF/forskrift/2014-04-10-548", "miljø", "Impregnering og skadedyr"),
+  56     LovKilde("Lov om bærekraftig finans", "https://lovdata.no/dokument/NL/lov/2021-12-22-161", "miljø", "Taksonomi"),
+  57     LovKilde("Produktforskriften", "https://lovdata.no/dokument/SF/forskrift/2004-06-01-922", "miljø", "Farlige stoffer i produkter"),
+  58 ]
+  59 
+  60 # Strategisk Område 2: Bygg og Produktkrav
+  61 BYGG_LOVER = [
+  62     LovKilde("DOK-forskriften", "https://lovdata.no/dokument/SF/forskrift/2014-12-17-1714", "bygg", "Dokumentasjon av byggevarer"),
+  63     LovKilde("TEK17", "https://lovdata.no/dokument/SF/forskrift/2017-06-19-840", "bygg", "Byggteknisk forskrift"),
+  64     LovKilde("TEK17 Kap 9 (Miljø)", "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1", "bygg", "Miljøkrav i bygg"),
+  65     LovKilde("Produktkontrolloven", "https://lovdata.no/dokument/NL/lov/1976-06-11-79", "bygg", "Produktsikkerhet"),
+  66     LovKilde("Tømmerforskriften", "https://lovdata.no/dokument/SF/forskrift/2015-04-24-406", "bygg", "Sporbarhet og import"),
+  67     LovKilde("FEU-forskriften", "https://lovdata.no/dokument/SF/forskrift/2011-01-14-36", "bygg", "Elektrisk utstyr"),
+  68     LovKilde("Internkontrollforskriften", "https://lovdata.no/dokument/SF/forskrift/1996-12-06-1127", "bygg", "HMS og rutiner"),
+  69     LovKilde("Plan- og bygningsloven", "https://lovdata.no/dokument/NL/lov/2008-06-27-71", "bygg", "Hovedlov for bygging"),
+  70 ]
+  71 
+  72 # Strategisk Område 3: Handel og Forbruker
+  73 HANDEL_LOVER = [
+  74     LovKilde("Forbrukerkjøpsloven", "https://lovdata.no/dokument/NL/lov/2002-06-21-34", "handel", "Reklamasjon og rettigheter"),
+  75     LovKilde("Kjøpsloven", "https://lovdata.no/dokument/NL/lov/1988-05-13-27", "handel", "Næringskjøp"),
+  76     LovKilde("Markedsføringsloven", "https://lovdata.no/dokument/NL/lov/2009-01-09-2", "handel", "Miljøpåstander/grønnvasking"),
+  77     LovKilde("Åpenhetsloven", "https://lovdata.no/dokument/NL/lov/2021-06-18-99", "handel", "Leverandørkjeder"),
+  78     LovKilde("Regnskapsloven", "https://lovdata.no/dokument/NL/lov/1998-07-17-56", "handel", "Bærekraftsrapportering/CSRD"),
+  79     LovKilde("Angrerettloven", "https://lovdata.no/dokument/NL/lov/2014-06-20-27", "handel", "Fjernsalg"),
+  80     LovKilde("Ehandelsloven", "https://lovdata.no/dokument/NL/lov/2003-05-23-35", "handel", "Elektronisk handel"),
+  81 ]
+  82 
+  83 # Samlet liste over alle lovkilder
+  84 ALLE_LOVER = MILJO_LOVER + BYGG_LOVER + HANDEL_LOVER
+  85 
+  86 # RSS-feeds for nyheter og høringer
+  87 RSS_KILDER = [
+  88     RSSKilde("Regjeringen: Klima & Miljø", "https://www.regjeringen.no/no/tema/klima-og-miljo/id1309/?type=rss", "miljø"),
+  89     RSSKilde("Regjeringen: Næringsliv", "https://www.regjeringen.no/no/tema/naringsliv/id945/?type=rss", "handel"),
+  90     RSSKilde("Regjeringen: Bygg & Bolig", "https://www.regjeringen.no/no/tema/plan-bygg-og-eiendom/id922/?type=rss", "bygg"),
+  91     RSSKilde("Miljødirektoratet", "https://www.miljodirektoratet.no/rss/nyheter/", "miljø"),
+  92     RSSKilde("Forbrukertilsynet", "https://www.forbrukertilsynet.no/feed", "handel"),
+  93     RSSKilde("DiBK", "https://dibk.no/rss", "bygg"),
+  94     RSSKilde("Stortinget: Saker", "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/RSS/", "alle"),
+  95     RSSKilde("Arbeidstilsynet", "https://www.arbeidstilsynet.no/rss/nyheter/", "bygg"),
+  96 ]
+  97 
+  98 # Utvidede nøkkelord for byggevarebransjen
+  99 KEYWORDS = {
+ 100     "miljø": [
+ 101         "bærekraft", "sirkulær", "grønnvasking", "miljøkrav", "klimagass", "utslipp",
+ 102         "resirkulering", "gjenvinning", "avfall", "kjemikalier", "reach", "svhc",
+ 103         "miljødeklarasjon", "epd", "livssyklus", "karbonavtrykk", "taksonomi",
+ 104         "biocid", "clp", "faremerking", "miljøgift"
+ 105     ],
+ 106     "bygg": [
+ 107         "byggevare", "ce-merking", "dokumentasjon", "produktpass", "tek17",
+ 108         "energikrav", "u-verdi", "brannkrav", "sikkerhet", "kvalitet",
+ 109         "treverk", "import", "eutr", "sporbarhet", "internkontroll",
+ 110         "elektrisk", "installasjon", "byggeplass", "hms"
+ 111     ],
+ 112     "handel": [
+ 113         "emballasje", "reklamasjon", "garanti", "forbruker", "markedsføring",
+ 114         "miljøpåstand", "åpenhet", "leverandørkjede", "menneskerettigheter",
+ 115         "aktsomhet", "rapportering", "csrd", "esg", "compliance",
+ 116         "bærekraftsrapport", "verdikjede"
+ 117     ]
+ 118 }
+ 119 
+ 120 ALLE_KEYWORDS = list(set(
+ 121     KEYWORDS["miljø"] + KEYWORDS["bygg"] + KEYWORDS["handel"]
+ 122 ))
+ 123 
+ 124 # Tekniske innstillinger
+ 125 CONFIG = {
+ 126     "cache_file": "lovradar_cache.json",
+ 127     "change_threshold_percent": 0.3,  # Minimum % endring for å rapportere
+ 128     "request_timeout": 30,
+ 129     "retry_attempts": 3,
+ 130     "retry_delay": 2,
+ 131     "rate_limit_delay": 0.5,  # Sekunder mellom requests
+ 132     "max_rss_entries": 15,
+ 133     "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
+ 134 }
+ 135 
+ 136 # Logging
+ 137 logging.basicConfig(
+ 138     level=logging.INFO,
+ 139     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
+ 140     datefmt="%Y-%m-%d %H:%M:%S"
+ 141 )
+ 142 logger = logging.getLogger("LovRadar")
+ 143 
+ 144 
+ 145 # --- HJELPEFUNKSJONER ---
+ 146 
+ 147 def normaliser_tekst(tekst: str) -> str:
+ 148     """
+ 149     Normaliserer tekst for sammenligning.
+ 150     Fjerner formatering, metadata og teknisk støy.
+ 151     """
+ 152     if not tekst:
+ 153         return ""
+ 154     
+ 155     # Fjern datoer og tidsstempler (ofte metadata som endres)
+ 156     tekst = re.sub(r'\d{1,2}\.\d{1,2}\.\d{2,4}', '', tekst)
+ 157     tekst = re.sub(r'\d{4}-\d{2}-\d{2}', '', tekst)
+ 158     
+ 159     # Fjern versjonsnumre og lignende
+ 160     tekst = re.sub(r'[Vv]ersjon\s*\d+(\.\d+)*', '', tekst)
+ 161     tekst = re.sub(r'Sist\s+endret.*?(?=\s{2}|\n|$)', '', tekst, flags=re.IGNORECASE)
+ 162     
+ 163     # Normaliser whitespace
+ 164     tekst = re.sub(r'\s+', ' ', tekst)
+ 165     
+ 166     # Fjern spesialtegn som kan variere
+ 167     tekst = re.sub(r'[§\-–—•·]', ' ', tekst)
+ 168     
+ 169     return tekst.strip().lower()
+ 170 
+ 171 
+ 172 def ekstraher_lovtekst(html: str) -> str:
+ 173     """
+ 174     Ekstraherer ren lovtekst fra HTML.
+ 175     Fokuserer på det materielle innholdet og ignorerer navigasjon/metadata.
+ 176     """
+ 177     if not html:
+ 178         return ""
+ 179     
+ 180     soup = BeautifulSoup(html, "html.parser")
+ 181     
+ 182     # Fjern elementer som ikke er innhold
+ 183     for tag in soup(["script", "style", "nav", "footer", "header", "aside", 
+ 184                      "button", "form", "input", "select", "meta", "link",
+ 185                      "noscript", "iframe"]):
+ 186         tag.decompose()
+ 187     
+ 188     # Fjern elementer med typiske metadata-klasser
+ 189     for selector in [".breadcrumb", ".navigation", ".sidebar", ".footer",
+ 190                      ".header", ".menu", ".pagination", ".share", ".print",
+ 191                      "[class*='meta']", "[class*='date']", "[class*='version']"]:
+ 192         for elem in soup.select(selector):
+ 193             elem.decompose()
+ 194     
+ 195     # Prøv å finne hovedinnholdet
+ 196     content = None
+ 197     
+ 198     # Lovdata-spesifikke selektorer
+ 199     content = soup.find("div", class_="LovdataParagraf") or \
+ 200               soup.find("div", class_="LovdataLov") or \
+ 201               soup.find("div", class_="dokumentBeholder") or \
+ 202               soup.find("div", id="LovdataDokument")
+ 203     
+ 204     # Generiske innholdssselektorer
+ 205     if not content:
+ 206         content = soup.find("article") or \
+ 207                   soup.find("main") or \
+ 208                   soup.find("div", {"role": "main"}) or \
+ 209                   soup.find("div", class_="content") or \
+ 210                   soup.body
+ 211     
+ 212     if not content:
+ 213         return ""
+ 214     
+ 215     # Hent ren tekst
+ 216     tekst = content.get_text(separator=" ")
+ 217     
+ 218     return normaliser_tekst(tekst)
+ 219 
+ 220 
+ 221 def beregn_endring(gammel: str, ny: str) -> tuple[float, list[str]]:
+ 222     """
+ 223     Beregner prosentvis endring og returnerer de viktigste endringene.
+ 224     """
+ 225     if not gammel or not ny:
+ 226         return 0.0, []
+ 227     
+ 228     # Normaliser for sammenligning
+ 229     gammel_norm = normaliser_tekst(gammel)
+ 230     ny_norm = normaliser_tekst(ny)
+ 231     
+ 232     # Beregn likhet
+ 233     matcher = difflib.SequenceMatcher(None, gammel_norm, ny_norm)
+ 234     likhet = matcher.ratio()
+ 235     endring_prosent = round((1 - likhet) * 100, 2)
+ 236     
+ 237     # Finn de viktigste endringene
+ 238     endringer = []
+ 239     if endring_prosent > 0:
+ 240         differ = difflib.unified_diff(
+ 241             gammel_norm.split('. '),
+ 242             ny_norm.split('. '),
+ 243             lineterm=''
+ 244         )
+ 245         for line in differ:
+ 246             if line.startswith('+') and not line.startswith('+++'):
+ 247                 endring = line[1:].strip()
+ 248                 if len(endring) > 20:  # Ignorer små fragmenter
+ 249                     endringer.append(f"Nytt: {endring[:200]}...")
+ 250             elif line.startswith('-') and not line.startswith('---'):
+ 251                 endring = line[1:].strip()
+ 252                 if len(endring) > 20:
+ 253                     endringer.append(f"Fjernet: {endring[:200]}...")
+ 254     
+ 255     return endring_prosent, endringer[:5]  # Maks 5 endringer
+ 256 
+ 257 
+ 258 @dataclass
+ 259 class Funn:
+ 260     """Representerer et funn fra skanningen."""
+ 261     type: str  # "lov" eller "rss"
+ 262     kilde: str
+ 263     kategori: str
+ 264     tittel: str
+ 265     url: str
+ 266     beskrivelse: str = ""
+ 267     endring_prosent: float = 0.0
+ 268     endringer: list = field(default_factory=list)
+ 269     keywords: list = field(default_factory=list)
+ 270 
+ 271 
+ 272 # --- HOVEDMOTOR ---
+ 273 
+ 274 class LovRadar:
+ 275     """Hovedklasse for regulatorisk overvåkning."""
+ 276     
+ 277     def __init__(self):
+ 278         self.cache = self._last_cache()
+ 279         self.funn: list[Funn] = []
+ 280         self.feil: list[str] = []
+ 281     
+ 282     def _last_cache(self) -> dict:
+ 283         """Laster cache fra fil."""
+ 284         if os.path.exists(CONFIG["cache_file"]):
+ 285             try:
+ 286                 with open(CONFIG["cache_file"], 'r', encoding='utf-8') as f:
+ 287                     return json.load(f)
+ 288             except Exception as e:
+ 289                 logger.warning(f"Kunne ikke laste cache: {e}")
+ 290         return {"lover": {}, "siste_kjoring": None}
+ 291     
+ 292     def _lagre_cache(self):
+ 293         """Lagrer cache til fil."""
+ 294         self.cache["siste_kjoring"] = datetime.now().isoformat()
+ 295         try:
+ 296             with open(CONFIG["cache_file"], 'w', encoding='utf-8') as f:
+ 297                 json.dump(self.cache, f, indent=2, ensure_ascii=False)
+ 298         except Exception as e:
+ 299             logger.error(f"Kunne ikke lagre cache: {e}")
+ 300     
+ 301     async def _fetch_med_retry(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
+ 302         """Henter URL med retry-logikk."""
+ 303         for attempt in range(CONFIG["retry_attempts"]):
+ 304             try:
+ 305                 async with session.get(url, timeout=CONFIG["request_timeout"]) as response:
+ 306                     if response.status == 200:
+ 307                         return await response.text()
+ 308                     elif response.status == 429:  # Rate limited
+ 309                         await asyncio.sleep(CONFIG["retry_delay"] * (attempt + 1))
+ 310                     else:
+ 311                         logger.warning(f"HTTP {response.status} for {url}")
+ 312                         return None
+ 313             except asyncio.TimeoutError:
+ 314                 logger.warning(f"Timeout for {url} (forsøk {attempt + 1})")
+ 315             except Exception as e:
+ 316                 logger.error(f"Feil ved {url}: {e}")
+ 317             
+ 318             if attempt < CONFIG["retry_attempts"] - 1:
+ 319                 await asyncio.sleep(CONFIG["retry_delay"])
+ 320         
+ 321         return None
+ 322     
+ 323     async def _skann_lover(self, session: aiohttp.ClientSession):
+ 324         """Skanner alle lovkilder for endringer."""
+ 325         logger.info(f"Skanner {len(ALLE_LOVER)} lovkilder...")
+ 326         
+ 327         if "lover" not in self.cache:
+ 328             self.cache["lover"] = {}
+ 329         
+ 330         for lov in ALLE_LOVER:
+ 331             await asyncio.sleep(CONFIG["rate_limit_delay"])
+ 332             
+ 333             html = await self._fetch_med_retry(session, lov.url)
+ 334             if not html:
+ 335                 self.feil.append(f"Kunne ikke hente: {lov.navn}")
+ 336                 continue
+ 337             
+ 338             tekst = ekstraher_lovtekst(html)
+ 339             if not tekst:
+ 340                 continue
+ 341             
+ 342             ny_hash = hashlib.sha256(tekst.encode()).hexdigest()
+ 343             
+ 344             # Sjekk om vi har tidligere data
+ 345             if lov.navn in self.cache["lover"]:
+ 346                 gammel = self.cache["lover"][lov.navn]
+ 347                 if ny_hash != gammel.get("hash"):
+ 348                     endring_prosent, endringer = beregn_endring(
+ 349                         gammel.get("tekst", ""),
+ 350                         tekst
+ 351                     )
+ 352                     
+ 353                     if endring_prosent >= CONFIG["change_threshold_percent"]:
+ 354                         self.funn.append(Funn(
+ 355                             type="lov",
+ 356                             kilde=lov.navn,
+ 357                             kategori=lov.kategori,
+ 358                             tittel=f"{lov.navn} - {lov.beskrivelse}",
+ 359                             url=lov.url,
+ 360                             beskrivelse=lov.beskrivelse,
+ 361                             endring_prosent=endring_prosent,
+ 362                             endringer=endringer
+ 363                         ))
+ 364                         logger.info(f"⚠️  Endring detektert: {lov.navn} ({endring_prosent}%)")
+ 365             else:
+ 366                 logger.info(f"📝 Ny baseline for: {lov.navn}")
+ 367             
+ 368             # Oppdater cache (lagre kun hash og begrenset tekst)
+ 369             self.cache["lover"][lov.navn] = {
+ 370                 "hash": ny_hash,
+ 371                 "tekst": tekst[:10000],  # Begrens for cache-størrelse
+ 372                 "sist_sjekket": datetime.now().isoformat(),
+ 373                 "kategori": lov.kategori
+ 374             }
+ 375     
+ 376     async def _skann_rss(self, session: aiohttp.ClientSession):
+ 377         """Skanner RSS-feeds for relevante nyheter."""
+ 378         logger.info(f"Skanner {len(RSS_KILDER)} RSS-kilder...")
+ 379         
+ 380         for rss in RSS_KILDER:
+ 381             await asyncio.sleep(CONFIG["rate_limit_delay"])
+ 382             
+ 383             html = await self._fetch_med_retry(session, rss.url)
+ 384             if not html:
+ 385                 continue
+ 386             
+ 387             try:
+ 388                 feed = feedparser.parse(html)
+ 389                 
+ 390                 for entry in feed.entries[:CONFIG["max_rss_entries"]]:
+ 391                     tittel = getattr(entry, 'title', '')
+ 392                     sammendrag = getattr(entry, 'summary', '')
+ 393                     link = getattr(entry, 'link', '')
+ 394                     
+ 395                     tekst = f"{tittel} {sammendrag}".lower()
+ 396                     
+ 397                     # Finn matchende keywords
+ 398                     matchende_keywords = [
+ 399                         kw for kw in ALLE_KEYWORDS
+ 400                         if kw in tekst
+ 401                     ]
+ 402                     
+ 403                     if matchende_keywords:
+ 404                         # Unngå duplikater
+ 405                         eksisterende_urls = [f.url for f in self.funn if f.type == "rss"]
+ 406                         if link not in eksisterende_urls:
+ 407                             self.funn.append(Funn(
+ 408                                 type="rss",
+ 409                                 kilde=rss.navn,
+ 410                                 kategori=rss.kategori,
+ 411                                 tittel=tittel,
+ 412                                 url=link,
+ 413                                 keywords=matchende_keywords[:5]
+ 414                             ))
+ 415                 
+ 416             except Exception as e:
+ 417                 logger.error(f"Feil ved parsing av {rss.navn}: {e}")
+ 418     
+ 419     async def kjor_skanning(self) -> dict:
+ 420         """Kjører komplett skanning."""
+ 421         logger.info("=" * 60)
+ 422         logger.info("LovRadar v14.0 - Starter strategisk skanning")
+ 423         logger.info("=" * 60)
+ 424         
+ 425         headers = {"User-Agent": CONFIG["user_agent"]}
+ 426         connector = aiohttp.TCPConnector(limit=5)  # Begrens samtidige tilkoblinger
+ 427         
+ 428         async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
+ 429             # Kjør skanninger sekvensielt for å respektere rate limits
+ 430             await self._skann_lover(session)
+ 431             await self._skann_rss(session)
+ 432         
+ 433         self._lagre_cache()
+ 434         
+ 435         # Generer rapport
+ 436         rapport = {
+ 437             "tidspunkt": datetime.now().isoformat(),
+ 438             "lovendringer": [asdict(f) for f in self.funn if f.type == "lov"],
+ 439             "nyheter": [asdict(f) for f in self.funn if f.type == "rss"],
+ 440             "feil": self.feil,
+ 441             "statistikk": {
+ 442                 "lover_sjekket": len(ALLE_LOVER),
+ 443                 "rss_sjekket": len(RSS_KILDER),
+ 444                 "lovendringer_funnet": len([f for f in self.funn if f.type == "lov"]),
+ 445                 "nyheter_funnet": len([f for f in self.funn if f.type == "rss"])
+ 446             }
+ 447         }
+ 448         
+ 449         logger.info("-" * 60)
+ 450         logger.info(f"Skanning fullført: {rapport['statistikk']['lovendringer_funnet']} lovendringer, "
+ 451                    f"{rapport['statistikk']['nyheter_funnet']} relevante nyheter")
+ 452         
+ 453         return rapport
+ 454 
+ 455 
+ 456 # --- E-POST RAPPORT ---
+ 457 
+ 458 def generer_html_rapport(rapport: dict) -> str:
+ 459     """Genererer en formatert HTML-rapport."""
+ 460     
+ 461     dato = datetime.now().strftime('%d.%m.%Y')
+ 462     
+ 463     # Grupper funn etter kategori
+ 464     lov_miljo = [f for f in rapport["lovendringer"] if f["kategori"] == "miljø"]
+ 465     lov_bygg = [f for f in rapport["lovendringer"] if f["kategori"] == "bygg"]
+ 466     lov_handel = [f for f in rapport["lovendringer"] if f["kategori"] == "handel"]
+ 467     
+ 468     nyheter_miljo = [f for f in rapport["nyheter"] if f["kategori"] == "miljø"]
+ 469     nyheter_bygg = [f for f in rapport["nyheter"] if f["kategori"] == "bygg"]
+ 470     nyheter_handel = [f for f in rapport["nyheter"] if f["kategori"] == "handel"]
+ 471     nyheter_alle = [f for f in rapport["nyheter"] if f["kategori"] == "alle"]
+ 472     
+ 473     def render_lovendring(f):
+ 474         endringer_html = ""
+ 475         if f.get("endringer"):
+ 476             endringer_html = "<ul style='margin: 5px 0; padding-left: 20px; font-size: 12px; color: #666;'>"
+ 477             for e in f["endringer"][:3]:
+ 478                 endringer_html += f"<li>{e}</li>"
+ 479             endringer_html += "</ul>"
+ 480         
+ 481         return f"""
+ 482         <div style="background: #fff3cd; padding: 10px; margin: 10px 0; border-left: 4px solid #ffc107; border-radius: 4px;">
+ 483             <b>{f['kilde']}</b> <span style="color: #dc3545;">({f['endring_prosent']}% endring)</span><br>
+ 484             <span style="color: #666; font-size: 12px;">{f.get('beskrivelse', '')}</span>
+ 485             {endringer_html}
+ 486             <a href="{f['url']}" style="color: #007bff;">Se kilde →</a>
+ 487         </div>
+ 488         """
+ 489     
+ 490     def render_nyhet(f):
+ 491         keywords = ", ".join(f.get("keywords", [])[:3])
+ 492         return f"""
+ 493         <div style="padding: 8px 0; border-bottom: 1px solid #eee;">
+ 494             <b>{f['tittel']}</b><br>
+ 495             <span style="color: #666; font-size: 12px;">
+ 496                 {f['kilde']} • Stikkord: {keywords}
+ 497             </span><br>
+ 498             <a href="{f['url']}" style="color: #007bff; font-size: 12px;">Les mer →</a>
+ 499         </div>
+ 500         """
+ 501     
+ 502     def render_seksjon(tittel, emoji, lovendringer, nyheter, farge):
+ 503         if not lovendringer and not nyheter:
+ 504             return ""
+ 505         
+ 506         innhold = ""
+ 507         if lovendringer:
+ 508             innhold += "<h4 style='margin: 10px 0 5px 0;'>🔴 Lovendringer:</h4>"
+ 509             for f in lovendringer:
+ 510                 innhold += render_lovendring(f)
+ 511         
+ 512         if nyheter:
+ 513             innhold += "<h4 style='margin: 15px 0 5px 0;'>📰 Relevante nyheter:</h4>"
+ 514             for f in nyheter:
+ 515                 innhold += render_nyhet(f)
+ 516         
+ 517         return f"""
+ 518         <div style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 5px solid {farge};">
+ 519             <h3 style="margin: 0 0 10px 0; color: {farge};">{emoji} {tittel}</h3>
+ 520             {innhold}
+ 521         </div>
+ 522         """
+ 523     
+ 524     # Bygg seksjoner
+ 525     seksjoner = ""
+ 526     seksjoner += render_seksjon("Miljø, Kjemikalier & Bærekraft", "🌱", lov_miljo, nyheter_miljo, "#28a745")
+ 527     seksjoner += render_seksjon("Bygg og Produktkrav", "🏗️", lov_bygg, nyheter_bygg, "#17a2b8")
+ 528     seksjoner += render_seksjon("Handel og Forbruker", "🛒", lov_handel, nyheter_handel, "#6f42c1")
+ 529     
+ 530     if nyheter_alle:
+ 531         seksjoner += render_seksjon("Generelt (Stortinget)", "⚖️", [], nyheter_alle, "#6c757d")
+ 532     
+ 533     if not seksjoner:
+ 534         seksjoner = """
+ 535         <div style="padding: 20px; text-align: center; color: #666;">
+ 536             <p>✅ Ingen vesentlige endringer eller relevante nyheter denne perioden.</p>
+ 537         </div>
+ 538         """
+ 539     
+ 540     # Feil-seksjon
+ 541     feil_html = ""
+ 542     if rapport.get("feil"):
+ 543         feil_html = f"""
+ 544         <div style="margin: 20px 0; padding: 10px; background: #f8d7da; border-radius: 4px;">
+ 545             <b>⚠️ Tekniske merknader:</b>
+ 546             <ul style="margin: 5px 0;">
+ 547                 {"".join([f"<li>{f}</li>" for f in rapport["feil"][:5]])}
+ 548             </ul>
+ 549         </div>
+ 550         """
+ 551     
+ 552     # Komplett HTML
+ 553     html = f"""
+ 554     <!DOCTYPE html>
+ 555     <html>
+ 556     <head>
+ 557         <meta charset="utf-8">
+ 558         <title>LovRadar Rapport {dato}</title>
+ 559     </head>
+ 560     <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; 
+ 561                  max-width: 700px; margin: 0 auto; padding: 20px; background: #f5f5f5;">
+ 562         
+ 563         <!-- Header -->
+ 564         <div style="background: linear-gradient(135deg, #1a5f7a 0%, #2d8e9f 100%); 
+ 565                     color: white; padding: 25px; border-radius: 12px; margin-bottom: 20px;">
+ 566             <h1 style="margin: 0; font-size: 24px;">🛡️ LovRadar v14.0</h1>
+ 567             <p style="margin: 5px 0 0 0; opacity: 0.9;">Bærekraft & Handel - Byggevarebransjen</p>
+ 568             <p style="margin: 10px 0 0 0; font-size: 14px; opacity: 0.8;">
+ 569                 Strategisk rapport: {dato}
+ 570             </p>
+ 571         </div>
+ 572         
+ 573         <!-- Sammendrag -->
+ 574         <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 20px; 
+ 575                     display: flex; justify-content: space-around; text-align: center;">
+ 576             <div>
+ 577                 <div style="font-size: 28px; font-weight: bold; color: #dc3545;">
+ 578                     {rapport['statistikk']['lovendringer_funnet']}
+ 579                 </div>
+ 580                 <div style="font-size: 12px; color: #666;">Lovendringer</div>
+ 581             </div>
+ 582             <div>
+ 583                 <div style="font-size: 28px; font-weight: bold; color: #17a2b8;">
+ 584                     {rapport['statistikk']['nyheter_funnet']}
+ 585                 </div>
+ 586                 <div style="font-size: 12px; color: #666;">Relevante nyheter</div>
+ 587             </div>
+ 588             <div>
+ 589                 <div style="font-size: 28px; font-weight: bold; color: #28a745;">
+ 590                     {rapport['statistikk']['lover_sjekket']}
+ 591                 </div>
+ 592                 <div style="font-size: 12px; color: #666;">Kilder overvåket</div>
+ 593             </div>
+ 594         </div>
+ 595         
+ 596         <!-- Hovedinnhold -->
+ 597         <div style="background: white; padding: 20px; border-radius: 8px;">
+ 598             {seksjoner}
+ 599         </div>
+ 600         
+ 601         {feil_html}
+ 602         
+ 603         <!-- Footer -->
+ 604         <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
+ 605             <p>LovRadar v14.0 | Proof of Concept | Pilotfase</p>
+ 606             <p>Basert på offentlige rettskilder under NLOD 2.0</p>
+ 607         </div>
+ 608     </body>
+ 609     </html>
+ 610     """
+ 611     
+ 612     return html
+ 613 
+ 614 
+ 615 def send_epost_rapport(rapport: dict):
+ 616     """Sender rapport via e-post."""
+ 617     bruker = os.environ.get("EMAIL_USER", "").strip()
+ 618     passord = os.environ.get("EMAIL_PASS", "").strip()
+ 619     mottaker = os.environ.get("EMAIL_RECIPIENT", "").strip() or bruker
+ 620     
+ 621     if not all([bruker, passord, mottaker]):
+ 622         logger.warning("E-postkonfigurasjon mangler. Hopper over sending.")
+ 623         return False
+ 624     
+ 625     # Sjekk om det er noe å rapportere
+ 626     if not rapport["lovendringer"] and not rapport["nyheter"]:
+ 627         logger.info("Ingen funn å rapportere. Hopper over e-post.")
+ 628         return False
+ 629     
+ 630     msg = MIMEMultipart("alternative")
+ 631     dato = datetime.now().strftime('%d.%m.%Y')
+ 632     
+ 633     n_lov = rapport['statistikk']['lovendringer_funnet']
+ 634     n_nyheter = rapport['statistikk']['nyheter_funnet']
+ 635     
+ 636     msg["Subject"] = f"🛡️ LovRadar {dato}: {n_lov} lovendring(er), {n_nyheter} nyhet(er)"
+ 637     msg["From"] = bruker
+ 638     msg["To"] = mottaker
+ 639     
+ 640     html = generer_html_rapport(rapport)
+ 641     msg.attach(MIMEText(html, "html", "utf-8"))
+ 642     
+ 643     try:
+ 644         with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
+ 645             server.login(bruker, passord)
+ 646             server.sendmail(bruker, [mottaker], msg.as_string())
+ 647         logger.info(f"📧 Rapport sendt til {mottaker}")
+ 648         return True
+ 649     except Exception as e:
+ 650         logger.error(f"E-postfeil: {e}")
+ 651         return False
+ 652 
+ 653 
+ 654 # --- HOVEDPROGRAM ---
+ 655 
+ 656 async def main():
+ 657     """Hovedfunksjon."""
+ 658     radar = LovRadar()
+ 659     rapport = await radar.kjor_skanning()
+ 660     
+ 661     # Lagre rapport som JSON
+ 662     rapport_fil = f"lovradar_rapport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
+ 663     with open(rapport_fil, 'w', encoding='utf-8') as f:
+ 664         json.dump(rapport, f, indent=2, ensure_ascii=False)
+ 665     logger.info(f"📁 Rapport lagret: {rapport_fil}")
+ 666     
+ 667     # Send e-post
+ 668     send_epost_rapport(rapport)
+ 669     
+ 670     return rapport
+ 671 
+ 672 
+ 673 if __name__ == "__main__":
+ 674     asyncio.run(main())
