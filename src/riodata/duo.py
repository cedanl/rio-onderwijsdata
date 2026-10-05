"""DUO open data client via onderwijsdata.duo.nl (CKAN API).

onderwijsdata.duo.nl draait CKAN 2.11 — alle 57 datasets zijn beschikbaar
via een REST-API zonder authenticatie.

Gebruik:
    from riodata import duo

    # Catalogus bekijken (live van CKAN)
    datasets = duo.catalog()
    print(datasets[0])

    # Beschikbare bestanden per dataset
    duo.resources("01voins-v1")

    # Data laden als DataFrame
    df = duo.load("01voins-v1")        # eerste resource (index 0)
    df = duo.load("p01hoinges", 1)     # tweede resource
    df = duo.load("p01hoinges", "c454d7e1-b9b1-4460-b9ff-55938c85788e")  # op UUID (stabiel)
    duo.resource_schemas("p01hoinges")  # officiële kolomtypes per resource, offline
"""
from __future__ import annotations
import io
import json
from functools import lru_cache

import httpx

from .duo_notes import details_from_pkg

DUO_COLUMN_GLOSSARY: dict[str, str] = {
    "STUDIEJAAR": "Studiejaar in formaat YYYY/YYYY (bijv. 2023/2024). Loopt van 1 augustus t/m 31 juli.",
    "BRIN_NUMMER": "Basisregistratie Instellingen-nummer: unieke code voor elke onderwijsinstelling.",
    "INSTELLINGSCODE_ACTUEEL": "Actuele BRIN-code van de instelling (kan afwijken van historische code bij fusie of naamswijziging).",
    "INSTELLINGSNAAM_ACTUEEL": "Actuele naam van de onderwijsinstelling zoals geregistreerd in de Basisregistratie Instellingen.",
    "AANTAL_INGESCHREVENEN": "Aantal studenten ingeschreven op peildatum 1 oktober van het studiejaar.",
    "INSTROOM": "Eerstejaars inschrijvingen: studenten die voor het eerst staan ingeschreven in een opleiding of instelling.",
    "UITSTROOM": "Studenten die de opleiding verlaten, onderscheiden in gediplomeerd en niet-gediplomeerd uitstroom.",
    "GEDIPLOMEERDEN": "Studenten die in het studiejaar een diploma of getuigschrift hebben behaald.",
    "GESLACHT": "Geslacht van de student: MAN, VROUW of ONBEKEND.",
    "NIVEAU": "Opleidingsniveau (mbo: niveau 1 t/m 4; ho: associate degree, bachelor, master).",
    "GEMEENTENUMMER": "CBS-gemeentecode (4 cijfers), conform de gemeentelijke indeling op de peildatum.",
    "GEMEENTENAAM": "Naam van de gemeente conform CBS-gemeentelijke indeling.",
    "PROVINCIENAAM": "Naam van de provincie.",
    "ONDERDEEL": "Studierichting op hoofdniveau (bijv. TECHNIEK, ECONOMIE, GEZONDHEIDSZORG).",
    "SUBONDERDEEL": "Verfijning van ONDERDEEL op een gedetailleerder niveau.",
    "SOORT_INSTELLING": "Type instelling: reguliere instelling, bijzonder of openbaar.",
    "TYPE_HOGER_ONDERWIJS": "Opleidingstype binnen het hoger onderwijs: bachelor, master, associate degree of anders.",
    "OPLEIDINGSNAAM_ACTUEEL": "Actuele naam van de opleiding zoals geregistreerd in CROHO (ho) of CREBO (mbo).",
    "CROHO_ONDERDEEL": "Hoofdcluster van de opleiding in het Centraal Register Opleidingen Hoger Onderwijs (CROHO).",
    "CROHO_SUBONDERDEEL": "Subcluster van de opleiding in het CROHO.",
    "CREBO_CODE": "Opleidingscode in het Centraal Register Beroepsopleidingen (CREBO) voor mbo-opleidingen.",
    "CROHO_CODE": "Opleidingscode in het Centraal Register Opleidingen Hoger Onderwijs (CROHO) voor ho-opleidingen.",
    "OPLEIDINGSCODE_ACTUEEL": "Actuele opleidingscode: CREBO-code voor mbo, CROHO-code voor ho.",
    "HERKOMST": "Geografische herkomst van de student: Nederland, EU/EEA, of niet-EU/EEA.",
    "NATIONALITEIT": "Nationaliteit van de student (bijv. Nederlandse, niet-Nederlandse).",
    "LEEFTIJD": "Leeftijd van de student in jaren op 1 oktober van het studiejaar.",
    "DIPLOMAJAAR": "Jaar waarin het vooropleidingsdiploma is behaald.",
    "SOORT_DIPLOMA": "Type vooropleidingsdiploma van de student (bijv. HAVO, VWO, MBO niveau 4).",
}


