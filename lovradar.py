import os
import json
import hashlib
import smtplib
import requests
import difflib
import re
import datetime
from email.mime.text import MIMEText
from email.header import Header
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup 

# --- DEN KOMPLETTE RADAREN (Compliance + Strategi) ---
LOVER = {
    # === 1. HARD LAW (Må følges i dag) ===
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Avfallsforskriften (Kap 6-7 Emballasje)": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    "Åpenhetsloven (Leverandørkjeder)": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Markedsføringsloven (Grønnvasking)": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 (Kap 9 Ytre miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",

    # === 2. SOFT LAW (Tolkning & Markedsføring) ===
    "Forbrukertilsynet: Bærekraftveileder": "https://www.forbrukertilsynet.no/lov-og-rett/veiledninger-og-retningslinjer/forbrukertilsynets-veiledning-om-bruk-av-baerekraftpastander-markedsforing",
    "Miljødirektoratet: Kjemikalienyheter": "https://www.miljodirektoratet.no/ansvarsomrader/kjemikalier/reach/",
    "DFØ: Miljøkrav i offentlige innkjøp": "https://www.anskaffelser.no/berekraftige-anskaffingar/klima-og-miljo-i-offentlige-anskaffelser",
    "Svanemerket: Nye krav (Høringer)": "https://svanemerket.no/horinger/",

    # === 3. FREMTID & STRATEGI (EØS/EU) ===
    "Regjeringen: EØS-notater (Klima/Miljø)": "https://www.regjeringen.no/no/tema/europapolitikk/eos-notatbasen/id686653/?topic=klima-og-miljo",
    
    # ✅ RETTET LENKE (hoeringer):
    "Miljødirektoratet: Høringer og konsultasjoner": "https://www.miljodirektoratet.no/hoeringer/"
}

CACHE_FILE = "lovradar_baerekraft_cache.json"

# Terskel: 0.5% (Fanger opp små, men viktige juridiske justeringer)
THRESHOLD = float(os.environ.get("THRESHOLD", "0.5"))

# User-Agent identifiserer roboten din overfor nettsidene
USER_AGENT = "LovRadar-Complete/8.5 (Internal Compliance Tool; +https://github.com/Majac999)" 

# E-post innstillinger
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_RECIPIENT", EMAIL_USER)

# --- HJELPEFUNKSJONER ---

def make_session():
    session = requests.Session()
    # Robust retry som håndterer både serverfeil og rate-limiting (429)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session

def get_company_context():
    context = os.environ.get("COMPANY_CONTEXT")
    if not context:
        return "Byggevarehandel (Obs Bygg/Coop). Fokus: Sirkulærøkonomi, kjemikalier, emballasje, åpenhetsloven, EU-taksonomi og unngå grønnvasking."
    return context

def get_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def clean_html(html_content: str) -> str:
    """Avansert vasking som fjerner menyer og støy fra ulike offentlige nettsider."""
    if not html_content: return ""
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Prøv å finne hovedinnholdet (snevrer inn søket)
        main_content = soup.find("main") or soup.find(id="content") or soup.find(id="main") or soup.find("article")
        if main_content:
            soup = main_content

        # 2. Fjern teknisk støy (script, style, nav osv.)
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "meta", "button", "aside", "form"]):
            element.decompose() 
            
        # 3. Fjern UI-elementer (Print, Share, TOC, Nyhetsbrev, Cookies)
        noisy_classes = re.compile(r'(share|social|print|tool|toc|breadcrumb|menu|newsletter|cookie|popup|banner|related|filter)', re.IGNORECASE)
        for div in soup.find_all(class_=noisy_classes):
            div.decompose()
        
        for div in soup.find_all(id=noisy_classes):
            div.decompose()

        # 4. Hent tekst
        text = soup.get_text(separator=" ")
        
        # 5. Fjern HTML-kommentarer
        text = re.sub(r"", "", text, flags=re.DOTALL)
        
        # 6. Normaliser whitespace
        text = re.sub(r"\s+", " ", text).strip()
        
        return text
    except Exception as e:
        print(f"⚠️ Feil i clean_html: {e}")
        return html_content 

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_cache():
    if not os.path.exists(CACHE_FILE): return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def unified_diff(old: str, new: str, context=3) -> str:
    old_words = old.split(" ")
    new_words = new.split(" ")
    
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    diff = []
    
    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        if opcode == 'equal':
            if a1 - a0 > context * 2:
                diff.append(" ".join(old_words[a0:a0+context]))
                diff.append("... [...] ...")
                diff.append(" ".join(old_words[a1-context:a1]))
            else:
                diff.append(" ".join(old_words[a0:a1]))
        elif opcode == 'insert':
            diff.append(f"🟢 [NYTT]: {' '.join(new_words[b0:b1])}")
        elif opcode == 'delete':
            diff.append(f"🔴 [SLETTET]: {' '.join(old_words[a0:a1])}")
        elif opcode == 'replace':
            diff.append(f"✏️ [ENDRET]: {' '.join(old_words[a0:a1])} -> {' '.join(new_words[b0:b1])}")
            
    return "\n".join(diff)[:5000] # Litt større grense for å fange EU-tekster

