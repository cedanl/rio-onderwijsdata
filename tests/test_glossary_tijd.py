"""Dataset-gebonden glossary en bewijsvlag voor _meest_recent."""
import re

import riodata
from riodata import duo

STARTJAAR_DATASETS = ("p01hoinges", "p02ho1ejrs", "p03hoinschr")


def test_zonder_dataset_blijft_gedrag_gelijk():
    defs = duo.column_definitions(["STUDIEJAAR", "ONBEKEND"])
    assert defs == {"STUDIEJAAR": duo.DUO_COLUMN_GLOSSARY["STUDIEJAAR"]}


def test_studiejaar_p01_p02_p03_is_startjaar():
    for ds in STARTJAAR_DATASETS:
        tekst = duo.column_definitions(["STUDIEJAAR"], ds)["STUDIEJAAR"]
        assert "Startjaar" in tekst and "2023 = studiejaar 2023/2024" in tekst
        assert "YYYY/YYYY" not in tekst


def test_scope_lekt_niet_naar_andere_datasets():
    assert duo.column_definitions(["STUDIEJAAR"], "functiemix")["STUDIEJAAR"] == duo.DUO_COLUMN_GLOSSARY["STUDIEJAAR"]
    assert duo.column_definitions(["STUDIEJAAR"], "p04andere")["STUDIEJAAR"] == duo.DUO_COLUMN_GLOSSARY["STUDIEJAAR"]
    assert duo.column_definitions(["OPLEIDINGSVORM"], "p01hoinges") == {}


def test_opleidingsvorm_codes_in_mbo_aanbod():
    tekst = duo.column_definitions(["OPLEIDINGSVORM"], "mbo_opleidingsaanbod")["OPLEIDINGSVORM"]
    assert all(c in tekst for c in ("VT = voltijd", "DT = deeltijd", "DU = duaal"))


def test_catalogus_kolomdefinities_gelijk_aan_scoped_glossary():
    """Catalogus en column_definitions() geven dezelfde definitie voor dezelfde dataset."""
    per_id = {r["_ckan_id"]: r for r in riodata.catalog("duo")}
    for ds in STARTJAAR_DATASETS:
        kd = per_id[ds]["_kolomdefinities"]
        assert kd["STUDIEJAAR"] == duo.column_definitions(["STUDIEJAAR"], ds)["STUDIEJAAR"]


def test_meest_recent_bewijs_klopt_met_de_naam():
    n = 0
    for r in riodata.catalog("duo"):
        if "_meest_recent" not in r:
            assert "_meest_recent_bewijs" not in r
            continue
        n += 1
        heeft_jaar = bool(re.search(r"\b20\d{2}\b", r["_meest_recent"]))
        assert r["_meest_recent_bewijs"] == ("jaartal_in_naam" if heeft_jaar else "geen")
    assert n == 30


def test_controlebestand_is_niet_autoritatief():
    r = next(r for r in riodata.catalog("duo") if r.get("_meest_recent") == "controlebestand")
    assert r["_meest_recent_bewijs"] == "geen"
