"""
Verrijkt DUO- en RIO-catalogus met gestructureerde metadata uit de echte data.
Puur Python — geen LLM nodig. Haalt per dataset kolommen, types en
voorbeeldwaarden op.

Gebruik:
  uv run python catalogus/verrijk_catalogus.py --source duo
  uv run python catalogus/verrijk_catalogus.py --source rio
  uv run python catalogus/verrijk_catalogus.py --source all
  uv run python catalogus/verrijk_catalogus.py --source duo --limit 5
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DATA_DIR = Path(__file__).parent.parent / "src" / "riodata" / "data"
DUO_INPUT = DATA_DIR / "duo_resources.json"
RIO_INPUT = DATA_DIR / "rio_resources_ai.json"
DUO_OUTPUT = DATA_DIR / "duo_resources_enriched.json"
RIO_OUTPUT = DATA_DIR / "rio_resources_enriched.json"

TOP_N_VALUES = 25


def parse_args():
    p = argparse.ArgumentParser(description="Verrijkt DUO/RIO catalogus met data-metadata.")
    p.add_argument("--source", choices=["duo", "rio", "all"], default="all")
    p.add_argument("--no-skip-existing", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    return p.parse_args()


def load_json(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data: list, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── DUO ──────────────────────────────────────────────────────────────────


def enrich_duo_entry(entry: dict) -> dict:
    """Verrijk één DUO entry met kolommen, types en top-waarden uit de echte data."""
    from riodata import duo as _duo

    dataset_id = entry.get("_ckan_id")
    if not dataset_id:
        return entry

    try:
        resources = _duo.resources(dataset_id)
    except Exception as e:
        print(f" WARN resources: {e}", end="")
        resources = []

    if not resources:
        return entry

    kolommen = {}
    kolomtypes = {}
    last_df_columns = []

    for res_idx, res in enumerate(resources[:5]):
        res_naam = res.get("naam", f"resource_{res_idx}")
        try:
            df = _duo.load(dataset_id, res_idx, nrows=200)
            last_df_columns = list(df.columns)
        except Exception as e:
            print(f" WARN {res_naam}: {e}", end="")
            continue

        res_kolommen = {}
        res_types = {}

        for col in df.columns:
            dtype = df[col].dtype
            non_null = df[col].dropna()

            if dtype.kind in ("i", "f", "u"):
                res_types[col] = "numeriek"
                if len(non_null) > 0:
                    res_kolommen[col] = f"numeriek (bereik: {non_null.min()}-{non_null.max()})"
                else:
                    res_kolommen[col] = "numeriek"
            else:
                uniques = non_null.unique()
                n_unique = len(uniques)
                res_types[col] = f"categorie ({n_unique} waarden)"
                top_vals = [str(v) for v in uniques[:TOP_N_VALUES]]
                res_kolommen[col] = top_vals

        if len(resources) == 1:
            kolommen = res_kolommen
            kolomtypes = res_types
        else:
            kolommen[res_naam] = res_kolommen
            kolomtypes[res_naam] = res_types

    if kolommen:
        entry["_kolommen"] = kolommen
    if kolomtypes:
        entry["_kolomtypes"] = kolomtypes

    try:
        col_defs = _duo.column_definitions(last_df_columns) if last_df_columns else {}
        if col_defs:
            entry["_kolomdefinities"] = col_defs
    except Exception as e:
        print(f" WARN defs: {e}", end="")

    return entry


# ─── RIO ──────────────────────────────────────────────────────────────────


def enrich_rio_entry(entry: dict) -> dict:
    """Verrijk één RIO entry met veldnamen, types en voorbeeldwaarden."""
    from riodata import fetch

    resource_name = entry.get("_rio_resource")
    if not resource_name:
        return entry

    try:
        records = fetch(resource_name, page=0, pageSize=50)
    except Exception:
        return entry

    if not records:
        return entry

    velden = {}
    veldtypes = {}

    for record in records:
        for key, value in record.items():
            if key.startswith("_"):
                continue
            if key not in velden:
                velden[key] = set()
            if key not in veldtypes:
                veldtypes[key] = None

            if value is None:
                continue

            if veldtypes[key] is None:
                if isinstance(value, bool):
                    veldtypes[key] = "boolean"
                elif isinstance(value, int):
                    veldtypes[key] = "integer"
                elif isinstance(value, float):
                    veldtypes[key] = "float"
                elif isinstance(value, list):
                    veldtypes[key] = "lijst"
                elif isinstance(value, dict):
                    veldtypes[key] = "object"
                else:
                    veldtypes[key] = "tekst"

            if isinstance(value, (str, int, float, bool)):
                velden[key].add(str(value))

    kolommen = {}
    for key, values in velden.items():
        sorted_vals = sorted(values)
        if len(sorted_vals) <= TOP_N_VALUES:
            kolommen[key] = sorted_vals
        else:
            kolommen[key] = sorted_vals[:TOP_N_VALUES]

    if kolommen:
        entry["_kolommen"] = kolommen
    if veldtypes:
        entry["_kolomtypes"] = {k: v or "onbekend" for k, v in veldtypes.items()}

    return entry


# ─── Main ─────────────────────────────────────────────────────────────────


def process_source(entries, enrich_fn, output_path, args, source_name):
    existing = {}
    if output_path.exists():
        existing_list = load_json(output_path)
        for e in existing_list:
            eid = e.get("_ckan_id") or e.get("_rio_resource")
            if eid:
                existing[eid] = e

    processed = 0
    skipped = 0
    failed = 0

    for idx, entry in enumerate(entries, 1):
        entry_id = entry.get("_ckan_id") or entry.get("_rio_resource") or str(idx)

        if not args.no_skip_existing and entry_id in existing and existing[entry_id].get("_kolomtypes"):
            skipped += 1
            continue

        if args.limit is not None and processed >= args.limit:
            break

        processed += 1
        naam = entry.get("bron", entry_id)
        print(f"[{idx}/{len(entries)}] {naam[:60]}", end="", flush=True)

        try:
            enriched = enrich_fn(dict(entry))
            existing[entry_id] = enriched
            n_cols = len(enriched.get("_kolommen", {}))
            print(f" OK ({n_cols} kolommen)")
        except Exception as e:
            print(f" FOUT: {e}")
            failed += 1
            continue

        if processed % 5 == 0:
            _save(entries, existing, output_path)

    _save(entries, existing, output_path)
    print(f"\n{source_name}: {processed} verrijkt, {skipped} overgeslagen, {failed} mislukt")


def _save(entries, existing, output_path):
    output_list = []
    for e in entries:
        eid = e.get("_ckan_id") or e.get("_rio_resource")
        output_list.append(existing.get(eid, e))
    save_json(output_list, output_path)


def main():
    args = parse_args()

    if args.source in ("duo", "all"):
        print("=== DUO datasets ===")
        duo_data = load_json(DUO_INPUT)
        process_source(duo_data, enrich_duo_entry, DUO_OUTPUT, args, "DUO")

    if args.source in ("rio", "all"):
        print("\n=== RIO resources ===")
        rio_data = load_json(RIO_INPUT)
        process_source(rio_data, enrich_rio_entry, RIO_OUTPUT, args, "RIO")

    print("\nKlaar.")


if __name__ == "__main__":
    main()
