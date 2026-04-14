# CLAUDE.md — RIO DUO Open Onderwijsdata

Dit is een Python package voor de RIO LOD API v2 — het dagelijks bijgewerkte
publieke register van Nederlandse onderwijsinstellingen en opleidingen —
plus een GitHub Pages catalogussite. Hieronder staat hoe je als AI-assistent
een nieuwe analyse maakt van A tot Z.

---

## Repo-structuur

```
src/riodata/client.py           RIO LOD API client (fetch, get, related)
data/02-prepared/
  rio_resources_ai.json         Catalogus: 14 resources met AI-samenvatting, tags, voorbeeldvragen
  rio_resources.json            Catalogus: zelfde resources, zonder AI-verrijking
RIO_LOD_API_v2.yml              OpenAPI spec van de RIO API
voorbeelden/
  manifest.json                 Bron voor alle voorbeelden op de site
  output/                       Plots (.png) en interpretaties (INTERPRETATIE.md)
  *.py                          Analysescripts
docs/                           GitHub Pages site (gebouwd door workflow)
```

---

## Workflow: nieuwe analyse toevoegen

### Stap 1 — Verken de catalogus

Lees `data/02-prepared/rio_resources_ai.json` om te zien welke resources beschikbaar zijn.
Elk object heeft: `_rio_resource`, `bron`, `periode`, `doel`, `tags`, `voorbeeldvragen`, `categorie`, `sub_resources`, `filters`.

Handige filters om relevante resources te vinden:
- Op categorie: `Instellingen`, `Opleidingsstructuur`, `Aanbod`, `Locaties`, `Licenties en erkenningen`
- Op `_rio_resource`: bijv. `"organisatorische-eenheden"`, `"aangeboden-opleidingen"`, `"onderwijslocaties"`
- Op `tags`: bijv. `instellingen`, `opleidingen`, `locaties`, `erkenningen`, `mbo`, `cohorten`

### Stap 2 — Verken de resource

Gebruik de client om data te bekijken vóórdat je analyses schrijft:

```python
from riodata import client

# Kleine steekproef van een resource
sample = client.fetch("onderwijslocaties", page=0, pageSize=3)

# Één record ophalen via ID (UUID)
instelling = client.get("organisatorische-eenheden", "some-uuid")

# Sub-resources ophalen
cohorten = client.related("aangeboden-opleidingen", uuid, "aangeboden-opleiding-cohorten")
```

Alle beschikbare resources staan in `RIO_LOD_API_v2.yml` (OpenAPI spec).

### Stap 3 — Schrijf het analysescript

Maak een nieuw script in `voorbeelden/`. Conventies:

- **Bestandsnaam**: beschrijvend, lowercase met underscores, bijv. `rio_mbo_aanbod_regio.py`
- **Docstring bovenaan**: vermeld gebruikte resource(s) en de centrale vraag
- **Output**: sla plot(s) op in `voorbeelden/output/` als PNG
- **Submap**: bij meerdere plots per analyse, gebruik een submap: `voorbeelden/output/{analyse_naam}/`
- Gebruik `matplotlib` voor visualisaties; geen interactieve libraries

Minimale scriptstructuur:

```python
"""
Titel van de analyse
Resource(s): RIO LOD API v2 — onderwijslocaties
Centrale vraag: ...
"""
import pandas as pd
import matplotlib.pyplot as plt
from riodata import client

OUTPUT = "voorbeelden/output/mijn_analyse.png"

# 1. Data ophalen
items = client.fetch("onderwijslocaties")
df = pd.DataFrame(items)

# 2. Bewerken en plotten
fig, ax = plt.subplots(figsize=(10, 6))
# ...
fig.suptitle("Titel", fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig(OUTPUT, dpi=150, bbox_inches="tight")
print(f"Plot opgeslagen: {OUTPUT}")
```

Scripts draaien met: `uv run python voorbeelden/mijn_analyse.py`

### Stap 4 — Schrijf de interpretatie

