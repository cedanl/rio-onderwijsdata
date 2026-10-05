"""CREBO-lijst van SBB: genormaliseerde tabel, editie-cache en deterministische lookup.

Bouwt voort op ``sbb.resources("crebolijst")``; de bestaande ``sbb.load()`` blijft werken.

    from riodata import crebo

    crebo.ververs("codelijst_2025_april")      # download, valideer en cache (netwerk)
    r = crebo.zoek("25604")                    # 'latest' = nieuwste gevalideerde editie in de cache
    r["status"]                                # "found" | "not_found" | "ambiguous"

Vereist ``openpyxl`` (``pip install 'riodata[sbb]'``).

Ontwerpkeuzes:
- CREBO-codes blijven strings. Een cel die in de XLSX als getal is opgeslagen heeft de
  voorloopnullen al verloren; die worden niet geraden of aangevuld.
- Ontbrekende waarden worden ``None``, rijen blijven behouden. Dubbele codes (over cohorten)
  blijven bestaan; de lookup geeft ze terug in plaats van de eerste.
- Bronkolommen blijven in ``bron`` bewaard. Kolomnamen worden via alias-lijsten (hieronder)
  herkend; herkent een lijst de verplichte kolommen niet, dan volgt een ``CreboSchemaFout``
  met de werkelijke kolomnamen, geen gok.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Genormaliseerde kolomnaam -> herkende bronkoppen (lowercase, zonder spaties/streepjes).
KOLOM_ALIASSEN: dict[str, tuple[str, ...]] = {
    "crebo": ("crebo", "crebocode", "creboopleidingscode", "opleidingscode"),
    "naam": ("naam", "opleidingsnaam", "kwalificatienaam", "omschrijving", "naamkwalificatie"),
    "niveau": ("niveau", "kwalificatieniveau", "mboniveau"),
    "geldig_van": ("ingangsdatum", "geldigvanaf", "geldigvan", "begindatum", "startdatum"),
    "geldig_tot": ("einddatum", "geldigtot", "geldigtm", "vervaldatum", "uitgangsdatum"),
}
VERPLICHT = ("crebo", "naam")
MIN_RIJEN = 100  # een CREBO-lijst met minder rijen is een afgekapt of verkeerd bestand
XLSX_CONTENTTYPES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
)


class CreboFout(Exception):
    """Basis voor alle CREBO-loaderfouten."""


class CreboSchemaFout(CreboFout):
    """Het bestand heeft niet de verwachte kolommen of omvang."""


class CreboEditieOnbekend(CreboFout):
    """Geen (gevalideerde) editie beschikbaar."""


@dataclass(frozen=True)
class CreboLijst:
    editie: str
    rijen: tuple[dict, ...]
    kolommen: tuple[str, ...]
    bron_url: str | None = None
    sha256: str | None = None
    gecontroleerd_op: str | None = None
    kolomtoewijzing: dict = field(default_factory=dict)


def _norm(kop) -> str:
    return re.sub(r"[\s_\-./]", "", str(kop or "").lower())


def _toewijzing(koppen: list[str]) -> dict[str, str]:
    """Wijs genormaliseerde namen toe aan bronkoppen; bij dubbelzinnigheid een fout."""
    out: dict[str, str] = {}
    for doel, aliassen in KOLOM_ALIASSEN.items():
        hits = [k for k in koppen if _norm(k) in aliassen]
        if len(hits) > 1:
            raise CreboSchemaFout(f"Kolom '{doel}' is dubbelzinnig: {hits}")
        if hits:
            out[doel] = hits[0]
    ontbreekt = [d for d in VERPLICHT if d not in out]
    if ontbreekt:
        raise CreboSchemaFout(f"Verplichte kolommen {ontbreekt} niet gevonden. Aanwezige kolommen: {koppen}")
    return out


def _tekst(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # 25604.0 uit een numerieke cel
    s = str(v).strip()
    return s or None


def _datum(v) -> str | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return s  # niet te lezen: ruwe tekst behouden, niet weggooien


def parse_xlsx(content: bytes, editie: str, *, bron_url: str | None = None, sheet: str | None = None) -> CreboLijst:
    """Lees een CREBO-XLSX naar een genormaliseerde tabel (zonder omvangscontrole)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError("Installeer openpyxl: pip install 'riodata[sbb]'")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:  # zip/xml-fout in het bestand zelf
        raise CreboSchemaFout(f"Geen leesbaar XLSX-bestand: {e}") from e
    ws = wb[sheet] if sheet else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    koppen: list[str] = []
    for rij in it:  # eerste niet-lege rij is de kop
        if any(c is not None and str(c).strip() for c in rij):
            koppen = [str(c).strip() if c is not None else "" for c in rij]
            break
    if not koppen:
        raise CreboSchemaFout("Bestand bevat geen kopregel")
    toe = _toewijzing(koppen)
    pos = {k: i for i, k in enumerate(koppen)}
    rijen = []
    for rij in it:
        if not any(c is not None and str(c).strip() for c in rij):
            continue
        bron = {k: (rij[i] if i < len(rij) else None) for k, i in pos.items() if k}
        rec = {
            "crebo": _tekst(bron.get(toe["crebo"])),
            "naam": _tekst(bron.get(toe["naam"])),
            "niveau": _tekst(bron.get(toe["niveau"])) if "niveau" in toe else None,
            "geldig_van": _datum(bron.get(toe["geldig_van"])) if "geldig_van" in toe else None,
            "geldig_tot": _datum(bron.get(toe["geldig_tot"])) if "geldig_tot" in toe else None,
            "editie": editie,
            "bron": {k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in bron.items()},
        }
        rijen.append(rec)
    return CreboLijst(
        editie=editie, rijen=tuple(rijen), kolommen=tuple(k for k in koppen if k),
        bron_url=bron_url, sha256=hashlib.sha256(content).hexdigest(), kolomtoewijzing=toe,
    )


