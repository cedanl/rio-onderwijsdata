# riodata

Python client voor Nederlandse onderwijsdata uit twee bronnen:

- **RIO LOD API v2** — dagelijks bijgewerkt register van instellingen en opleidingen
- **DUO Open Data** — 57 datasets via [onderwijsdata.duo.nl](https://onderwijsdata.duo.nl) (CKAN API)

## Installatie

```bash
pip install riodata                  # alleen clients (httpx)
pip install riodata[analyse]         # + pandas, matplotlib, openpyxl
pip install riodata[duo]             # + openpyxl (voor DUO Excel-bestanden)
pip install riodata[catalogus]       # + anthropic (voor catalogus_ai.py)
```

## RIO LOD API

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

## DUO Open Data

```python
from riodata import duo

# Catalogus bekijken (57 datasets, offline)
datasets = duo.catalog()

# Zoeken op trefwoord
hits = duo.search("prognose mbo")

# Beschikbare bestanden per dataset
duo.resources("studentprognoses-mbo-per-instelling")

# Data laden als DataFrame (vereist pandas)
df = duo.load("studentprognoses-mbo-per-instelling", "mbo-studentenprognose_instelling")
df = duo.load("p01hoinges", 1)           # WO ingeschrevenen per geslacht
df = duo.load("p01hoinges", "wetenschappelijk")  # selectie op naam
```

## Catalogus

```python
import riodata

riodata.catalog(source="rio")   # 14 RIO-resources (offline, lokale JSON)
riodata.catalog(source="duo")   # 57 DUO-datasets (offline, lokale JSON)
riodata.catalog(source="all")   # 71 gecombineerd

# Live DUO-catalogus vernieuwen vanuit CKAN
riodata.catalog(source="duo", live=True)
```

Elk record heeft dezelfde velden: `leverancier`, `bron`, `beschrijving`, `periode`,
`onderwijstype`, `tags`, `voorbeeldvragen`, `combineerbaar_met`, en voor DUO ook
`_ckan_id`, `_resources` en `_kolommen`.

## Structuur

```
src/riodata/
  client.py             RIO LOD API client (fetch, get, related)
  duo.py                DUO CKAN client (catalog, resources, load, search)
  data/
    rio_resources_ai.json   14 RIO-resources met AI-verrijking
    rio_resources.json      idem, zonder AI-verrijking
    duo_resources.json      57 DUO-datasets (gegenereerd uit CKAN)
data/02-prepared/       bron-JSONs voor de catalogus
voorbeelden/            analysescripts + plots
docs/                   GitHub Pages catalogussite
RIO_LOD_API_v2.yml      OpenAPI spec van de RIO API
```

## Links

- [Catalogussite](https://cedanl.github.io/rio-onderwijsdata)
- [RIO LOD API documentatie](https://lod.onderwijsregistratie.nl/api/rio/v2)
- [DUO Open Data portaal](https://onderwijsdata.duo.nl/datasets)
