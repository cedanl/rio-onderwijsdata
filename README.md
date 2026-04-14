# rio-duo-open-onderwijsdata

Python package en catalogussite voor de [RIO LOD API v2](https://lod.onderwijsregistratie.nl/api/rio/v2) — het dagelijks bijgewerkte register van Nederlandse onderwijsinstellingen, -aanbieders en opleidingen (Registratie Instellingen en Opleidingen).

## Installatie

```bash
uv sync
```

## Gebruik

```python
from riodata import client

# Alle onderwijslocaties ophalen (pagineert automatisch)
locaties = client.fetch("onderwijslocaties")

# Één record ophalen via ID
instelling = client.get("organisatorische-eenheden", "some-uuid")

# Sub-resources ophalen
cohorten = client.related("aangeboden-opleidingen", uuid, "aangeboden-opleiding-cohorten")
```

## Structuur

```
src/riodata/client.py           RIO LOD API client (fetch, get, related)
data/02-prepared/
  rio_resources.json            14 resources — basismetadata
  rio_resources_ai.json         14 resources — met AI-samenvatting, tags, voorbeeldvragen
catalogus/catalogus_ai.py       AI-verrijking via Claude Batches API
voorbeelden/                    Analysescripts + output
docs/                           GitHub Pages catalogussite
RIO_LOD_API_v2.yml              OpenAPI spec van de RIO API
```

## Nieuwe analyse toevoegen

Zie `CLAUDE.md` voor de stap-voor-stap workflow.

Scripts draaien met:

```bash
uv run python voorbeelden/rio_onderwijslocaties.py
```
