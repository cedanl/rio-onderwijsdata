"""Pakketdata: alle JSON-assets zijn parsebaar en elke bron levert een catalogus."""
import json
from importlib.resources import files

import pytest

import riodata

BRONNEN = ["rio", "duo", "roa", "uwv", "inspectie", "sbb"]


def test_alle_json_assets_zijn_geldig():
    bestanden = [f for f in files("riodata.data").iterdir() if f.name.endswith(".json")]
    assert len(bestanden) >= 9
    for f in bestanden:
        assert isinstance(json.loads(f.read_text(encoding="utf-8")), list), f.name


@pytest.mark.parametrize("bron", BRONNEN)
def test_elke_bron_levert_records(bron):
    assert riodata.catalog(source=bron)


def test_all_is_som_van_de_bronnen():
    assert len(riodata.catalog(source="all")) == sum(len(riodata.catalog(source=b)) for b in BRONNEN)
