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

# --- KONFIGURASJON: BÆREKRAFT, MARKEDSFØRING & COMPLIANCE ---
LOVER = {
    # --- HARD LAW (Lover og forskrifter) ---
    "Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",
    "Avfallsforskriften (Kap 6-7 Emballasje)": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    "Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",
    "Markedsføringsloven (Villedende praksis)": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "TEK17 (Kap 9 Ytre miljø)": "https://www.dibk.no/regelverk/byggteknisk-forskrift-tek17/9/9-1",

    # --- SOFT LAW (Veiledere og Tilsyn - Kritisk for drift/markedsføring) ---
    "Veileder: Bærekraftpåstander": "https://www.forbrukertilsynet.no/lov-og-rett/veiledninger-og-retningslinjer/forbrukertilsynets-veiledning-om-bruk-av-baerekraftpastander-markedsforing",
    "Kjemikalier (REACH Nyheter)": "https://www.miljodirektoratet.no/ansvarsomrader/kjemikalier/reach/",
    "DFØ - Miljøkrav anskaffelser": "https://www.anskaffelser.no/berekraftige-anskaffingar/klima-og-miljo-i-offentlige-anskaffelser",
    "Svanemerket - Høringer": "https://svanemerket.no/horinger/",
    "Etisk Handel - Åpenhetsloven": "https://etiskhandel.no/aapenhetsloven/"
}

CACHE_FILE = "lovradar_baerekraft_cache.json"

# FIKSET TERSKEL: Standard satt til 0.5% for å fange små endringer.
THRESHOLD = float(os.environ.get("THRESHOLD", "0.5"))

# HUSK: Bytt ut 'DITT_BRUKERNAVN'
USER_AGENT = "LovRadar-Sustainability/7.3 (Internal Compliance Tool; +https://github.com/DITT_BRUKERNAVN)" 

# E-post innstillinger
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_RECIPIENT", EMAIL_USER)

# --- HJELPEFUNKSJONER ---

def make_session():
    session = requests.Session()
    # FIKSET: Lagt til 429 (Too Many Requests) i retry-listen
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session

def get_company_context():
    context = os.environ.get("COMPANY_CONTEXT")
    if not context:
        return "Byggevarehandel (Obs Bygg/Coop). Fokus: Sirkulærøkonomi, kjemikalier, emballasje, åpenhetsloven og unngå grønnvasking i markedsføring."
    return context

def get_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def clean_html(html_content: str) -> str:
    """Robust vasking for å fjerne støy som menyer, del-knapper og footere."""
    if not html_content: return ""
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Prøv å finne hovedinnholdet
        main_content = soup.find("main") or soup.find(id="content") or soup.find(id="main") or soup.find("article")
        if main_content:
            soup = main_content

        # 2. Fjern teknisk støy
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "meta", "button", "aside", "form"]):
            element.decompose() 
            
        # 3. Aggressiv fjerning av UI-elementer
        noisy_classes = re.compile(r'(share|social|print|tool|toc|breadcrumb|menu|newsletter|cookie|popup|banner|related)', re.IGNORECASE)
        for div in soup.find_all(class_=noisy_classes):
            div.decompose()
        
        for div in soup.find_all(id=noisy_classes):
            div.decompose()

        # 4. Hent tekst
        text = soup.get_text(separator=" ")
        
        # 5. FIKSET: Regex for HTML-kommentarer (Var tom i din versjon)
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
            
    return "\n".join(diff)[:4000]

# --- KJERNEFUNKSJONER ---

def sjekk_endringer():
    cache = load_cache()
    sess = make_session()
    funn = []

    print(f"🔍 Starter sjekk av {len(LOVER)} BÆREKRAFTSKILDER (Terskel: {THRESHOLD}%)...")

    for navn, url in LOVER.items():
        try:
            prev_entry = cache.get(navn, {})
            etag = prev_entry.get("etag")
            headers = {"If-None-Match": etag} if etag else {}

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
        print("❌ E-post kan ikke sendes: Mangler brukernavn/passord i miljøvariabler.")
        for f in funn:
             print(f"\n--- ENDRING I {f['navn']} ---\n{f['diff']}\n")
        return

    print(f"📧 Forbereder varsel for {len(funn)} endringer...")

    linjer = [f"# 🌱 LovRadar Bærekraft: {len(funn)} endring(er)"]
    linjer.append(f"**Tidspunkt:** {get_timestamp()}\n")
    
    for f in funn:
        linjer.append(f"## 🔴 {f['navn']}")
        linjer.append(f"- **Endring:** {f['prosent']:.2f}%")
        linjer.append(f"- **Lenke:** {f['url']}")
        linjer.append("\n```diff")
        linjer.append(f['diff'])
        linjer.append("```\n---")

    # --- ESG & MARKEDSFØRINGS-ANALYSE ---
    linjer.append("\n### 🌍 AI-ANALYSE (ESG & MARKEDSFØRING)")
    linjer.append("**KONTEKST:**")
    linjer.append(get_company_context())
    
    linjer.append("\n**OPPGAVE:**")
    linjer.append("Du er en juridisk ekspert på bærekraft og markedsføring i Coop-systemet. Analyser endringene:")
    linjer.append("1. **Markedsføring:** Påvirker dette hva vi har lov å si i reklame? (Grønnvasking-risiko).")
    linjer.append("2. **Drift/Innkjøp:** Er det nye krav til kjemikalier, emballasje eller avfall?")
    linjer.append("3. **Compliance:** Krever dette oppdatering av våre aktsomhetsvurderinger (Åpenhetsloven)?")
    
    msg = MIMEText("\n".join(linjer), "plain", "utf-8")
    msg["Subject"] = Header(f"🌱 Bærekraftvarsel: Endring i {funn[0]['navn']}", "utf-8")
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