# --- KJERNEFUNKSJONER ---

def sjekk_endringer():
    cache = load_cache()
    sess = make_session()
    funn = []

    print(f"🔍 Starter sjekk av {len(LOVER)} STRATEGISKE KILDER (Terskel: {THRESHOLD}%)...")

    for navn, url in LOVER.items():
        try:
            prev_entry = cache.get(navn, {})
            etag = prev_entry.get("etag")
            headers = {"If-None-Match": etag} if etag else {}

            # Økt timeout fordi Regjeringen/EØS-sider kan være trege
            r = sess.get(url, headers=headers, timeout=(10, 30))
            
            if r.status_code == 304:
                print(f" ✅ {navn}: Uendret (304)")
                continue
                
            r.raise_for_status()
            
        except Exception as e:
            print(f" ⚠️  FEIL ved {navn} ({url}): {e}")
            continue

        clean_text = clean_html(r.text)
        current_hash = sha256(clean_text)
        new_etag = r.headers.get("ETag")

        prev_hash = prev_entry.get("hash")
        prev_text = prev_entry.get("text", "")

        cache[navn] = {
            "hash": current_hash, 
            "text": clean_text, 
            "url": url,
            "etag": new_etag,
            "sist_sjekket": get_timestamp()
        }

        if not prev_hash:
            print(f" 🆕 {navn}: Lagret for første gang.")
            continue

        if current_hash == prev_hash:
            print(f" ✅ {navn}: Ingen tekstendring.")
            continue

        matcher = difflib.SequenceMatcher(None, prev_text, clean_text)
        likhet = matcher.ratio()
        endring_pct = (1 - likhet) * 100

        if endring_pct >= THRESHOLD:
            print(f" 🚨 ENDRING: {navn} ({endring_pct:.2f}%)")
            funn.append({
                "navn": navn,
                "url": url,
                "prosent": endring_pct,
                "diff": unified_diff(prev_text, clean_text)
            })
        else:
            print(f" ⚪ {navn}: Endring under terskel ({endring_pct:.2f}%)")

    save_cache(cache)
    return funn

def send_epost(funn):
    if not funn:
        return

    if not (EMAIL_USER and EMAIL_PASS):
        print("❌ E-post kan ikke sendes: Mangler brukernavn/passord.")
        for f in funn:
             print(f"\n--- ENDRING I {f['navn']} ---\n{f['diff']}\n")
        return

    print(f"📧 Forbereder varsel for {len(funn)} endringer...")

    linjer = [f"# 🌍 LovRadar: Strategisk Bærekraftsvarsel"]
    linjer.append(f"**Tidspunkt:** {get_timestamp()}\n")
    linjer.append(f"Det er oppdaget **{len(funn)}** endringer som påvirker Obs Bygg/Coop.\n")
    
    for f in funn:
        linjer.append(f"## 🔴 {f['navn']}")
        linjer.append(f"- **Omfang:** {f['prosent']:.2f}% endring")
        linjer.append(f"- **Kilde:** {f['url']}")
        linjer.append("\n**Hva er endret (Diff):**")
        linjer.append("```diff")
        linjer.append(f['diff'])
        linjer.append("```\n---")

    # --- AI-INSTRUKS FOR TOTALANALYSE ---
    linjer.append("\n### 🤖 AI-ANALYSE (JUS, MARKEDSFØRING & STRATEGI)")
    linjer.append("**DIN ROLLE:** Juridisk og kommersiell bærekraftsrådgiver for Coop/Obs Bygg.")
    linjer.append("**OPPGAVE:** Analyser endringene ovenfor kort og presist:")
    
    linjer.append("\n**1. MARKEDSFØRING (Risiko for Grønnvasking):**")
    linjer.append("- Endrer dette hvilke ord/påstander vi kan bruke i reklame?")
    linjer.append("- Må vi oppdatere nettsider eller emballasje?")
    
    linjer.append("\n**2. DRIFT & INNKJØP (Compliance):**")
    linjer.append("- Er nye stoffer forbudt? Nye krav til emballasje eller sortering?")
    linjer.append("- Påvirker dette Åpenhetsloven-vurderingene våre?")
    
    linjer.append("\n**3. FREMTID & STRATEGI (Hvis EØS/Høring):**")
    linjer.append("- Hva kommer fra EU? Hvor lang tid har vi før dette treffer butikkhyllene?")
    linjer.append("- Bør vi sende innspill til høringen?")
    
    msg = MIMEText("\n".join(linjer), "plain", "utf-8")
    msg["Subject"] = Header(f"🌍 Strategivarsel: {funn[0]['navn']}", "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print("✅ E-post sendt.")
    except Exception as e:
        print(f"❌ Feil ved sending: {e}")

if __name__ == "__main__":
    funn = sjekk_endringer()
    send_epost(funn)
