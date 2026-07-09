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
    df = duo.load("p01hoinges", "Ingeschrevenen hbo geslacht")  # op naam
"""
from __future__ import annotations
import io
import httpx

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
    "LEERWEG": "Onderwijsvorm: VOLTIJD, DEELTIJD of DUAAL.",
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


def column_definitions(columns: list[str]) -> dict[str, str]:
    """Geeft bekende definities terug voor kolomnamen uit DUO-datasets.

    Returns dict met alleen de kolommen waarvoor een definitie bekend is.
    """
    return {col: DUO_COLUMN_GLOSSARY[col] for col in columns if col in DUO_COLUMN_GLOSSARY}

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
        resource:   Index (int) of naam-substring (str) van de resource (default: 0)
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

    r = httpx.get(url, timeout=120, follow_redirects=True)
    r.raise_for_status()
    content = io.BytesIO(r.content)

    if "csv" in fmt:
        if skiprows is not None:
            kwargs["skiprows"] = skiprows
        # DUO CSV-bestanden gebruiken komma als scheidingsteken en aanhalingstekens
        return pd.read_csv(content, **kwargs)
    else:
        kw = {"sheet_name": 0, **kwargs}
        if skiprows is not None:
            kw["skiprows"] = skiprows
        return pd.read_excel(content, **kw)


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
    if isinstance(resource, int):
        if resource >= len(res_list):
            raise IndexError(
                f"Dataset '{dataset_id}' heeft {len(res_list)} resources, "
                f"index {resource} bestaat niet."
            )
        return res_list[resource]
    # String: zoek op naam-substring (case-insensitive)
    matches = [r for r in res_list if resource.lower() in r["naam"].lower()]
    if not matches:
        namen = [r["naam"] for r in res_list]
        raise ValueError(
            f"Geen resource met '{resource}' in dataset '{dataset_id}'. "
            f"Beschikbaar: {namen}"
        )
    return matches[0]
