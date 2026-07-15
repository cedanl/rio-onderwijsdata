__version__ = "0.3.0"

from .client import fetch, get, related
from . import duo, roa, uwv, inspectie, sbb


def catalog(source: str = "rio", ai: bool = True, live: bool = False) -> list[dict]:
    """Geef catalogusrecords terug.

    Args:
        source: "rio"       — alleen RIO LOD API resources (lokale JSON, snel)
                "duo"       — alleen DUO datasets (lokale snapshot)
                "roa"       — alleen ROA arbeidsmarktdata
                "uwv"       — alleen UWV Open Match Data
                "inspectie" — alleen Inspectie van het Onderwijs datasets
                "sbb"       — alleen SBB kwalificatiestructuur datasets
                "all"       — alles gecombineerd
        ai:     Bij source="rio"/"all": gebruik AI-verrijkte beschrijvingen (default True).
        live:   Bij source="duo"/"all": haal DUO-records live op van CKAN i.p.v. lokale
                snapshot (default False). Vereist internetverbinding.
    """
    import json
    from importlib.resources import files

    data_dir = files("riodata.data")

    def _rio():
        if ai:
            try:
                return json.loads(data_dir.joinpath("rio_resources_enriched.json").read_text(encoding="utf-8"))
            except FileNotFoundError:
                pass
        filename = "rio_resources_ai.json" if ai else "rio_resources.json"
        return json.loads(data_dir.joinpath(filename).read_text(encoding="utf-8"))

    def _duo():
        if live:
            return duo.catalog()
        try:
            return json.loads(data_dir.joinpath("duo_resources_enriched.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        return json.loads(data_dir.joinpath("duo_resources.json").read_text(encoding="utf-8"))

    def _roa():
        return json.loads(files("riodata.data").joinpath("roa_resources.json").read_text(encoding="utf-8"))

    def _uwv():
        return json.loads(files("riodata.data").joinpath("uwv_resources.json").read_text(encoding="utf-8"))

    def _inspectie():
        return json.loads(files("riodata.data").joinpath("inspectie_resources.json").read_text(encoding="utf-8"))

    def _sbb():
        return json.loads(files("riodata.data").joinpath("sbb_resources.json").read_text(encoding="utf-8"))

    if source == "rio":
        return _rio()
    if source == "duo":
        return _duo()
    if source == "roa":
        return _roa()
    if source == "uwv":
        return _uwv()
    if source == "inspectie":
        return _inspectie()
    if source == "sbb":
        return _sbb()
    if source == "all":
        return _rio() + _duo() + _roa() + _uwv() + _inspectie() + _sbb()
    raise ValueError(
        f"Ongeldige source '{source}'. "
        f"Kies 'rio', 'duo', 'roa', 'uwv', 'inspectie', 'sbb' of 'all'."
    )


__all__ = ["fetch", "get", "related", "catalog", "duo", "roa", "uwv", "inspectie", "sbb", "__version__"]
