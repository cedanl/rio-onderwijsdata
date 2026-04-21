"""ROA Arbeidsmarktinformatiesysteem client via DataverseNL.

Het Researchcentrum voor Onderwijs en Arbeidsmarkt (ROA) publiceert
arbeidsmarktprognoses en schoolverlatersdata via DataverseNL (DANS).

Gebruik:
    from riodata import roa

    # Catalogus
    datasets = roa.catalog()

    # Arbeidsmarktprognoses laden (AIS tot 2030, ~42 MB)
    df = roa.load("ais2030", "arbeidsmarkt")

    # Schoolverlaterscijfers laden (~23 MB)
    df = roa.load("ais2030", "schoolverlaters")

    # Arbeidsmarktuitkomsten (klein, ~0.2 MB)
    df = roa.load("ais2030", "uitkomsten")
"""
from __future__ import annotations

import io
import httpx

DATAVERSE_BASE = "https://dataverse.nl/api"

# DOI's van de ROA datasets op DataverseNL
_DATASETS: dict[str, dict] = {
    "ais2030": {
        "doi": "doi:10.34894/DVQTOG",
        "naam": "AIS tot 2030",
        "beschrijving": (
            "ROA Arbeidsmarktinformatiesysteem: middellange-termijn arbeidsmarktprognoses "
            "per opleiding en beroep tot 2030, plus kerncijfers schoolverlatersonderzoeken."
        ),
        "editie": "2025",
        "resources": {
            "arbeidsmarkt":   572235,
            "toelichting":    565548,
            "uitkomsten":     566770,
            "schoolverlaters": 565551,
        },
    },
    "ais2028": {
        "doi": "doi:10.34894/UIQHCI",
        "naam": "AIS tot 2028",
        "beschrijving": (
            "ROA Arbeidsmarktinformatiesysteem editie 2023 en 2024: "
            "prognoses per opleiding en beroep tot 2028."
        ),
        "editie": "2024",
        "resources": {
            "arbeidsmarkt_2023":   425745,
            "arbeidsmarkt_2024":   425747,
            "toelichting_2023":    425746,
            "toelichting_2024":    425742,
        },
    },
}


def catalog() -> list[dict]:
    """Geef beschikbare ROA datasets als catalogusrecords."""
    records = []
    for dataset_id, meta in _DATASETS.items():
        resources = [
            {"naam": naam, "file_id": fid, "url": f"{DATAVERSE_BASE}/access/datafile/{fid}"}
            for naam, fid in meta["resources"].items()
        ]
        records.append({
            "leverancier": "ROA",
            "bron": meta["naam"],
            "beschrijving": meta["beschrijving"],
            "periode": f"Editie {meta['editie']}",
            "onderwijstype": ["Allen"],
            "doel": "Arbeidsmarktprognoses en schoolverlatersonderzoek per opleiding en beroep",
            "frequentie": "Jaarlijks",
            "categorie": "Arbeidsmarkt",
            "sectie": "ROA / DataverseNL",
            "documentatie": {
                "tekst": meta["naam"],
                "url": f"https://doi.org/{meta['doi'].replace('doi:', '')}",
            },
            "filters": ["opleiding", "beroep", "regio"],
            "sub_resources": [],
            "voorbeeldvragen": [
                f"Wat zijn de arbeidsmarktperspectieven voor MBO-gediplomeerden tot {meta['editie'][:4]}?",
                "Welke opleidingen hebben de beste arbeidsmarktkansen?",
                "Hoe verhoudt de uitstroom van schoolverlaters zich tot de vraag per beroep?",
            ],
            "tags": ["roa", "arbeidsmarkt", "prognose", "schoolverlaters", "opleiding", "beroep"],
            "combineerbaar_met": [
                "DUO (diplomering per opleiding)",
                "CBS (arbeidsdeelname naar onderwijsniveau)",
                "RIO (aangeboden opleidingen)",
            ],
            "_rio_resource": None,
            "_ckan_id": None,
            "_roa_id": dataset_id,
            "_resources": resources,
            "_thema": "Arbeidsmarkt",
        })
    return records


def resources(dataset_id: str) -> list[dict]:
    """Geef beschikbare bestanden voor een ROA dataset."""
    meta = _get_meta(dataset_id)
    return [
        {"naam": naam, "file_id": fid, "url": f"{DATAVERSE_BASE}/access/datafile/{fid}"}
        for naam, fid in meta["resources"].items()
    ]


def load(
    dataset_id: str,
    resource: int | str = 0,
    **kwargs,
) -> "pd.DataFrame":
    """Download en laad een ROA dataset als DataFrame.

    Args:
        dataset_id: "ais2030" of "ais2028"
        resource:   Index (int), resourcenaam (str, bijv. "arbeidsmarkt", "schoolverlaters")
                    of file_id (int > 1000)
        **kwargs:   Doorgegeven aan pd.read_csv()

    Vereist pandas (uv add 'riodata[analyse]').
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("Installeer pandas: uv add 'riodata[analyse]'")

    meta = _get_meta(dataset_id)
    file_id = _pick_file_id(meta, resource, dataset_id)

    r = httpx.get(
        f"{DATAVERSE_BASE}/access/datafile/{file_id}",
        timeout=180,
        follow_redirects=True,
    )
    r.raise_for_status()

    content = r.content
    for enc in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            kw = {"sep": ";", "encoding": enc, **kwargs}
            return pd.read_csv(io.BytesIO(content), **kw)
        except (UnicodeDecodeError, Exception):
            continue
    raise RuntimeError(f"Kon ROA bestand {file_id} niet decoderen.")


# ── intern ────────────────────────────────────────────────────────────────────

def _get_meta(dataset_id: str) -> dict:
    if dataset_id not in _DATASETS:
        raise ValueError(
            f"Onbekende dataset '{dataset_id}'. Kies uit: {list(_DATASETS)}"
        )
    return _DATASETS[dataset_id]


def _pick_file_id(meta: dict, resource: int | str, dataset_id: str) -> int:
    res = meta["resources"]
    names = list(res.keys())
    ids = list(res.values())

    if isinstance(resource, int) and resource > 1000:
        # Directe file_id meegegeven
        return resource
    if isinstance(resource, int):
        if resource >= len(names):
            raise IndexError(
                f"Dataset '{dataset_id}' heeft {len(names)} resources, index {resource} bestaat niet."
            )
        return ids[resource]
    # String: zoek op naam-substring
    matches = [name for name in names if resource.lower() in name.lower()]
    if not matches:
        raise ValueError(
            f"Geen resource met '{resource}' in dataset '{dataset_id}'. Beschikbaar: {names}"
        )
    return res[matches[0]]
