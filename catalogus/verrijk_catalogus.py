"""
Verrijkt DUO- en RIO-catalogus-entries met data-analyse en LLM-samenvattingen.

Per dataset haalt het script de echte data op, analyseert kolommen en waarden,
en genereert via een LLM een verrijkte catalogus-entry met samenvatting,
voorbeeldvragen, tags, kolomtoelichting en meer.

Gebruik:
  uv run python catalogus/verrijk_catalogus.py --source duo --base-url http://localhost:11434/v1 --model big-pickle
  uv run python catalogus/verrijk_catalogus.py --source rio --base-url http://localhost:11434/v1 --model big-pickle
  uv run python catalogus/verrijk_catalogus.py --source all --limit 5
  uv run python catalogus/verrijk_catalogus.py --no-skip-existing --source duo
  uv run python catalogus/verrijk_catalogus.py --help
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

# ─── Paden ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent / "src" / "riodata" / "data"
DUO_INPUT = DATA_DIR / "duo_resources.json"
RIO_INPUT = DATA_DIR / "rio_resources_ai.json"
DUO_OUTPUT = DATA_DIR / "duo_resources_enriched.json"
RIO_OUTPUT = DATA_DIR / "rio_resources_enriched.json"

# ─── LLM-prompt templates ──────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Je bent een assistent die Nederlandse onderwijsdatabronnen analyseert voor \
beleids- en datamedewerkers bij onderwijsinstellingen. Je krijgt een \
catalogus-entry aangeboden met metadata én een steekproef van de werkelijke \
data. Geef altijd antwoord als geldige JSON zonder extra tekst of markdown."""

DUO_USER_TEMPLATE = """\
Analyseer deze DUO-dataset en genereer een verrijkte catalogus-entry.

## Metadata
- Bron: {bron}
- Beschrijving: {beschrijving}
- Categorie: {categorie}
- Periode: {periode}
- Onderwijstype: {onderwijstype}

## Beschikbare bestanden
{resources_overview}

## Kolomanalyse (per bestand)
{kolom_analyse}

## Geladen data (eerste {n_rows} rijen van eerste bestand)
{data_sample}

## Kolomdefinities (uit DUO glossary)
{kolom_definities}

Geef terug als JSON met exact deze sleutels:
{{
  "samenvatting": "<3-4 zinnen over inhoud, doelgroep, granulariteit>",
  "voorbeeldvragen": ["<vraag 1>", "<vraag 2>", ...],
  "tags": ["<tag1>", "<tag2>", ...],
  "niet_geschikt_voor": ["<wat de dataset NIET kan>", ...],
  "kolomtoelichting": {{"KOLOMNAAM": "<uitleg in begrijpelijke taal>", ...}},
  "waardenbereik": {{
    "periode": "<bijv. 2006-2023 of onbekend>",
    "meetwaarden": ["<belangrijkste numerieke kolommen met range>"],
    "geografisch_niveau": "<bijv. instelling, gemeente, landelijk>"
  }},
  "combineerbaar_met": ["<resource of dataset + uitleg>", ...]
}}

Voorbeeldvragen moeten divers en concreet zijn (minimaal 8, maximaal 10).
Tags moeten synoniemen en gerelateerde termen bevatten.
niet_geschikt_voor moet duidelijk maken wat de dataset NIET biedt."""

RIO_USER_TEMPLATE = """\
Analyseer deze RIO LOD API-resource en genereer een verrijkte catalogus-entry.

## Metadata
- Bron: {bron}
- Beschrijving: {beschrijving}
- Categorie: {categorie}
- Periode: {periode}
- Filters: {filters}
- Sub-resources: {sub_resources}

## Beschikbare velden (uit {n_samples} voorbeeldrecords)
{veld_overzicht}

## Voorbeeldrecords (JSON)
{voorbeeld_records}

Geef terug als JSON met exact deze sleutels:
{{
  "samenvatting": "<3-4 zinnen over inhoud, doelgroep, granulariteit>",
  "voorbeeldvragen": ["<vraag 1>", "<vraag 2>", ...],
  "tags": ["<tag1>", "<tag2>", ...],
  "niet_geschikt_voor": ["<wat de resource NIET kan>", ...],
  "kolomtoelichting": {{"VELDNAAM": "<uitleg in begrijpelijke taal>", ...}},
  "waardenbereik": {{
    "periode": "<bijv. actueel of historisch bereik>",
    "meetwaarden": ["<belangrijkste waarden>"],
    "geografisch_niveau": "<bijv. instelling, gemeente, landelijk>"
  }},
  "combineerbaar_met": ["<resource of dataset + uitleg>", ...]
}}

Voorbeeldvragen moeten divers en concreet zijn (minimaal 8, maximaal 10).
Tags moeten synoniemen en gerelateerde termen bevatten.
niet_geschikt_voor moet duidelijk maken wat de resource NIET biedt."""


