import os
import json
import hashlib
import smtplib
import requests
import difflib
import re
from email.mime.text import MIMEText
from email.header import Header
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup  # <--- NY: Proff HTML-vasking

# --- KONFIG ---
LOVER = {
    # ... (Samme liste som før, behold den du har) ...
    "Kjøpsloven": "https://lovdata.no/dokument/NL/lov/1988-05-13-27",
    "Avfallsforskriften (Emballasje)": "https://lovdata.no/dokument/SF/forskrift/2004-06-01-930",
    # ... lim inn resten av listen din her ...
}

CACHE_FILE = "lovradar_cache.json"
THRESHOLD = float(os.environ.get("THRESHOLD", "0.2")) 
USER_AGENT = "LovRadar/7.0 (Internal Compliance Tool; +https://github.com/DITT_BRUKERNAVN)" # <--- Oppdatert iht Pkt 8

# E-post innstillinger
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_RECIPIENT", EMAIL_USER)

# --- HJELPEFUNKSJONER ---

def make_session():
    session = requests.Session()
    # Pkt 3: God retry-logikk beholdes
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session

def get_company_context():
    context = os.environ.get("COMPANY_CONTEXT")
    if not context:
        return "Generisk byggevarehandel."
    return context

def clean_html(html_content: str) -> str:
    """
    Pkt 1: Bruker BeautifulSoup for robust vasking.
    Fjerner menyer, footer, scripts og støy.
    """
    if not html_content: return ""
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Fjern elementer som ikke er selve lovteksten (Støy)
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
            element.decompose() # Sletter elementet helt

        # Hent tekst og normaliser whitespace
        text = soup.get_text(separator=" ")
        
        # Pkt 1: Regex for å fjerne HTML-kommentarer hvis noen gjenstår
        text = re.sub(r"", "", text, flags=re.DOTALL)
        
        # Normaliser whitespace (fjerner tabs og doble mellomrom)
        text = re.sub(r"\s+", " ", text).strip()
        
        return text
    except Exception as e:
        print(f"⚠️ Feil i clean_html: {e}")
        return html_content # Fallback til rå HTML hvis BS4 feiler

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_cache():
    if not os.path.exists(CACHE_FILE): return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def unified_diff(old: str, new: str, context=3) -> str:
    """
    Pkt 3/4: Lager en lesbar diff. 
    Splitter på ord for detaljer, men kunne vært setninger.
    """
    old_words = old.split(" ")
    new_words = new.split(" ")
    
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    diff = []
    
    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        if opcode == 'equal':
            if a1 - a0 > context * 2:
                diff.append(" ".join(old_words[a0:a0+context]))
                diff.append("... [...] ...") # Kortere separator
                diff.append(" ".join(old_words[a1-context:a1]))
            else:
                diff.append(" ".join(old_words[a0:a1]))
        elif opcode == 'insert':
            diff.append(f"🟢 [NYTT]: {' '.join(new_words[b0:b1])}")
        elif opcode == 'delete':
            diff.append(f"🔴 [SLETTET]: {' '.join(old_words[a0:a1])}")
        elif opcode == 'replace':
            diff.append(f"✏️ [ENDRET]: {' '.join(old_words[a0:a1])} -> {' '.join(new_words[b0:b1])}")
            
    return "\n".join(diff)[:2500] # Pkt 4: Trunker hvis ekstremt lang

# --- KJERNEFUNKSJONER ---

def sjekk_endringer():
    cache = load_cache()
    sess = make_session()
    funn = []

    print(f"🔍 Starter sjekk av {len(LOVER)} kilder...")

    for navn, url in LOVER.items():
        try:
            prev_entry = cache.get(navn, {})
            etag = prev_entry.get("etag")
            headers = {"If-None-Match": etag} if etag else {}

            r = sess.get(url, headers=headers, timeout=20) # Pkt 5: Økt timeout litt
            
            # Pkt 2: Bruk ETag effektivt
            if r.status_code == 304:
                print(f" ✅ {navn}: Uendret (304)")
                continue
                
            r.raise_for_status()
            
        except Exception as e:
            # Pkt 5: Bedre logging av feil
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
            "sist_sjekket": os.popen('date -u').read().strip() # Pkt: Metadata
        }

        if not prev_hash:
            print(f" 🆕 {navn}: Lagret for første gang.")
            continue

        if current_hash == prev_hash:
            print(f" ✅ {navn}: Ingen tekstendring.")
            continue

        # Endring oppdaget
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
            print(f" ⚪ {navn}: Ubetydelig endring ({endring_pct:.2f}%)")

    save_cache(cache)
    return funn

def send_epost(funn):
    if not funn:
        return

    # Pkt 6: Sjekk at vi faktisk kan sende mail
    if not (EMAIL_USER and EMAIL_PASS):
        print("❌ E-post kan ikke sendes: Mangler brukernavn/passord i Secrets.")
        return

    print(f"📧 Forbereder varsel for {len(funn)} endringer...")

    linjer = [f"# ⚖️ LovRadar: {len(funn)} endring(er)"]
    linjer.append(f"**Tidspunkt:** {os.popen('date -u').read().strip()}\n")
    
    for f in funn:
        linjer.append(f"## 🔴 {f['navn']}")
        linjer.append(f"- **Endring:** {f['prosent']:.2f}%")
        linjer.append(f"- **Lenke:** {f['url']}")
        linjer.append("\n```diff")
        linjer.append(f["diff"])
        linjer.append("```\n---")

    linjer.append("\n### 🤖 AI-ANALYSE INSTRUKS")
    linjer.append("**KONTEKST:**")
    linjer.append(get_company_context())
    linjer.append("\n**OPPGAVE:** Analyser konsekvenser for varer/drift.")
    
    msg = MIMEText("\n".join(linjer), "plain", "utf-8")
    msg["Subject"] = Header(f"LovRadar: Endring i {funn[0]['navn']}", "utf-8")
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
