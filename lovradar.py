name: LovRadar Ukentlig Sjekk

on:
  schedule:
    - cron: '0 5 * * 1'  # Kjører kl 06:00 hver MANDAG (Norsk tid)
  workflow_dispatch:     

jobs:
  kjore-radar:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Hent koden
        uses: actions/checkout@v4

      - name: Sett opp Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Installer biblioteker
        run: pip install requests

      - name: Kjør LovRadar-scriptet
        env:
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASS: ${{ secrets.EMAIL_PASS }}
        run: python lovradar.py # PEKER PÅ RIKTIG FILNAVN

      - name: Lagre cache tilbake til GitHub
        run: |
          git config --global user.name 'LovRadar Bot'
          git config --global user.email 'bot@noreply.github.com'
          git add tekst_cache/
          git diff --quiet && git diff --staged --quiet || (git commit -m "Oppdaterte lov-cache [skip ci]" && git pull --rebase origin main && git push)
