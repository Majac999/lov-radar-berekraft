"""
Dette er vår nye, smarte Arbeidsrett-bot.
Versjon 2: Leser CSV-filen.
"""
from __future__ import annotations

import os
from typing import AsyncIterable

import fastapi_poe as fp
from modal import App, Image, asgi_app
import pandas as pd  # Importerer pandas

# --- DINE NØKLER ---
bot_access_key = "HiycA1BQ691yic4LpzOH3bXyqjRmK5xh"
bot_name = "Arbeidsrett"  # Pass på at dette er bot-navnet fra Poe
# ---------------------

# --- Last inn CSV-filen ---
CSV_FILENAME = "CSV_FILENAME = "kunnskapsbase.tsv"" # Filen du flyttet og ga nytt navn

script_dir = os.path.dirname(__file__)
csv_file_path = os.path.join(script_dir, CSV_FILENAME)

try:
    df_kunnskap = pd.read_csv(csv_file_path)
    df_kunnskap = df_kunnskap.fillna("") # Fyller ut tomme celler
    print(f"Vellykket: '{CSV_FILENAME}' er lastet inn.")
except FileNotFoundError:
    print(f"KRITISK FEIL: Fant ikke filen: '{CSV_FILENAME}'")
    print(f"Sjekk at filen er kopiert til mappen: {script_dir}")
    df_kunnskap = None
# ----------------------------

class SmartBot(fp.PoeBot):
    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:

        last_message = request.query[-1].content

        if df_kunnskap is not None and not df_kunnskap.empty:
            try:
                # Søker etter en nøyaktig match i 'bruker_utsagn'-kolonnen
                match = df_kunnskap[df_kunnskap['bruker_utsagn'].str.lower() == last_message.lower()]

                if not match.empty:
                    # Henter data fra den første matchen
                    intent = match.iloc[0]['intent_type']
                    begrep = match.iloc[0]['normalisert_begrep']
                    mapping = match.iloc[0]['forventet_mapping']
                    dialog_nivaa = match.iloc[0]['dialog_nivaa']
                    oppfolging = match.iloc[0]['oppfoelgingsspoersmaal_1']

                    if dialog_nivaa == 1 and oppfolging:
                        # Hvis dialog_nivaa er 1, still oppfølgingsspørsmålet
                        yield fp.PartialResponse(text=oppfolging)
                    else:
                        # Hvis dialog_nivaa er 0, gi et direkte svar
                        svar_tekst = f"Fant match!\nTema: {begrep}\nMapping: {mapping}"
                        yield fp.PartialResponse(text=svar_tekst)
                else:
                    yield fp.PartialResponse(text=f"Fant ingen nøyaktig match for: '{last_message}'")
            except KeyError as e:
                yield fp.PartialResponse(text=f"Feil: CSV-filen mangler en nøkkelkolonne: {e}")
        else:
            yield fp.PartialResponse(text="Feil: Kunnskapsbasen (CSV) er ikke lastet.")


# Alle bibliotekene koden vår trenger
REQUIREMENTS = ["fastapi-poe", "pandas"]
image = (
    Image.debian_slim()
    .pip_install(*REQUIREMENTS)
    .env({"POE_ACCESS_KEY": bot_access_key}) # DENNE ER NÅ RIKTIG
    .mount(modal.Mount.from_local_dir(
        local_path=".", 
        remote_path="/root"
    ))
)
app = App("arbeidsrett-bot-poe")


@app.function(image=image)
@asgi_app()
def fastapi_app():
    bot = SmartBot() 
    app = fp.make_app(
        bot,
        access_key=bot_access_key,
        bot_name=bot_name,
        allow_without_key=not (bot_access_key and bot_name),
    )
    return app

