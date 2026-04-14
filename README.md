# riodata

Python client voor de [RIO LOD API v2](https://lod.onderwijsregistratie.nl/api/rio/v2) — het dagelijks bijgewerkte register van Nederlandse onderwijsinstellingen en opleidingen.

## Installatie

```bash
pip install riodata                  # alleen client
pip install riodata[analyse]         # + pandas en matplotlib
pip install riodata[catalogus]       # + anthropic (voor catalogus_ai.py)
```

## Gebruik

```python
from riodata import fetch, get, related

# Alle onderwijslocaties ophalen (pagineert automatisch)
locaties = fetch("onderwijslocaties")

# Aangeboden opleidingen per instelling via BRIN-code
aanbod = fetch("aangeboden-opleidingen", organisatorischeEenheidcode="25LH")

# Één record ophalen via UUID
instelling = get("organisatorische-eenheden", "some-uuid")

# Sub-resources van een record
cohorten = related("aangeboden-opleidingen", uuid, "aangeboden-opleiding-cohorten")
```

## Structuur

```
src/riodata/          Python package (RIO LOD API client)
catalogus/            AI-verrijking van de resourcecatalogus
data/02-prepared/     14 RIO-resources met samenvatting, tags en voorbeeldvragen
voorbeelden/          Analysescripts + gegenereerde plots
docs/                 GitHub Pages catalogussite
RIO_LOD_API_v2.yml    OpenAPI spec van de RIO API
```

## Links

- [Catalogussite](https://cedanl.github.io/rio-onderwijsdata)
- [RIO LOD API documentatie](https://lod.onderwijsregistratie.nl/api/rio/v2)
