import os

import re

import difflib

import json

import hashlib

import smtplib

import requests

from email.mime.text import MIMEText

from email.header import Header

from requests.adapters import HTTPAdapter

from urllib3.util.retry import Retry



# --- KONFIG ---

LOVER = {

"Kjøpsloven": "https://lovdata.no/dokument/NL/lov/1988-05-13-27",

"Forbrukerkjøpsloven": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",

"Avhendingslova": "https://lovdata.no/dokument/NL/lov/1992-07-03-93",

"Markedsføringsloven": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",

"Angrerettloven": "https://lovdata.no/dokument/NL/lov/2014-06-20-27",

"E-handelsloven": "https://lovdata.no/dokument/NL/lov/2003-05-23-35",

"Finansavtaleloven": "https://lovdata.no/dokument/NL/lov/2020-12-18-146",

"Åpenhetsloven": "https://lovdata.no/dokument/NL/lov/2021-06-18-99",

"Arbeidsmiljøloven": "https://lovdata.no/dokument/NL/lov/2005-06-17-62",

"Likestillings- og diskrimineringsloven": "https://lovdata.no/dokument/NL/lov/2017-06-16-51",

"Plan- og bygningsloven": "https://lovdata.no/dokument/NL/lov/2008-06-27-71",

"Forurensningsloven": "https://lovdata.no/dokument/NL/lov/1981-03-13-6",

"Naturmangfoldloven": "https://lovdata.no/dokument/NL/lov/2009-06-19-100",

"Produktkontrolloven": "https://lovdata.no/dokument/NL/lov/1976-06-11-79",

"Regnskapsloven": "https://lovdata.no/dokument/NL/lov/1998-07-17-56",

"Bokføringsloven": "https://lovdata.no/dokument/NL/lov/2004-11-19-73",

"Lov om bærekraftig finans": "https://lovdata.no/dokument/NL/lov/2021-12-17-148",

}



CACHE_FILE = "lovradar_cache.json"

THRESHOLD = float(os.environ.get("THRESHOLD", "0.5")) # prosent terskel for endring

USER_AGENT = "LovRadar/6.0 (+https://example.local)"



SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")

SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

EMAIL_USER = os.environ.get("EMAIL_USER")

EMAIL_PASS = os.environ.get("EMAIL_PASS")

EMAIL_TO = os.environ.get("EMAIL_TO", EMAIL_USER)



# --- HJELPEFUNKSJONER ---



def make_session():

session = requests.Session()

retry = Retry(

total=3,

backoff_factor=1,

status_forcelist=[429, 500, 502, 503, 504],

allowed_methods=["GET"],

)

adapter = HTTPAdapter(max_retries=retry)

session.mount("http://", adapter)

session.mount("https://", adapter)

session.headers.update({"User-Agent": USER_AGENT})

return session



def strip_html(html: str) -> str:

# fjern script/style

html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)

# fjern tagger

text = re.sub(r"(?s)<[^>]+>", " ", html)

# unescape &nbsp; etc.

text = re.sub(r"&nbsp;", " ", text)

# normaliser whitespace

text = re.sub(r"\s+", " ", text)

return text.strip()



def sha256(text: str) -> str:

return hashlib.sha256(text.encode("utf-8")).hexdigest()



def load_cache():

if not os.path.exists(CACHE_FILE):

return {}

with open(CACHE_FILE, "r", encoding="utf-8") as f:

return json.load(f)



def save_cache(cache: dict):

with open(CACHE_FILE, "w", encoding="utf-8") as f:

json.dump(cache, f, ensure_ascii=False, indent=2)



def unified_diff(old: str, new: str, context=5) -> str:

old_lines = old.split()

new_lines = new.split()

diff = difflib.unified_diff(old_lines, new_lines, lineterm="", n=context)

# begrens lengde

diff_list = list(diff)

if len(diff_list) > 400:

diff_list = diff_list[:400] + ["...", "(diff trunkert)"]

return "\n".join(diff_list)



# --- KJERNEFUNKSJONER ---



def sjekk_endringer():

cache = load_cache()

sess = make_session()

funn = []



for navn, url in LOVER.items():

print(f"Sjekker {navn} ...")

try:

r = sess.get(url, timeout=12)

r.raise_for_status()

except Exception as e:

print(f" ⚠️ Klarte ikke å hente: {e}")

continue



raw_html = r.text

clean_text = strip_html(raw_html)

current_hash = sha256(clean_text)



prev_entry = cache.get(navn, {})

prev_hash = prev_entry.get("hash")

prev_text = prev_entry.get("text", "")



# lagre ny versjon i cache uansett

cache[navn] = {"hash": current_hash, "text": clean_text, "url": url}



if not prev_hash:

print(" ✅ Førstegangslagret.")

continue



if current_hash == prev_hash:

print(" ✅ Uendret.")

continue



# beregn endringsgrad på tekst

matcher = difflib.SequenceMatcher(None, prev_text, clean_text)

likhet = matcher.ratio()

endring_pct = (1 - likhet) * 100



if endring_pct >= THRESHOLD:

print(f" 🔴 Endring oppdaget ({endring_pct:.2f}%)")

diff_excerpt = unified_diff(prev_text, clean_text, context=4)

funn.append(

{

"navn": navn,

"url": url,

"prosent": endring_pct,

"diff": diff_excerpt,

}

)

else:

print(f" ⚪ Småendring ({endring_pct:.2f}%), ignorerer.")



save_cache(cache)

return funn



def send_epost(funn):

if not funn:

print("\n✅ Ingen endringer funnet.")

return

if not (EMAIL_USER and EMAIL_PASS and EMAIL_TO):

print("⚠️ Mangler e-postkonfig (EMAIL_USER/EMAIL_PASS).")

return



funn = sorted(funn, key=lambda x: x["prosent"], reverse=True)

tekst = []

tekst.append("🚨 LOVENDRINGER OPPDAGET\n")

tekst.append(f"Antall lover med endringer: {len(funn)}\n")

tekst.append("=" * 60 + "\n")



for f in funn:

tekst.append(f"🔴 {f['navn']} ({f['prosent']:.2f}%)")

tekst.append(f"Lenke: {f['url']}")

tekst.append("Diff-utdrag:\n" + f["diff"] + "\n")

tekst.append("-" * 60 + "\n")



body = "\n".join(tekst)



msg = MIMEText(body, "plain", "utf-8")

msg["Subject"] = Header(f"LovRadar: {len(funn)} endring(er) oppdaget", "utf-8")

msg["From"] = EMAIL_USER

msg["To"] = EMAIL_TO



try:

with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:

server.login(EMAIL_USER, EMAIL_PASS)

server.send_message(msg)

print(f"\n📧 E-post sendt til {EMAIL_TO} med {len(funn)} endring(er).")

except Exception as e:

print(f"❌ Feil ved sending av e-post: {e}")



if __name__ == "__main__":

funn = sjekk_endringer()

send_epost(funn)


