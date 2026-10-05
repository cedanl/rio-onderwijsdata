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
def catalog() -> list[dict]:
    """Geef beschikbare ROA datasets als catalogusrecords (lokale snapshot).

    ``roa_resources.json`` is de enige resourcebron: de loader leest dezelfde lijst.
    """
    import json
    from importlib.resources import files
    return json.loads(files("riodata.data").joinpath("roa_resources.json").read_text(encoding="utf-8"))


def _datasets() -> dict[str, dict]:
    return {
        r["_roa_id"]: {"naam": r["bron"], "resources": {x["naam"]: x["file_id"] for x in r["_resources"]}}
        for r in catalog()
    }


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

    Bron-URL, checksum en encoding staan in ``df.attrs['bron']``. Download-, decodeer-,
    parser- en schemafouten zijn aparte uitzonderingen (zie ``riodata._lezen``).

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

    from ._lezen import herkomst, lees_csv

    df, enc = lees_csv(r.content, defaults={"sep": ";"}, **kwargs)
    df.attrs["bron"] = {**herkomst(r.content, str(r.url)), "encoding": enc, "file_id": file_id}
    return df


# ── intern ────────────────────────────────────────────────────────────────────

def _get_meta(dataset_id: str) -> dict:
    datasets = _datasets()
    if dataset_id not in datasets:
        raise ValueError(
            f"Onbekende dataset '{dataset_id}'. Kies uit: {list(datasets)}"
        )
    return datasets[dataset_id]


def _pick_file_id(meta: dict, resource: int | str, dataset_id: str) -> int:
    res = meta["resources"]
    if isinstance(resource, int) and not isinstance(resource, bool) and resource > 1000:
        # Directe file_id meegegeven
        return resource
    from ._resolutie import kies
    items = [{"naam": naam, "file_id": fid} for naam, fid in res.items()]
    return kies(items, resource, dataset_id, id_key="file_id")["file_id"]
