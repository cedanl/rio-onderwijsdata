"""Geplande broncontrole: vergelijk de bron met de catalogus en het vorige manifest.

Gebruik:
    uv run python catalogus/broncontrole.py [--manifest catalogus/bronmanifest.json] [--schrijf]

Wat het doet (en wat niet):
- **DUO CKAN**: inventaris van datasets (naam, ``metadata_modified``, resource-IDs, hash van
  ``notes``). Verwijderde/verplaatste datasets, nieuwe datasets en gewijzigde resources of
  beschrijvingen worden als *review* gemeld. Dit leest alleen CKAN; het past de catalogus niet aan.
- **RIO-contract**: hash van de meegeleverde OpenAPI-spec tegen het filtercontract (offline).
  Een nieuwe spec die het contract niet meer dekt is een reviewmelding.
- RIO live, SBB, ROA, UWV en Inspectie worden nog **niet** gecontroleerd.

Het manifest houdt vier tijdstempels apart: ``laatste_succesvolle_controle`` (wanneer wij
keken), ``bron_laatst_gewijzigd`` (wat de bron zelf meldt), ``catalogus_gebouwd`` (wanneer de
catalogusdata is gebouwd) en de dekking van de gecontroleerde inventaris (``aantal``). Een
ongewijzigde bron geeft geen melding, ongeacht de leeftijd van de laatste commit.

Exitcodes: 0 = niets te melden, 10 = review nodig, 1 = controle mislukt. Bij mislukken wordt het
manifest niet overschreven (laatst-goede snapshot blijft).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "riodata" / "data"
MANIFEST = Path(__file__).resolve().parent / "bronmanifest.json"
CKAN = "https://onderwijsdata.duo.nl/api/3/action/package_search"
SCHEMA_VERSIE = 1


def _sha(tekst: str) -> str:
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()


def duo_inventaris(pkgs: list[dict]) -> dict:
    """Maak een inventaris van CKAN-packages (zonder volatiele velden)."""
    items = {
        p["name"]: {
            "metadata_modified": p.get("metadata_modified"),
            "notes_sha256": _sha(p.get("notes") or ""),
            "resources": sorted(r.get("id", "") for r in p.get("resources", [])),
        }
        for p in pkgs
    }
    gewijzigd = [v["metadata_modified"] for v in items.values() if v["metadata_modified"]]
    return {
        "aantal": len(items),
        "bron_laatst_gewijzigd": max(gewijzigd) if gewijzigd else None,
        "inhoud_sha256": _sha(json.dumps(items, sort_keys=True)),
        "items": items,
    }


def rio_contract_inventaris(spec_pad: Path, contract_pad: Path) -> dict:
    spec_sha = hashlib.sha256(spec_pad.read_bytes()).hexdigest()
    contract = json.loads(contract_pad.read_text(encoding="utf-8"))
    return {
        "aantal": len(contract["resources"]),
        "bron_laatst_gewijzigd": None,
        "inhoud_sha256": spec_sha,
        "items": {"spec_sha256": spec_sha, "contract_spec_sha256": contract["spec_sha256"]},
    }


def vergelijk_items(oud: dict, nieuw: dict) -> dict:
    """Verschil tussen twee ``items``-dicts: nieuw, verwijderd en gewijzigd (op sleutel)."""
    return {
        "nieuw": sorted(set(nieuw) - set(oud)),
        "verwijderd": sorted(set(oud) - set(nieuw)),
        "gewijzigd": sorted(k for k in set(oud) & set(nieuw) if oud[k] != nieuw[k]),
    }


def meldingen_duo(oud: dict | None, nieuw: dict, catalogus_ids: set[str]) -> list[str]:
    out = []
    bron_ids = set(nieuw["items"])
    for i in sorted(bron_ids - catalogus_ids):
        out.append(f"DUO: nieuwe dataset in CKAN die niet in de catalogus staat: {i}")
    for i in sorted(catalogus_ids - bron_ids):
        out.append(f"DUO: catalogusdataset niet meer in CKAN (verwijderd of verplaatst): {i}")
    if oud:
        d = vergelijk_items(oud["items"], nieuw["items"])
        for i in d["gewijzigd"]:
            o, n = oud["items"][i], nieuw["items"][i]
            wat = []
            if o["resources"] != n["resources"]:
                wat.append("resources")
            if o["notes_sha256"] != n["notes_sha256"]:
                wat.append("beschrijving")
            out.append(f"DUO: {i} gewijzigd ({', '.join(wat) or 'metadata'}; was {o['metadata_modified']}, nu {n['metadata_modified']})")
    return out


def meldingen_rio(nieuw: dict) -> list[str]:
    i = nieuw["items"]
    if i["spec_sha256"] != i["contract_spec_sha256"]:
        return ["RIO: de OpenAPI-spec wijkt af van het filtercontract; draai catalogus/genereer_filtercontract.py"]
    return []


def fetch_duo(client) -> list[dict]:
    pkgs, start = [], 0
    while True:
        r = client.get(CKAN, params={"rows": 100, "start": start}, timeout=60)
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            raise RuntimeError(f"CKAN fout: {body.get('error')}")
        batch = body["result"]["results"]
        pkgs += batch
        start += len(batch)
        if not batch or start >= body["result"]["count"]:
            return pkgs


def controleer(oud_manifest: dict | None, *, duo_pkgs: list[dict], catalogus_ids: set[str],
               spec_pad: Path = ROOT / "RIO_LOD_API_v2.yml",
               contract_pad: Path = DATA / "rio_filtercontract.json",
               nu: dt.datetime | None = None, catalogus_gebouwd: str | None = None) -> tuple[dict, list[str]]:
    """Bouw het nieuwe manifest en de reviewmeldingen. Pure functie, zonder netwerk."""
    nu = nu or dt.datetime.now(dt.timezone.utc)
    oud = (oud_manifest or {}).get("bronnen", {})
    duo = duo_inventaris(duo_pkgs)
    bronnen = {"duo_ckan": duo}
    meldingen = meldingen_duo(oud.get("duo_ckan"), duo, catalogus_ids)
    if contract_pad.exists() and spec_pad.exists():
        rio = rio_contract_inventaris(spec_pad, contract_pad)
        bronnen["rio_contract"] = rio
        meldingen += meldingen_rio(rio)
    stempel = nu.isoformat(timespec="seconds")
    for b in bronnen.values():
        b["laatste_succesvolle_controle"] = stempel
    manifest = {
        "schema_versie": SCHEMA_VERSIE,
        "catalogus_gebouwd": catalogus_gebouwd or (oud_manifest or {}).get("catalogus_gebouwd"),
        "niet_gecontroleerd": ["rio_live", "sbb", "roa", "uwv", "inspectie"],
        "bronnen": bronnen,
    }
    return manifest, meldingen


def _catalogus_ids() -> set[str]:
    return {r["_ckan_id"] for r in json.loads((DATA / "duo_resources.json").read_text(encoding="utf-8"))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--schrijf", action="store_true", help="schrijf het manifest na een geslaagde controle")
    args = ap.parse_args(argv)
    import httpx

    oud = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else None
    try:
        with httpx.Client() as client:
            pkgs = fetch_duo(client)
        manifest, meldingen = controleer(oud, duo_pkgs=pkgs, catalogus_ids=_catalogus_ids())
    except Exception as e:  # netwerk of CKAN-fout: manifest blijft zoals het was
        print(f"Controle mislukt, manifest ongewijzigd: {e}", file=sys.stderr)
        return 1
    if args.schrijf:
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for m in meldingen:
        print(m)
    return 10 if meldingen else 0


if __name__ == "__main__":
    sys.exit(main())
