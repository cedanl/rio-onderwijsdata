"""Genereer het RIO-filtercontract uit de OpenAPI-spec.

Schrijft ``src/riodata/data/rio_filtercontract.json`` en zet de queryfilters uit de spec in
``filters`` van de RIO-catalogusbestanden (bestaande filters blijven staan, ontbrekende
worden achteraan toegevoegd).

Gebruik:
    uv run --extra catalogus python catalogus/genereer_filtercontract.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "RIO_LOD_API_v2.yml"
DATA = ROOT / "src" / "riodata" / "data"
CONTRACT = DATA / "rio_filtercontract.json"
CATALOGI = ("rio_resources.json", "rio_resources_ai.json", "rio_resources_enriched.json")

PAGINERING = ("page", "pageSize", "sort")


def _param(spec: dict, p: dict) -> dict:
    if "$ref" in p:
        p = spec["components"]["parameters"][p["$ref"].split("/")[-1]]
    schema = p.get("schema", {})
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
    return {
        "naam": p["name"],
        "in": p.get("in"),
        "type": schema.get("type"),
        "format": schema.get("format"),
        "enum": schema.get("enum"),
        "beschrijving": p.get("description"),
    }


def bouw_contract(spec_pad: Path = SPEC) -> dict:
    raw = spec_pad.read_bytes()
    spec = yaml.safe_load(raw)
    resources = {}
    for pad, item in spec["paths"].items():
        get = item.get("get")
        if not get or "{" in pad:
            continue
        params = [_param(spec, p) for p in get.get("parameters", [])]
        resources[pad.strip("/")] = {
            "filters": [{**p, "bron": "openapi"} for p in params
                        if p["in"] == "query" and p["naam"] not in PAGINERING],
            "paginering": [p["naam"] for p in params if p["naam"] in PAGINERING],
            # In de spec heeft ``sort`` geen schema: waarden en richting zijn dus onbekend.
            "sort_schema_in_spec": any(p["naam"] == "sort" and p["type"] for p in params),
        }
    # Filters die de catalogus noemt maar de spec niet kent: niet weggooien, wel markeren.
    for r in json.loads((DATA / "rio_resources_ai.json").read_text(encoding="utf-8")):
        res = resources.get(r["_rio_resource"])
        if res is None:
            continue
        in_spec = {f["naam"] for f in res["filters"]}
        res["catalogus_zonder_spec"] = [
            {"naam": n, "status": "niet in spec; live ondersteuning niet vastgesteld"}
            for n in r.get("filters", []) if n not in in_spec
        ]
    return {
        "spec_versie": spec["info"].get("version"),
        "spec_sha256": hashlib.sha256(raw).hexdigest(),
        "resources": resources,
    }


def _vervang_filters(tekst: str, resource: str, nieuw: list[str]) -> str:
    """Vervang de ``filters``-lijst van één record en behoud de opmaak van het bestand."""
    anker = tekst.index(f'"_rio_resource": "{resource}"')
    begin = tekst.rindex('"filters": [', 0, anker)
    eind = tekst.index("]", begin) + 1
    oud = tekst[begin:eind]
    if "\n" in oud:
        regel_begin = tekst.rindex("\n", 0, begin) + 1
        inspring = " " * (begin - regel_begin)
        items = ",\n".join(f"{inspring}  {json.dumps(n)}" for n in nieuw)
        vervanging = f'"filters": [\n{items}\n{inspring}]'
    else:
        vervanging = '"filters": ' + json.dumps(nieuw, ensure_ascii=False)
    return tekst[:begin] + vervanging + tekst[eind:]


def sync_catalogus(contract: dict, pad: Path) -> int:
    """Voeg ontbrekende spec-filters toe aan ``filters``; de rest van het bestand blijft gelijk."""
    tekst = pad.read_text(encoding="utf-8")
    gewijzigd = 0
    for r in json.loads(tekst):
        spec_res = contract["resources"].get(r["_rio_resource"])
        if spec_res is None:
            continue
        huidig = r.get("filters", [])
        nieuw = huidig + [f["naam"] for f in spec_res["filters"] if f["naam"] not in huidig]
        if nieuw != huidig:
            tekst = _vervang_filters(tekst, r["_rio_resource"], nieuw)
            gewijzigd += 1
    pad.write_text(tekst, encoding="utf-8")
    return gewijzigd


def main() -> None:
    contract = bouw_contract()
    CONTRACT.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{CONTRACT.name}: spec {contract['spec_versie']}, {len(contract['resources'])} resources")
    for naam in CATALOGI:
        print(f"{naam}: {sync_catalogus(contract, DATA / naam)} records bijgewerkt")


if __name__ == "__main__":
    main()
