"""Contracttests voor de RIO-filters: catalogus en spec mogen niet ongemerkt uiteenlopen."""
import importlib.util
import json
from importlib.resources import files
from pathlib import Path

import pytest

import riodata
from riodata import filtercontract, typewaarden, valideer_filters

ROOT = Path(__file__).resolve().parent.parent
CATALOGI = ("rio_resources.json", "rio_resources_ai.json", "rio_resources_enriched.json")


def _laad(naam):
    return json.loads(files("riodata.data").joinpath(naam).read_text(encoding="utf-8"))


@pytest.mark.parametrize("bestand", CATALOGI)
def test_catalogusfilters_komen_overeen_met_spec(bestand):
    """Extra of ontbrekende filters in de catalogus laten deze test falen."""
    res = filtercontract()["resources"]
    for r in _laad(bestand):
        spec = res[r["_rio_resource"]]
        verwacht = {f["naam"] for f in spec["filters"]} | {f["naam"] for f in spec.get("catalogus_zonder_spec", [])}
        assert set(r["filters"]) == verwacht, f"{bestand}: {r['_rio_resource']}"
        assert len(r["filters"]) == len(set(r["filters"]))


def test_alle_14_resources_in_contract():
    assert {r["_rio_resource"] for r in riodata.catalog("rio")} == set(filtercontract()["resources"])


def test_status_en_opleidingseenheidtype_beschikbaar():
    per_res = {r["_rio_resource"]: r["filters"] for r in riodata.catalog("rio")}
    assert "status" in per_res["aangeboden-opleiding-cohorten"]
    assert "opleidingseenheidtype" in per_res["opleidingen"]
    assert filtercontract()["resources"]["aangeboden-opleiding-cohorten"]["filters"]
    status = next(f for f in riodata.filtercontract()["resources"]["aangeboden-opleiding-cohorten"]["filters"]
                  if f["naam"] == "status")
    assert status["enum"] == ["O", "G"]


def test_bestaande_filters_blijven_staan():
    per_res = {r["_rio_resource"]: r["filters"] for r in riodata.catalog("rio")}
    assert per_res["aangeboden-opleiding-cohorten"][:5] == [
        "aangebodenOpleidingCohorttype", "aanmeldperiode", "beginAanmeldperiode",
        "eindeAanmeldperiode", "datumGeldigOp"]
    assert per_res["opleidingen"][0] == "datumGeldigOp"


def test_datumgeldigop_op_cohorten_is_gemarkeerd_als_niet_in_spec():
    res = filtercontract()["resources"]["aangeboden-opleiding-cohorten"]
    assert [f["naam"] for f in res["catalogus_zonder_spec"]] == ["datumGeldigOp"]
    assert "datumGeldigOp" not in {f["naam"] for f in res["filters"]}


def test_sort_zonder_schema_in_spec_is_vastgelegd():
    for res in filtercontract()["resources"].values():
        assert "sort" in res["paginering"]
        assert res["sort_schema_in_spec"] is False
        assert "sort" not in {f["naam"] for f in res["filters"]}


def test_contract_is_actueel_met_spec():
    """Het contractbestand moet gelijk zijn aan wat de generator nu uit de spec maakt."""
    pytest.importorskip("yaml")
    spec = importlib.util.spec_from_file_location("genereer", ROOT / "catalogus" / "genereer_filtercontract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    nieuw = mod.bouw_contract(ROOT / "RIO_LOD_API_v2.yml")
    assert nieuw == filtercontract(), "Draai catalogus/genereer_filtercontract.py opnieuw"


def test_enums_komen_uit_spec_en_niet_uit_voorbeelden():
    f = {x["naam"]: x for x in filtercontract()["resources"]["aangeboden-opleidingen"]["filters"]}
    assert len(f["type"]["enum"]) == 10
    assert f["datumGeldigOp"]["format"] == "date"
    assert f["onderwijslocatieId"]["enum"] is None


def test_mbo_selectie_volgt_spec_enum():
    waarden = typewaarden("aangeboden-opleidingen", "mbo")
    assert waarden == ["AANGEBODENMBOOPLEIDING", "AANGEBODENMBOOPLEIDINGSONDERDEEL"]
    opl = typewaarden("opleidingen", "mbo")
    assert "MBOKWALIFICATIE" in opl and all(w.startswith("MBO") for w in opl)
    assert not any(w.startswith("HO") for w in opl)


def test_ho_breed_en_geen_gegokt_hbo_wo():
    assert typewaarden("aangeboden-opleidingen", "ho") == [
        "AANGEBODENHOOPLEIDING", "AANGEBODENHOOPLEIDINGSONDERDEEL"]
    for sector in ("hbo", "wo"):
        with pytest.raises(ValueError, match="onderscheiden"):
            typewaarden("aangeboden-opleidingen", sector)


def test_typewaarden_onbekende_sector_en_resource():
    with pytest.raises(ValueError, match="Onbekend sector"):
        typewaarden("opleidingen", "vo-ish")
    with pytest.raises(ValueError, match="Onbekend resource"):
        typewaarden("opleidingn", "mbo")
    with pytest.raises(ValueError, match="geen type-filter"):
        typewaarden("examenlicenties", "mbo")


def test_valideer_geldig():
    assert valideer_filters("aangeboden-opleiding-cohorten", {"status": "O", "pageSize": 5}) == []


def test_valideer_geeft_herstelopties():
    (p,) = valideer_filters("aangeboden-opleiding-cohorten", {"status": "X"})
    assert p["probleem"] == "ongeldige waarde" and "O, G" in p["herstel"]
    (p,) = valideer_filters("opleidingen", {"opleidingseenheidtyp": "HOOPLEIDING"})
    assert "opleidingseenheidtype" in p["herstel"]
    (p,) = valideer_filters("opleidingen", {"datumGeldigOp": "01-01-2024"})
    assert p["probleem"] == "ongeldige datum" and "YYYY-MM-DD" in p["herstel"]


def test_valideer_catalogusfilter_zonder_spec_is_waarschuwing():
    (p,) = valideer_filters("aangeboden-opleiding-cohorten", {"datumGeldigOp": "2024-01-01"})
    assert p["probleem"] == "waarschuwing"