# Definities die alleen gelden voor een bepaalde dataset en die de algemene definitie
# hierboven vervangen. Alleen opnemen wat uit de bron of uit de data is te onderbouwen.
DUO_COLUMN_GLOSSARY_SCOPED: dict[str, dict[str, str]] = {
    # STUDIEJAAR is hier numeriek (kolomtype 'numeriek'), geen 'YYYY/YYYY'-tekst.
    **{
        dataset: {
            "STUDIEJAAR": (
                "Startjaar van het studiejaar als geheel getal (2023 = studiejaar 2023/2024). "
                "Peildatum 1 oktober."
            ),
        }
        for dataset in ("p01hoinges", "p02ho1ejrs", "p03hoinschr")
    },
    # LEERWEG-waarden in de datastore (gecontroleerd 2026-10-05): o.a. BBL, BOLVT, EX; niet VOLTIJD/DEELTIJD/DUAAL.
    # BOL en BBL volgen de gangbare mbo-termen; VT/DT (voltijd/deeltijd) en EX (extraneus) zijn afgeleid uit
    # de code en het DUO-overzicht van leerwegen en niet in de dataset zelf gedefinieerd.
    **{
        dataset: {
            "LEERWEG": (
                "Leerwegcode zoals gepubliceerd, o.a. BBL (beroepsbegeleidende leerweg), BOLVT en BOLDT "
                "(beroepsopleidende leerweg, voltijd resp. deeltijd; afgeleid uit de code) en EX (extraneus; "
                "afgeleid). Niet VOLTIJD/DEELTIJD/DUAAL."
            ),
        }
        for dataset in (
            "mbo-studenten-per-instelling",
            "mbo-studenten-per-sectorkamer-en-leerweg",
            "instromende-mbo-studenten",
            "gediplomeerde-mbo-studenten",
        )
    },
    # OPLEIDINGSVORM in mbo_opleidingsaanbod_cohorten: KLASSIKAAL, COACHING, KLASSIKAAL_EN_ONLINE of leeg
    # (gecontroleerd 2026-10-05 in de datastore). Dit zijn geen VT/DT/DU-codes.
    "mbo_opleidingsaanbod": {
        "OPLEIDINGSVORM": (
            "Vorm waarin het cohort wordt gegeven, zoals gepubliceerd: KLASSIKAAL, COACHING of "
            "KLASSIKAAL_EN_ONLINE; kan leeg zijn. Geen VT/DT/DU-codes."
        ),
    },
}


def column_definitions(columns: list[str], dataset_id: str | None = None) -> dict[str, str]:
    """Geeft bekende definities terug voor kolomnamen uit DUO-datasets.

    Met ``dataset_id`` gaan definities die specifiek voor die dataset gelden voor op de
    algemene definitie. Zonder ``dataset_id`` is het gedrag ongewijzigd.

    Returns dict met alleen de kolommen waarvoor een definitie bekend is.
    """
    scoped = DUO_COLUMN_GLOSSARY_SCOPED.get(dataset_id, {}) if dataset_id else {}
    return {
        col: scoped.get(col, DUO_COLUMN_GLOSSARY.get(col))
        for col in columns
        if col in scoped or col in DUO_COLUMN_GLOSSARY
    }

CKAN_BASE = "https://onderwijsdata.duo.nl/api/3/action"
PORTAL_BASE = "https://onderwijsdata.duo.nl"

_GROUP_TO_ONDERWIJSTYPE = {
    "basisonderwijs": "PO",
    "voorgezet-onderwijs": "VO",
    "middelbaarberoepsonderwijs": "MBO",
    "hoger-onderwijs": "HO",
    "speciaal-onderwijs-en-leerproblemen": "SO",
    "inburgering": "Inburgering",
    "arbeidsovereenkomst-en-cao": "Arbeidsmarkt",
}


# ── publieke functies ──────────────────────────────────────────────────────────

