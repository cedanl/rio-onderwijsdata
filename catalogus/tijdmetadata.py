"""Leg tijdmetadata van DUO-datasets vast als aparte, herleidbare claims (`_tijd`).

Alleen datasets waarvan de CKAN-beschrijving (``package_show``) is gelezen staan hier; elke claim
heeft een bronzin of -veld. Waarnemingsperiode, prognosehorizon, editie, peildatum en verversing zijn
aparte velden, en tegenstrijdige bronclaims blijven naast elkaar staan met reviewstatus.

Gebruik:
    uv run python catalogus/tijdmetadata.py

Uitbreiden: lees de ``notes`` en ``extras`` van een dataset, voeg een invoer toe aan ``TIJD`` en draai
het script opnieuw. Geen invoer betekent: niet gecontroleerd (niet: geen tijdmetadata).
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "src" / "riodata" / "data"
BESTANDEN = ("duo_resources.json", "duo_resources_enriched.json")
OPGEHAALD = "2026-10-05"
CKAN = "https://onderwijsdata.duo.nl/api/3/action/package_show?id="

TIJD: dict[str, dict] = {
    "studentprognoses-mbo-per-instelling": {
        "periode": "2021-2040",
        "frequentie": "Twee keer per jaar (februari/maart en april/mei)",
        "_tijd": {
            "bron": {"url": CKAN + "studentprognoses-mbo-per-instelling",
                     "metadata_modified": "2026-04-29T12:20:34", "opgehaald_op": OPGEHAALD},
            "periode": {
                "waarde": "2021-2040",
                "soort": "prognose",
                "bronzin": "Deze gegevens hebben betrekking op de periode 2021-2040",
                "opmerking": "De notes spreken van historische studentenaantallen en een prognose binnen deze "
                             "periode; de grens tussen historische en voorspelde jaren staat niet in de metadata.",
            },
            "editie": {
                "publicatiedatum": "2026-04-29",
                "versies": "versie 1 = publicatie februari/maart, versie 2 = publicatie april/mei (kenmerk in het bestand)",
                "bronzin": "De publicatiedatum is 29-04-2026.",
            },
            "peildatum": {
                "bronnen": ["1-cijfer mbo: 2025-10-01", "Bevolkingsaantallen CBS: 2025-01-01"],
                "bronzin": "1-cijfer mbo (peildatum 01-10-2025), Bevolkingsaantallen CBS (peildatum 01-01-2025)",
            },
            "verversing": {
                "waarde": "twee keer per jaar",
                "bronzin": "de publicatie van de gegevens vindt twee keer per jaar plaats in februari/maart en in april/mei",
            },
            "claims_in_conflict": [
                {"veld": "verversing", "waarde": "jaarlijks",
                 "bron": "CKAN extras.frequency = .../frequency/ANNUAL",
                 "reviewstatus": "conflict: notes zeggen twee keer per jaar; de notes zijn gevolgd"},
            ],
            "eerdere_catalogusclaims": [
                {"veld": "periode", "waarde": "2021-2030", "reviewstatus": "onjuist volgens bron (2021-2040)"},
                {"veld": "frequentie", "waarde": "Jaarlijks", "reviewstatus": "conflict met notes (twee keer per jaar)"},
            ],
            "reviewstatus": f"bronverificatie {OPGEHAALD}",
        },
    },
    "mbo_opleidingsaanbod": {
        "periode": "Actueel aanbod (open cohorten met aanmeldperiode die nog loopt), dagelijks geactualiseerd",
        "frequentie": "Dagelijks",
        "_tijd": {
            "bron": {"url": CKAN + "mbo_opleidingsaanbod",
                     "metadata_modified": "2026-10-03T02:35:06", "opgehaald_op": OPGEHAALD},
            "periode": {
                "waarde": None,
                "soort": "actueel overzicht (geen waarnemingsperiode)",
                "bronzin": "de actuele aangeboden opleidingen met de bijbehorende cohorten waarvan de status open is "
                           "en waarvan de aanmeldperiode nog niet is verstreken",
            },
            "editie": None,
            "peildatum": None,
            "verversing": {"waarde": "dagelijks", "bronzin": "Het mbo opleidingsaanbod wordt dagelijks geactualiseerd."},
            "claims_in_conflict": [],
            "eerdere_catalogusclaims": [
                {"veld": "frequentie", "waarde": "Onbekend",
                 "reviewstatus": "onvolledig: CKAN heeft geen frequency-extra, de notes (sectie Periode) wel"},
                {"veld": "periode", "waarde": "Jaarlijks bijgewerkt (zie dataset voor peilmoment)",
                 "reviewstatus": "onjuist volgens bron (dagelijks geactualiseerd)"},
            ],
            "reviewstatus": f"bronverificatie {OPGEHAALD}",
        },
    },
}


def pas_toe(records: list[dict]) -> int:
    n = 0
    for r in records:
        t = TIJD.get(r.get("_ckan_id"))
        if not t:
            continue
        r["periode"], r["frequentie"], r["_tijd"] = t["periode"], t["frequentie"], t["_tijd"]
        n += 1
    return n


def main() -> None:
    for naam in BESTANDEN:
        pad = DATA / naam
        tekst = pad.read_text(encoding="utf-8")
        records = json.loads(tekst)
        n = pas_toe(records)
        pad.write_text(json.dumps(records, ensure_ascii=False, indent=2) + ("\n" if tekst.endswith("\n") else ""),
                       encoding="utf-8")
        print(f"{naam}: {n} records bijgewerkt")


if __name__ == "__main__":
    main()