# ─── Hulptaken ──────────────────────────────────────────────────────────────


def _json_extract(text: str) -> dict | None:
    """Probeer JSON te extrateren uit LLM-antwoord."""
    # Eerst proberen: volledige tekst is JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Tweede poging: uit markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Derde poging: zoek naar eerste { en laatste }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _call_llm(client: httpx.Client, base_url: str, model: str, user_msg: str) -> dict | None:
    """Roep de LLM aan en retourneer parsed JSON."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    }

    try:
        resp = client.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return _json_extract(content)
    except httpx.TimeoutException:
        print("    TIMEOUT: LLM-reactie duurde langer dan 120 seconden")
        return None
    except httpx.HTTPStatusError as e:
        print(f"    HTTP FOUT {e.response.status_code}: {e.response.text[:200]}")
        return None
    except (KeyError, IndexError) as e:
        print(f"    Onverwacht LLM-antwoordformaat: {e}")
        return None
    except Exception as e:
        print(f"    Onverwachte fout bij LLM-aanroep: {e}")
        return None


# ─── DUO-analyse ────────────────────────────────────────────────────────────


def analyseer_duo(entry: dict) -> dict | None:
    """Haal data op en analyseer een DUO-dataset."""
    from riodata import duo as _duo

    dataset_id = entry.get("_ckan_id")
    if not dataset_id:
        return None

    result = {
        "resources_overview": "",
        "kolom_analyse": "",
        "data_sample": "",
        "kolom_definities": "",
        "n_rows": 0,
    }

    # 1. Beschikbare bestanden
    try:
        resources = _duo.resources(dataset_id)
        lines = []
        for r in resources:
            lines.append(f"- {r['naam']} ({r['format']})")
        result["resources_overview"] = "\n".join(lines) if lines else "Geen bestanden gevonden"
    except Exception as e:
        print(f"    FOUT bij ophalen resources: {e}")
        result["resources_overview"] = f"Fout bij ophalen: {e}"

    # 2. Data laden (eerste resource, max 100 rijen)
    df = None
    try:
        df = _duo.load(dataset_id, 0, nrows=100)
        result["n_rows"] = len(df)
    except Exception as e:
        print(f"    FOUT bij laden data: {e}")

    # 3. Kolomanalyse
    if df is not None:
        kolom_lines = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            n_unique = df[col].nunique()
            top_vals = df[col].dropna().unique()[:20].tolist()
            top_str = ", ".join(str(v) for v in top_vals[:10])

            line = f"- {col} (dtype={dtype}, uniek={n_unique})"
            if n_unique <= 20:
                line += f" waarden: [{top_str}]"
            else:
                line += f" top: [{top_str}]"

            # Min/max bij numerieke kolommen
            if df[col].dtype.kind in ("i", "f", "u"):
                vmin, vmax = df[col].min(), df[col].max()
                line += f" range=[{vmin}..{vmax}]"

            kolom_lines.append(line)

        result["kolom_analyse"] = "\n".join(kolom_lines)

        # 4. Kolomdefinities uit glossary
        try:
            defs = _duo.column_definitions(list(df.columns))
            if defs:
                def_lines = [f"- {k}: {v}" for k, v in defs.items()]
                result["kolom_definities"] = "\n".join(def_lines)
        except Exception:
            pass

        # 5. Data sample (eerste 10 rijen als JSON)
        sample = df.head(10).to_dict(orient="records")
        result["data_sample"] = json.dumps(sample, ensure_ascii=False, indent=2, default=str)
    else:
        result["kolom_analyse"] = "Kon data niet laden"
        result["data_sample"] = "Niet beschikbaar"

    return result


def verrijk_duo_entry(
    entry: dict,
    client: httpx.Client,
    base_url: str,
    model: str,
) -> dict:
    """Verrijk één DUO-entry met LLM-analyse."""
    dataset_id = entry.get("_ckan_id", "onbekend")
    naam = entry.get("bron", dataset_id)

    # Data ophalen en analyseren
    analyse = analyseer_duo(entry)
    if analyse is None:
        print(f"    Kan geen data ophalen voor {dataset_id}, sla over")
        return entry

    # LLM-prompt samenstellen
    user_msg = DUO_USER_TEMPLATE.format(
        bron=entry.get("bron", ""),
        beschrijving=entry.get("beschrijving", ""),
        categorie=entry.get("categorie", ""),
        periode=entry.get("periode", ""),
        onderwijstype=", ".join(entry.get("onderwijstype", [])) if isinstance(entry.get("onderwijstype"), list) else str(entry.get("onderwijstype", "")),
        resources_overview=analyse["resources_overview"],
        kolom_analyse=analyse["kolom_analyse"],
        n_rows=analyse["n_rows"],
        data_sample=analyse["data_sample"],
        kolom_definities=analyse["kolom_definities"] or "Geen definities beschikbaar",
    )

    # LLM aanroepen
    result = _call_llm(client, base_url, model, user_msg)
    if result is None:
        print(f"    LLM-fout voor {dataset_id}, sla over")
        return entry

    # Resultaat toevoegen aan entry
    for key in ("samenvatting", "voorbeeldvragen", "tags", "niet_geschikt_voor",
                "kolomtoelichting", "waardenbereik", "combineerbaar_met"):
        if key in result:
            entry[key] = result[key]

    return entry


# ─── RIO-analyse ────────────────────────────────────────────────────────────


def analyseer_rio(entry: dict) -> dict | None:
    """Haal data op en analyseer een RIO-resource."""
    from riodata import fetch

    resource_name = entry.get("_rio_resource")
    if not resource_name:
        return None

    result = {
        "veld_overzicht": "",
        "voorbeeld_records": "",
        "n_samples": 0,
    }

    # Voorbeeldrecords ophalen
    try:
        records = fetch(resource_name, page=0, pageSize=10)
        result["n_samples"] = len(records)
    except Exception as e:
        print(f"    FOUT bij ophalen {resource_name}: {e}")
        return None

    if not records:
        print(f"    Geen records gevonden voor {resource_name}")
        return None

    # Veldanalyse
    field_types = {}
    for record in records:
        for key, value in record.items():
            if key not in field_types:
                if value is None:
                    field_types[key] = "None"
                elif isinstance(value, list):
                    field_types[key] = "list"
                elif isinstance(value, dict):
                    field_types[key] = "dict"
                elif isinstance(value, bool):
                    field_types[key] = "bool"
                elif isinstance(value, int):
                    field_types[key] = "int"
                elif isinstance(value, float):
                    field_types[key] = "float"
                else:
                    field_types[key] = "str"

    veld_lines = [f"- {k}: {v}" for k, v in field_types.items()]
    result["veld_overzicht"] = "\n".join(veld_lines)

    # Records als JSON (beperkt tot 3 voorbeeldrecords)
    sample = records[:3]
    result["voorbeeld_records"] = json.dumps(sample, ensure_ascii=False, indent=2, default=str)

    return result


def verrijk_rio_entry(
    entry: dict,
    client: httpx.Client,
    base_url: str,
    model: str,
) -> dict:
    """Verrijk één RIO-entry met LLM-analyse."""
    resource_name = entry.get("_rio_resource", "onbekend")
    naam = entry.get("bron", resource_name)

    # Data ophalen en analyseren
    analyse = analyseer_rio(entry)
    if analyse is None:
        print(f"    Kan geen data ophalen voor {resource_name}, sla over")
        return entry

    # LLM-prompt samenstellen
    filters_str = ", ".join(entry.get("filters", [])) or "geen"
    sub_str = ", ".join(entry.get("sub_resources", [])) or "geen"

    user_msg = RIO_USER_TEMPLATE.format(
        bron=entry.get("bron", ""),
        beschrijving=entry.get("beschrijving", ""),
        categorie=entry.get("categorie", ""),
        periode=entry.get("periode", ""),
        filters=filters_str,
        sub_resources=sub_str,
        n_samples=analyse["n_samples"],
        veld_overzicht=analyse["veld_overzicht"],
        voorbeeld_records=analyse["voorbeeld_records"],
    )

    # LLM aanroepen
    result = _call_llm(client, base_url, model, user_msg)
    if result is None:
        print(f"    LLM-fout voor {resource_name}, sla over")
        return entry

    # Resultaat toevoegen aan entry
    for key in ("samenvatting", "voorbeeldvragen", "tags", "niet_geschikt_voor",
                "kolomtoelichting", "waardenbereik", "combineerbaar_met"):
        if key in result:
            entry[key] = result[key]

    return entry


# ─── Tussentijds opslaan ───────────────────────────────────────────────────


def save_json(data: list, path: Path) -> None:
    """Sla lijst op als JSON-bestand."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: Path) -> list:
    """Laad JSON-bestand."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─── Hoofdprogramma ────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Verrijkt DUO- en RIO-catalogus-entries met LLM-analyse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  uv run python catalogus/verrijk_catalogus.py --source duo --base-url http://localhost:11434/v1 --model big-pickle
  uv run python catalogus/verrijk_catalogus.py --source rio --base-url http://localhost:11434/v1 --model big-pickle
  uv run python catalogus/verrijk_catalogus.py --source all --limit 5
  uv run python catalogus/verrijk_catalogus.py --no-skip-existing --source duo
        """,
    )
    parser.add_argument(
        "--source", choices=["duo", "rio", "all"], default="all",
        help="Welke bron te verrijken (standaard: all)",
    )
    parser.add_argument(
        "--base-url", default="http://localhost:11434/v1",
        help="Basis-URL van de OpenAI-compatible LLM API (standaard: http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--model", default="big-pickle",
        help="Modelnaam voor de LLM (standaard: big-pickle)",
    )
    parser.add_argument(
        "--output-dir", default="src/riodata/data/",
        help="Map voor uitvoerbestanden (standaard: src/riodata/data/)",
    )
    parser.add_argument(
        "--skip-existing", action="store_true", default=True,
        help="Sla entries over die al een samenvatting key hebben (standaard: aan)",
    )
    parser.add_argument(
        "--no-skip-existing", action="store_true",
        help="Sla geen entries over, verrijk alles opnieuw",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Verwerk maximaal N entries (handig voor testen)",
    )

    args = parser.parse_args()

    # Bepaal skip-gedrag
    skip_existing = args.skip_existing and not args.no_skip_existing

    output_dir = Path(args.output_dir)

    # HTTP-client aanmaken
    http_client = httpx.Client()

    # ─── DUO ────────────────────────────────────────────────────────────
    if args.source in ("duo", "all"):
        print(f"=== DUO datasets verrijken ===")
        print(f"Input:  {DUO_INPUT}")
        print(f"Output: {output_dir / 'duo_resources_enriched.json'}")
        print()

        duo_data = load_json(DUO_INPUT)
        total = len(duo_data)
        if args.limit:
            total = min(total, args.limit)

        enriched = 0
        skipped = 0
        failed = 0

        for i, entry in enumerate(duo_data[:total]):
            dataset_id = entry.get("_ckan_id", "onbekend")
            naam = entry.get("bron", dataset_id)

            # Check of al verrijkt
            if skip_existing and "samenvatting" in entry:
                skipped += 1
                continue

            print(f"Verrijken {i + 1}/{total}: {naam}...")

            try:
                entry = verrijk_duo_entry(entry, http_client, args.base_url, args.model)
                enriched += 1
            except Exception as e:
                print(f"    FOUT: {e}")
                failed += 1

            # Tussentijds opslaan na elke entry
            save_json(duo_data, output_dir / "duo_resources_enriched.json")

        print(f"\nDUO klaar: {enriched} verrijkt, {skipped} overgeslagen, {failed} gefaald")
        save_json(duo_data, output_dir / "duo_resources_enriched.json")

    # ─── RIO ────────────────────────────────────────────────────────────
    if args.source in ("rio", "all"):
        print(f"\n=== RIO resources verrijken ===")
        print(f"Input:  {RIO_INPUT}")
        print(f"Output: {output_dir / 'rio_resources_enriched.json'}")
        print()

        rio_data = load_json(RIO_INPUT)
        total = len(rio_data)
        if args.limit:
            total = min(total, args.limit)

        enriched = 0
        skipped = 0
        failed = 0

        for i, entry in enumerate(rio_data[:total]):
            resource_name = entry.get("_rio_resource", "onbekend")
            naam = entry.get("bron", resource_name)

            # Check of al verrijkt
            if skip_existing and "samenvatting" in entry:
                skipped += 1
                continue

            print(f"Verrijken {i + 1}/{total}: {naam}...")

            try:
                entry = verrijk_rio_entry(entry, http_client, args.base_url, args.model)
                enriched += 1
            except Exception as e:
                print(f"    FOUT: {e}")
                failed += 1

            # Tussentijds opslaan na elke entry
            save_json(rio_data, output_dir / "rio_resources_enriched.json")

        print(f"\nRIO klaar: {enriched} verrijkt, {skipped} overgeslagen, {failed} gefaald")
        save_json(rio_data, output_dir / "rio_resources_enriched.json")

    http_client.close()
    print("\nAlle verrijkingen voltooid.")


if __name__ == "__main__":
    main()