def catalog() -> list[dict]:
    """Haal alle DUO datasets op als catalogusrecords (live van CKAN).

    Returns een lijst in hetzelfde formaat als riodata.catalog():
    leverancier, bron, beschrijving, periode, onderwijstype, tags, ...
    plus extra sleutels: _ckan_id, _resources.
    """
    pkgs = _ckan("package_search", rows=100, start=0)["results"]
    return [_pkg_to_record(p) for p in pkgs]


def resources(dataset_id: str) -> list[dict]:
    """Geef beschikbare bestanden (resources) voor een dataset.

    Returns lijst van dicts met: naam, url, format, id
    """
    pkg = _ckan("package_show", id=dataset_id)
    return [
        {
            "naam": r.get("name", ""),
            "url": _public_url(r),
            "format": r.get("format", "").upper(),
            "id": r.get("id", ""),
        }
        for r in pkg.get("resources", [])
    ]


def load(
    dataset_id: str,
    resource: int | str = 0,
    skiprows: int | None = None,
    **kwargs,
) -> "pd.DataFrame":
    """Download en laad een DUO dataset als DataFrame.

    Args:
        dataset_id: CKAN package-naam, bijv. "01voins-v1" of "p01hoinges"
        resource:   Index (int), CKAN resource-UUID, exacte naam of unieke naam-substring (str).
                    Een substring die op meerdere resources past geeft ``AmbigueResource``.
        skiprows:   Rijen overslaan boven de echte header (zelden nodig bij CSV)
        **kwargs:   Doorgegeven aan pd.read_csv() of pd.read_excel()

    Vereist pandas (uv add 'riodata[analyse]').
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("Installeer pandas: uv add 'riodata[analyse]'")

    res_list = resources(dataset_id)
    if not res_list:
        raise ValueError(f"Dataset '{dataset_id}' heeft geen downloadbare resources.")

    res = _pick_resource(res_list, resource, dataset_id)
    url = res["url"]
    fmt = res["format"].lower()
    schema = _schema_voor(dataset_id, res["id"])

    r = httpx.get(url, timeout=120, follow_redirects=True)
    r.raise_for_status()
    content = io.BytesIO(r.content)

    if "csv" in fmt:
        if skiprows is not None:
            kwargs["skiprows"] = skiprows
        if schema and "dtype" not in kwargs:
            # Codes als tekst lezen zoals de Datastore ze typeert: '0106' blijft '0106'.
            tekst = {k["naam"]: str for k in schema["kolommen"] if k["type"] == "text"}
            if tekst:
                kwargs["dtype"] = tekst
        # DUO CSV-bestanden gebruiken komma als scheidingsteken en aanhalingstekens
        df = pd.read_csv(content, **kwargs)
    else:
        kw = {"sheet_name": 0, **kwargs}
        if skiprows is not None:
            kw["skiprows"] = skiprows
        df = pd.read_excel(content, **kw)
    df.attrs["bron"] = {
        "dataset_id": dataset_id,
        "resource_id": res["id"],
        "resource_naam": res["naam"],
        "url": url,
        "schema_sha256": schema["schema_sha256"] if schema else None,
    }
    return df


# ── resource-schema's (offline, RIO-10) ───────────────────────────────────────

def resource_schemas(dataset_id: str) -> list[dict]:
    """Schema's van alle resources van een dataset, uit de meegeleverde snapshot.

    Per resource: ``resource_id`` (CKAN-UUID, stabiel), bronmetadata (formaat, MIME,
    grootte, hash, ``last_modified``), ``kolommen`` met het officiële Datastore-type,
    ``definities`` die voor déze resource gelden, ``waarden`` (``volledige_scan`` met
    ``domein`` óf ``steekproef`` met alleen ``voorbeeldwaarden``) en ``inspectie.status``.
    ``technisch_aantal_rijen`` is alleen een laadcontrole, geen telling van personen.

    Lege lijst als de dataset niet in de snapshot staat. Geen netwerk nodig.
    """
    ds = _schema_snapshot()["datasets"].get(dataset_id)
    if not ds:
        return []
    return [_met_definities(dataset_id, r) for r in ds["resources"]]


def resource_schema(dataset_id: str, resource: int | str) -> dict:
    """Schema van één resource: op UUID, index, exacte naam of unieke naam-substring.

    Een ambigue substring geeft ``AmbigueResource`` met de opties; een onbekende
    dataset of resource geeft ``ResourceNietGevonden``.
    """
    from ._resolutie import ResourceNietGevonden, kies
    schemas = resource_schemas(dataset_id)
    if not schemas:
        raise ResourceNietGevonden(f"Dataset '{dataset_id}' staat niet in de schema-snapshot.", [])
    items = [{**s, "id": s["resource_id"]} for s in schemas]
    gekozen = kies(items, resource, dataset_id, id_key="id")
    gekozen.pop("id")
    return gekozen


def _met_definities(dataset_id: str, res: dict) -> dict:
    uit = json.loads(json.dumps(res))
    uit["definities"] = column_definitions([k["naam"] for k in res["kolommen"]], dataset_id)
    return uit


def _schema_voor(dataset_id: str, resource_id: str) -> dict | None:
    """Snapshot-schema van een resource, alleen als de UUID exact overeenkomt."""
    ds = _schema_snapshot()["datasets"].get(dataset_id) or {}
    for r in ds.get("resources", []):
        if r["resource_id"] == resource_id and r["inspectie"]["status"] == "ok":
            return r
    return None


@lru_cache(maxsize=1)
def _schema_snapshot() -> dict:
    from importlib.resources import files
    try:
        tekst = files("riodata.data").joinpath("duo_resource_schemas.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"datasets": {}}
    return json.loads(tekst)


def search(query: str) -> list[dict]:
    """Zoek DUO datasets op een trefwoord.

    Returns catalogusrecords die matchen (zelfde formaat als catalog()).
    """
    result = _ckan("package_search", q=query, rows=50)
    return [_pkg_to_record(p) for p in result["results"]]


# ── intern ────────────────────────────────────────────────────────────────────

def _ckan(endpoint: str, **params) -> dict:
    r = httpx.get(f"{CKAN_BASE}/{endpoint}", params=params, timeout=30)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"CKAN fout bij {endpoint}: {body.get('error')}")
    return body["result"]


def _public_url(r: dict) -> str:
    url = r.get("url", "")
    if "beheer-ggm-ckan-prd" in url:
        return f"{PORTAL_BASE}/datastore/dump/{r['id']}"
    return url


def _pkg_to_record(pkg: dict) -> dict:
    groups = [g["name"] for g in pkg.get("groups", [])]
    onderwijstypen = [_GROUP_TO_ONDERWIJSTYPE.get(g, g) for g in groups]
    tags = [t["name"].lower() for t in pkg.get("tags", [])]

    notes = pkg.get("notes", "") or ""
    beschrijving = notes.split("\n\n")[0].replace("## ", "").replace("\r", "").strip()
    beschrijving = " ".join(beschrijving.split())[:300]

    res_list = [
        {
            "naam": r.get("name", ""),
            "url": _public_url(r),
            "format": r.get("format", "").upper(),
            "id": r.get("id", ""),
        }
        for r in pkg.get("resources", [])
    ]

    return {
        "leverancier": "DUO",
        "bron": pkg.get("title", pkg["name"]),
        "beschrijving": beschrijving,
        "periode": "Zie dataset (jaarlijks bijgewerkt)",
        "onderwijstype": onderwijstypen or ["Allen"],
        "doel": beschrijving,
        "frequentie": "Jaarlijks",
        "categorie": _groups_to_categorie(groups),
        "sectie": "DUO Open Data (CKAN)",
        "documentatie": {
            "tekst": pkg.get("title", pkg["name"]),
            "url": f"{PORTAL_BASE}/dataset/{pkg['name']}",
        },
        "filters": [],
        "sub_resources": [],
        "voorbeeldvragen": [],
        "tags": tags + ["duo", "open-data"],
        "combineerbaar_met": ["RIO organisatorische-eenheden (via BRIN-code)"],
        "_rio_resource": None,
        "_ckan_id": pkg["name"],
        "_resources": res_list,
        "_thema": _groups_to_categorie(groups),
        **details_from_pkg(pkg),
    }


def _groups_to_categorie(groups: list[str]) -> str:
    mapping = {
        "basisonderwijs": "PO",
        "voorgezet-onderwijs": "VO",
        "middelbaarberoepsonderwijs": "MBO",
        "hoger-onderwijs": "HO",
        "speciaal-onderwijs-en-leerproblemen": "SO",
        "inburgering": "Inburgering",
        "arbeidsovereenkomst-en-cao": "Arbeidsmarkt",
    }
    cats = [mapping.get(g, g) for g in groups]
    return "/".join(cats) if cats else "Overig"


def _pick_resource(res_list: list[dict], resource: int | str, dataset_id: str) -> dict:
    from ._resolutie import kies
    return kies(res_list, resource, dataset_id, id_key="id")