Maak een `INTERPRETATIE.md` naast de plot. Bij een enkele plot: `voorbeelden/output/{naam}_INTERPRETATIE.md`.
Bij een submap: `voorbeelden/output/{naam}/INTERPRETATIE.md`.

Structuur van de interpretatie:

```markdown
# Titel van de analyse

**Resource(s):** RIO LOD API v2 — [resource naam]
**Periode:** actueel (dagelijks bijgewerkt)
**Analyseniveau:** ...

---

## Belangrijkste bevindingen

### 1. Bevinding
Beschrijving met concrete cijfers uit de plot.

### 2. Bevinding
...

---

## Strategische implicaties

1. ...
2. ...

---

*Bron: RIO LOD API v2 — lod.onderwijsregistratie.nl*
*Analyse: [maand jaar]*
```

### Stap 5 — Voeg toe aan manifest

Voeg een entry toe aan `voorbeelden/manifest.json`:

```json
{
  "id": "mijn_analyse",
  "titel": "Korte beschrijvende titel",
  "vraag": "De centrale vraag die deze analyse beantwoordt?",
  "datasets": ["onderwijslocaties"],
  "plot": "mijn_analyse.png",
  "interpretatie": "mijn_analyse_INTERPRETATIE.md",
  "status": "experimenteel"
}
```

Het veld `datasets` bevat `_rio_resource` waarden (bijv. `"onderwijslocaties"`, `"organisatorische-eenheden"`).

Voor een analyse met submap:
- `"plot": "mijn_analyse/mijn_analyse.png"`
- `"interpretatie": "mijn_analyse/INTERPRETATIE.md"` → wordt door de workflow hernoemd naar `mijn_analyse_INTERPRETATIE.md`

Velden:
| Veld | Beschrijving |
|---|---|
| `id` | Uniek, lowercase underscore, zelfde als scriptnaam |
| `titel` | Wat de analyse laat zien (max ~60 tekens) |
| `vraag` | De concrete vraag die beantwoord wordt |
| `datasets` | Lijst van `_rio_resource` waarden die gebruikt worden |
| `plot` | Pad relatief t.o.v. `voorbeelden/output/` |
| `interpretatie` | Idem, of `null` als er geen is |
| `status` | Altijd `"experimenteel"` |

### Stap 6 — Push

```bash
git add voorbeelden/
git commit -m "feat: [beschrijving analyse]"
git push
```

De GitHub Actions workflow pikt de wijzigingen in `voorbeelden/manifest.json` en `voorbeelden/output/` automatisch op, en synct alles naar `docs/voorbeelden/`.

---

## Client-referentie

```python
from riodata import client

client.fetch(resource, **params)
# Haalt alle items op van een list-resource, pagineert automatisch via HATEOAS.
# page=N voor slechts één pagina; pageSize=N (max 100, API-maximum)
# Voorbeeld: client.fetch("onderwijslocaties", page=0, pageSize=10)

client.get(resource, id, **params)
# Haalt één resource op via UUID.
# Voorbeeld: client.get("organisatorische-eenheden", "some-uuid")

client.related(resource, id, sub, **params)
# Haalt gelinkte sub-resources op.
# Voorbeeld: client.related("aangeboden-opleidingen", uuid, "aangeboden-opleiding-cohorten")
```

API-tips:
- Paginering: de API pagineert via HATEOAS `_links.next`; `client.fetch()` volgt dit automatisch
- Filters: gebruik query-parameters zoals `organisatorischeEenheidType=ONDERWIJSINSTELLING`
- Datum: `datumGeldigOp=2024-01-01` voor historische snapshots
- Alle beschikbare endpoints en parameters staan in `RIO_LOD_API_v2.yml`

---

## Wat niet hoeft

- Geen `docs/` handmatig aanpassen — de workflow regelt dat
- Geen `docs/data.json` of `docs/voorbeelden.json` aanraken
- Geen nieuwe dependencies toevoegen zonder `uv add`
