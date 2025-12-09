import requests
import tarfile
import io

URL_LOVER = "https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2"

HEADERS = {"User-Agent": "LovRadar/1.0"}

print("Laster ned lover...")
response = requests.get(URL_LOVER, headers=HEADERS, timeout=300)
print(f"Lastet ned {len(response.content) / 1024 / 1024:.1f} MB")

fil = io.BytesIO(response.content)

with tarfile.open(fileobj=fil, mode="r:bz2") as tar:
    filer = tar.getnames()
    print(f"Totalt {len(filer)} filer")
    print("")
    print("FORSTE 20 FILNAVN:")
    for i, f in enumerate(filer[:20]):
        print(f"  {f}")