def valideer_download(content: bytes, content_type: str | None, lijst: CreboLijst) -> list[str]:
    """Controleer contenttype, bestandssignatuur, kolommen en omvang. Leeg = goedgekeurd."""
    problemen = []
    if content_type and content_type.split(";")[0].strip().lower() not in XLSX_CONTENTTYPES:
        problemen.append(f"contenttype '{content_type}' is geen XLSX")
    if not content.startswith(b"PK"):
        problemen.append("bestand is geen zip/XLSX (verkeerde signatuur)")
    if len(lijst.rijen) < MIN_RIJEN:
        problemen.append(f"slechts {len(lijst.rijen)} rijen (minimaal {MIN_RIJEN} verwacht)")
    if not any(r["crebo"] for r in lijst.rijen):
        problemen.append("geen enkele CREBO-code gevonden")
    return problemen


# ── editie-cache ─────────────────────────────────────────────────────────────

def cache_dir() -> Path:
    return Path(os.environ.get("RIODATA_CACHE", Path.home() / ".cache" / "riodata")) / "crebo"


def _manifest_pad() -> Path:
    return cache_dir() / "manifest.json"


def manifest() -> dict:
    """``{editie: {bron_url, sha256, bytes, rijen, gecontroleerd_op}}`` van gevalideerde edities."""
    try:
        return json.loads(_manifest_pad().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _bekende_edities() -> dict[str, str]:
    from . import sbb
    return {r["naam"]: r["url"] for r in sbb.resources("crebolijst")}


def ververs(editie: str, *, client=None) -> CreboLijst:
    """Download een bekende editie, valideer die en zet haar in de cache.

    Een editie die de validatie niet haalt wordt niet in het manifest opgenomen en dus
    nooit ``latest``. Gooit ``CreboSchemaFout`` met de redenen.
    """
    import httpx
    bekend = _bekende_edities()
    if editie not in bekend:
        raise CreboEditieOnbekend(f"Onbekende editie '{editie}'. Bekend: {sorted(bekend)}")
    url = bekend[editie]
    r = (client or httpx).get(url, timeout=60, follow_redirects=True)
    r.raise_for_status()
    lijst = parse_xlsx(r.content, editie, bron_url=url)
    problemen = valideer_download(r.content, r.headers.get("content-type"), lijst)
    if problemen:
        raise CreboSchemaFout(f"Editie '{editie}' afgekeurd: " + "; ".join(problemen))
    return _bewaar(lijst, r.content)


def _bewaar(lijst: CreboLijst, content: bytes) -> CreboLijst:
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{lijst.editie}.xlsx").write_bytes(content)
    nu = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    m = manifest()
    m[lijst.editie] = {"bron_url": lijst.bron_url, "sha256": lijst.sha256, "bytes": len(content),
                       "rijen": len(lijst.rijen), "gecontroleerd_op": nu}
    _manifest_pad().write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return CreboLijst(**{**lijst.__dict__, "gecontroleerd_op": nu})


def laad(editie: str = "latest") -> CreboLijst:
    """Laad een gecachete, gevalideerde editie.

    ``latest`` is de editie met de laatste ``gecontroleerd_op`` in het manifest. Is er geen
    gevalideerde editie, dan volgt een fout: er wordt niet teruggevallen op een ingebakken lijst.
    De checksum van het cachebestand wordt bij het laden opnieuw gecontroleerd.
    """
    m = manifest()
    if not m:
        raise CreboEditieOnbekend("Geen gevalideerde CREBO-editie in de cache. Draai crebo.ververs(<editie>) eerst.")
    if editie == "latest":
        editie = max(m, key=lambda e: m[e]["gecontroleerd_op"])
    if editie not in m:
        raise CreboEditieOnbekend(f"Editie '{editie}' niet in cache. Beschikbaar: {sorted(m)}")
    content = (cache_dir() / f"{editie}.xlsx").read_bytes()
    if hashlib.sha256(content).hexdigest() != m[editie]["sha256"]:
        raise CreboSchemaFout(f"Cachebestand van '{editie}' komt niet overeen met de gecontroleerde checksum")
    lijst = parse_xlsx(content, editie, bron_url=m[editie]["bron_url"])
    return CreboLijst(**{**lijst.__dict__, "gecontroleerd_op": m[editie]["gecontroleerd_op"]})


# ── lookup ───────────────────────────────────────────────────────────────────

def zoek(code: str, editie: str | CreboLijst = "latest", peildatum: str | None = None) -> dict:
    """Zoek een CREBO-code deterministisch.

    Returns ``{"status", "code", "editie", "gecontroleerd_op", "matches"}`` met status:
    ``found`` (precies één geldige rij), ``not_found`` (geen) of ``ambiguous`` (meerdere
    geldige rijen: allemaal teruggegeven, nooit de eerste gekozen).

    ``peildatum`` (YYYY-MM-DD) filtert op geldigheid; een rij zonder begin- of einddatum telt als
    geldig aan die kant. Zonder peildatum tellen alle rijen met die code mee.
    """
    lijst = editie if isinstance(editie, CreboLijst) else laad(editie)
    sleutel = str(code).strip()
    matches = [r for r in lijst.rijen if r["crebo"] == sleutel]
    if peildatum:
        matches = [r for r in matches
                   if (r["geldig_van"] is None or r["geldig_van"] <= peildatum)
                   and (r["geldig_tot"] is None or r["geldig_tot"] >= peildatum)]
    status = "not_found" if not matches else "found" if len(matches) == 1 else "ambiguous"
    return {"status": status, "code": sleutel, "editie": lijst.editie,
            "gecontroleerd_op": lijst.gecontroleerd_op, "peildatum": peildatum, "matches": matches}
