# riodata

Python client voor Nederlandse onderwijs- en arbeidsmarktdata uit zes bronnen:

- **RIO LOD API v2** — dagelijks bijgewerkt register van instellingen en opleidingen (14 resources)
- **DUO Open Data** — 56 datasets via [onderwijsdata.duo.nl](https://onderwijsdata.duo.nl) (CKAN API)
- **ROA** — arbeidsmarktprognoses (2 datasets)
- **UWV** — Open Match Data (1 dataset)
- **Inspectie van het Onderwijs** — open data (2 datasets)
- **SBB** — CREBO-lijst en kwalificatiedossiers (2 datasets)

## Installatie

```bash
pip install riodata                  # alleen clients (httpx)
pip install riodata[analyse]         # + pandas, matplotlib, openpyxl
pip install riodata[duo]             # + openpyxl (voor DUO Excel-bestanden)
pip install riodata[sbb]             # + openpyxl (voor de CREBO-loader, riodata.crebo)
pip install riodata[catalogus]       # + anthropic, pyyaml (voor de catalogusscripts)
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

# Catalogus bekijken (56 datasets, offline)
datasets = duo.catalog()

# Zoeken op trefwoord
hits = duo.search("prognose mbo")

# Beschikbare bestanden per dataset
duo.resources("studentprognoses-mbo-per-instelling")

# Data laden als DataFrame (vereist pandas)
df = duo.load("studentprognoses-mbo-per-instelling", "mbo-studentenprognose_instelling")
df = duo.load("p01hoinges", 1)           # WO ingeschrevenen per geslacht
df = duo.load("p01hoinges", "b88721ef-9787-4299-afc7-5d74380d29ba")  # op CKAN resource-UUID (stabiel)
# Een naam-substring die op meer resources past geeft AmbigueResource met de opties.

# Officiële kolomtypes per resource (offline; '0106' blijft tekst)
duo.resource_schemas("p01hoinges")
```

## Datasetcontract

Modelonafhankelijk contract voor alle zes bronnen, afgestemd op `onderwijsdata.contract` (CBS):

```python
from riodata import contract

contract.catalog_records(sector="mbo")            # alleen datasets waar mbo 'supported' is
contract.get_dataset("duo:p01hoinges")             # of de alias "p01hoinges"
contract.get_resource("duo:p01hoinges", "c454d7e1-b9b1-4460-b9ff-55938c85788e")
contract.scope_review()                            # dekking nog onbekend
contract.catalog_manifest()                        # versie, inhoudshash, aantallen
```

Dekking is `supported`/`unsupported`/`unknown`, nooit afgeleid uit een ontbrekend veld. HO-breed
(`ho_breed`) staat los van hbo en wo; `sectorselectie[sector].verplicht` zegt wanneer een sector
alleen met een filter (RIO-type), resourcekeuze of rijselectie (DUO) leverbaar is.

## Broncontrole

Een wekelijkse workflow (`.github/workflows/broncontrole.yml`) vergelijkt de DUO CKAN-inventaris en de
RIO-spec met de catalogus en meldt verschillen als issue. De catalogus wordt daarbij niet automatisch
vernieuwd. RIO live, SBB, ROA, UWV en Inspectie worden nog niet gecontroleerd.

## Catalogus

```python
import riodata

riodata.catalog(source="rio")   # 14 RIO-resources (offline, lokale JSON)
riodata.catalog(source="duo")   # 56 DUO-datasets (offline, lokale JSON)
riodata.catalog(source="all")   # 77 gecombineerd (RIO, DUO, ROA, UWV, Inspectie, SBB)

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
    duo_resources.json      56 DUO-datasets (gegenereerd uit CKAN)
data/02-prepared/       bron-JSONs voor de catalogus
voorbeelden/            analysescripts + plots
docs/                   GitHub Pages catalogussite
RIO_LOD_API_v2.yml      OpenAPI spec van de RIO API
```

## Links

- [Catalogussite](https://cedanl.github.io/rio-onderwijsdata)
- [RIO LOD API documentatie](https://lod.onderwijsregistratie.nl/api/rio/v2)
- [DUO Open Data portaal](https://onderwijsdata.duo.nl/datasets)
