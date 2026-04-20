__version__ = "0.1.0"

from .client import fetch, get, related

def catalog(ai=True):
    import json
    from importlib.resources import files
    filename = "rio_resources_ai.json" if ai else "rio_resources.json"
    return json.loads(files("riodata.data").joinpath(filename).read_text(encoding="utf-8"))

__all__ = ["fetch", "get", "related", "catalog", "__version__"]
