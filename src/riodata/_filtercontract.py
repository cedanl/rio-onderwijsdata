"""RIO-filtercontract: queryparameters per resource, afgeleid uit de OpenAPI-spec.

Het contract (``data/rio_filtercontract.json``) wordt gegenereerd door
``catalogus/genereer_filtercontract.py``. Enums, types en formats komen uit de spec,
niet uit voorbeeldrecords. Filters die wel in de catalogus staan maar niet in de spec
(``datumGeldigOp`` op cohorten) staan onder ``catalogus_zonder_spec``: live ondersteuning
is daarvoor niet vastgesteld.
"""
from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from importlib.resources import files

# Sectorvoorvoegsel in de enumwaarden van het type-filter. Alleen wat de spec zelf zegt:
# RIO kent ``HO*`` als één sector; hbo en wo zijn daarin niet te onderscheiden.
_SECTOREN = {"mbo": "MBO", "ho": "HO"}
_SECTOR_RE = {k: re.compile(rf"^(AANGEBODEN)?{v}") for k, v in _SECTOREN.items()}


@lru_cache(maxsize=1)
def filtercontract() -> dict:
    """Het volledige contract: ``spec_versie``, ``spec_sha256`` en ``resources``."""
    return json.loads(files("riodata.data").joinpath("rio_filtercontract.json").read_text(encoding="utf-8"))


def _resource(resource: str) -> dict:
    res = filtercontract()["resources"]
    if resource not in res:
        raise ValueError(_onbekend("resource", resource, list(res)))
    return res[resource]


def _onbekend(soort: str, waarde: str, opties: list[str]) -> str:
    dichtbij = difflib.get_close_matches(str(waarde), opties, n=3, cutoff=0.5)
    hint = f" Bedoelde je: {', '.join(dichtbij)}?" if dichtbij else ""
    return f"Onbekend {soort} '{waarde}'.{hint} Geldig: {', '.join(opties)}"


def filters(resource: str) -> dict[str, dict]:
    """Filters van een resource als ``{naam: {type, format, enum, ...}}``."""
    return {f["naam"]: f for f in _resource(resource)["filters"]}


def typewaarden(resource: str, sector: str, filter_naam: str | None = None) -> list[str]:
    """Waarden van het type-filter die bij een sector horen, volgens de spec-enum.

    ``sector``: ``"mbo"`` of ``"ho"``. ``"hbo"`` en ``"wo"`` geven een ``ValueError``: het
    RIO-typefilter onderscheidt die niet, dus een sectorlabel hbo/wo mag hieruit niet geraden
    worden (gebruik CROHO of DUO-data voor die splitsing).
    """
    sector = sector.lower()
    if sector in ("hbo", "wo"):
        raise ValueError(
            f"RIO-typefilters onderscheiden '{sector}' niet: de spec kent alleen 'HO' (hbo en wo samen). "
            "Gebruik 'ho', of een bron met die splitsing (CROHO, DUO)."
        )
    if sector not in _SECTOR_RE:
        raise ValueError(_onbekend("sector", sector, [*_SECTOR_RE, "hbo", "wo"]))
    kandidaten = [
        f for f in _resource(resource)["filters"]
        if f["enum"] and (filter_naam is None or f["naam"] == filter_naam)
        and f["naam"].lower().endswith("type")
    ]
    if not kandidaten:
        raise ValueError(f"Resource '{resource}' heeft geen type-filter met vaste waarden.")
    return [w for w in kandidaten[0]["enum"] if _SECTOR_RE[sector].match(w)]


def valideer_filters(resource: str, params: dict) -> list[dict]:
    """Toets filterargumenten tegen het contract.

    Geeft een lijst problemen terug (leeg = geldig). Elk probleem heeft ``filter``, ``probleem``
    en ``herstel`` (geldige opties of een voorstel). Filters met bron ``catalogus_zonder_spec``
    worden niet geweigerd maar krijgen probleem ``waarschuwing``.
    """
    bekend = filters(resource)
    zonder_spec = {f["naam"]: f["status"] for f in _resource(resource).get("catalogus_zonder_spec", [])}
    problemen = []
    for naam, waarde in params.items():
        if naam in _resource(resource)["paginering"]:
            continue
        f = bekend.get(naam)
        if f is None and naam in zonder_spec:
            problemen.append({"filter": naam, "probleem": "waarschuwing", "herstel": zonder_spec[naam]})
            continue
        if f is None:
            problemen.append({"filter": naam, "probleem": "onbekend filter",
                              "herstel": _onbekend("filter", naam, list(bekend))})
            continue
        if f["enum"] and waarde not in f["enum"]:
            problemen.append({"filter": naam, "probleem": "ongeldige waarde",
                              "herstel": _onbekend("waarde", waarde, f["enum"])})
        elif f["format"] == "date" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(waarde)):
            problemen.append({"filter": naam, "probleem": "ongeldige datum",
                              "herstel": "Gebruik formaat YYYY-MM-DD"})
        elif f["format"] == "uuid" and not re.fullmatch(r"[0-9a-fA-F-]{36}", str(waarde)):
            problemen.append({"filter": naam, "probleem": "ongeldige uuid",
                              "herstel": "Gebruik een UUID, bijv. uit een eerder opgehaald record"})
    return problemen
