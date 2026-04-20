__version__ = "0.1.0"

from .client import fetch, get, related
from . import duo


def catalog(source: str = "rio", ai: bool = True, live: bool = False) -> list[dict]:
    """Geef catalogusrecords terug.

    Args:
        source: "rio"  — alleen RIO LOD API resources (lokale JSON, snel)
                "duo"  — alleen DUO datasets (lokale snapshot)
                "all"  — RIO + DUO gecombineerd
        ai:     Bij source="rio"/"all": gebruik AI-verrijkte beschrijvingen (default True).
        live:   Bij source="duo"/"all": haal DUO-records live op van CKAN i.p.v. lokale
                snapshot (default False). Vereist internetverbinding.
    """
    import json
    from importlib.resources import files

    def _rio():
        filename = "rio_resources_ai.json" if ai else "rio_resources.json"
        return json.loads(files("riodata.data").joinpath(filename).read_text(encoding="utf-8"))

    def _duo():
        if live:
            return duo.catalog()
        return json.loads(files("riodata.data").joinpath("duo_resources.json").read_text(encoding="utf-8"))

    if source == "rio":
        return _rio()
    if source == "duo":
        return _duo()
    if source == "all":
        return _rio() + _duo()
    raise ValueError(f"Ongeldige source '{source}'. Kies 'rio', 'duo' of 'all'.")


__all__ = ["fetch", "get", "related", "catalog", "duo", "__version__"]
