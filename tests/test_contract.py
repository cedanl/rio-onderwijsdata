"""Contracttests voor riodata.contract (RIO-03), offline."""
import json

import pytest

import riodata
from riodata import contract as c
from riodata._resolutie import AmbigueResource, ResourceIndexFout, ResourceNietGevonden, kies


def test_alle_records_geldig_en_alle_providers():
    records = c.catalog_records(compact=False)
    assert {r["dataset_id"].split(":")[0] for r in records} == set(c.PROVIDERS)
    assert len(records) == len(riodata.catalog(source="all"))
    for r in records:
        assert c.valideer_record(r) == [], r["dataset_id"]


def test_ids_uniek_en_aliases_blijven_werken():
    ids = [r["dataset_id"] for r in c.catalog_records()]
    assert len(ids) == len(set(ids))
    assert c.get_dataset("p01hoinges")["dataset_id"] == "duo:p01hoinges"
    assert c.get_dataset("rio:onderwijslocaties")["aliases"] == ["onderwijslocaties"]
    assert c.get_dataset("AIS2030")["dataset_id"] == "roa:ais2030"
    with pytest.raises(c.DatasetNietGevonden):
        c.get_dataset("duo:bestaat-niet")


def test_sectorprofiel_laat_alleen_passende_records_toe():
    for s in c.SECTOREN:
        for r in c.catalog_records(sector=s):
            assert r["scopeprofiel"][s] == c.SUPPORTED
    mbo = {r["dataset_id"] for r in c.catalog_records(sector="mbo")}
    assert "duo:mbo-studenten-per-instelling" in mbo  # DCAT-thema bve + titel
    assert "inspectie:oordelen" not in mbo  # scopebesluit RIO-05
    assert not any(i.startswith(("duo:p0", "roa:", "uwv:")) for i in mbo)


def test_rio_registers_niet_integraal_mbo():
    r = c.get_dataset("rio:aangeboden-opleidingen")
    assert r["scopeprofiel"]["mbo"] == c.SUPPORTED
    sel = r["sectorselectie"]["mbo"]
    assert sel["verplicht"] is True and sel["filter"] == "type"
    assert all(w.startswith("AANGEBODENMBO") for w in sel["waarden"])
    # Register zonder sectorfilter: onbekend, staat in scope_review
    org = c.get_dataset("rio:organisatorische-eenheden")
    assert set(org["scopeprofiel"].values()) == {c.UNKNOWN}
    assert "rio:organisatorische-eenheden" in {x["dataset_id"] for x in c.scope_review()}


def test_ho_breed_hbo_en_wo_onderscheiden():
    for r in c.catalog_records(provider="rio", compact=False):
        assert r["scopeprofiel"]["hbo"] != c.SUPPORTED and r["scopeprofiel"]["wo"] != c.SUPPORTED
    rio = c.get_dataset("rio:aangeboden-opleidingen")
    assert rio["ho_breed"]["status"] == c.SUPPORTED
    assert rio["sectorselectie"]["hbo"]["soort"] == "niet_beschikbaar"

    p01 = c.get_dataset("duo:p01hoinges")
    hbo, wo = p01["sectorselectie"]["hbo"], p01["sectorselectie"]["wo"]
    assert hbo["verplicht"] and wo["verplicht"]
    assert not set(hbo["resource_ids"]) & set(wo["resource_ids"])
    per_id = {x["resource_id"]: x for x in p01["resources"]}
    assert all("hoger beroepsonderwijs" in per_id[i]["naam"] for i in hbo["resource_ids"])
    assert all("wetenschappelijk" in per_id[i]["naam"] for i in wo["resource_ids"])


def test_rijselectie_hbo_wo_uit_volledige_scan():
    r = c.get_dataset("duo:adressen_ho")
    sel = r["sectorselectie"]["hbo"]
    assert sel["soort"] == "rijen" and sel["verplicht"]
    assert {(x["kolom"], x["waarde"]) for x in sel["selecties"]} == {("SOORT HO", "hbo")}


def test_onbekende_of_brede_labels_geven_geen_toelating():
    assert c._scope_uit_types({"allen"}) == {s: c.UNKNOWN for s in c.SECTOREN}
    assert c._scope_uit_types(set()) == {s: c.UNKNOWN for s in c.SECTOREN}
    assert c._scope_uit_types({"ho"}) == {"mbo": c.UNSUPPORTED, "hbo": c.UNKNOWN, "wo": c.UNKNOWN}
    assert c._scope_uit_types({"vo", "mbo"})["mbo"] == c.UNKNOWN
    assert c._scope_uit_types({"po"}) == {s: c.UNSUPPORTED for s in c.SECTOREN}


def test_resource_ids_stabiel_bij_herordening():
    items = [{"naam": "a", "id": "u1"}, {"naam": "b", "id": "u2"}, {"naam": "c", "id": "u3"}]
    omgekeerd = list(reversed(items))
    for rid in ("u1", "u2", "u3"):
        assert kies(items, rid, "x") == kies(omgekeerd, rid, "x")


def test_get_resource_op_uuid_met_schema():
    res = c.get_resource("duo:p01hoinges", "b88721ef-9787-4299-afc7-5d74380d29ba")
    assert res["sector"] == "wo" and res["id_soort"] == "ckan_uuid"
    assert res["schema_details"]["inspectie"]["status"] == "ok"
    assert c.get_resource("roa:ais2030", "566770")["naam"] == "uitkomsten"
    assert c.get_resource("sbb:crebolijst", "58909")["naam"] == "codelijst_2026_april"


def test_ambigue_substring_geeft_opties():
    with pytest.raises(AmbigueResource) as e:
        c.get_resource("duo:p01hoinges", "wetenschappelijk")
    assert len(e.value.opties) == 3
    assert all("id" in o and "naam" in o for o in e.value.opties)
    assert isinstance(e.value, ValueError)  # bestaande except ValueError blijft werken


def test_index_validatie():
    items = [{"naam": "a"}, {"naam": "b"}]
    for fout in (-1, 2, 99):
        with pytest.raises(ResourceIndexFout):
            kies(items, fout, "x")
    with pytest.raises(IndexError):  # achterwaarts compatibel
        kies(items, -1, "x")
    with pytest.raises(TypeError):
        kies(items, True, "x")
    with pytest.raises(ResourceNietGevonden):
        kies(items, "zzz", "x")


def test_loaders_gebruiken_dezelfde_resolutie(monkeypatch):
    from riodata import roa, sbb
    with pytest.raises(ResourceIndexFout):
        roa._pick_file_id(roa._get_meta("ais2030"), -1, "ais2030")
    with pytest.raises(AmbigueResource):
        sbb._pick_resource(sbb.resources("crebolijst"), "codelijst_2025", "crebolijst")
    assert sbb._pick_resource(sbb.resources("crebolijst"), "codelijst_2026", "crebolijst")["output_id"] == 58909


def test_roa_loader_en_catalogus_een_bron():
    from riodata import roa
    for rec in riodata.catalog(source="roa"):
        meta = roa._get_meta(rec["_roa_id"])
        assert meta["resources"] == {x["naam"]: x["file_id"] for x in rec["_resources"]}


def test_compact_klein_details_op_verzoek():
    compact = c.catalog_records(sector="mbo")
    assert all("beperkingen" not in r and "schema" not in r["resources"][0] for r in compact if r["resources"])
    assert len(json.dumps(compact)) < 80_000
    detail = c.get_dataset("duo:p01hoinges")
    assert detail["resources"][0]["schema"]["status"] == c.SUPPORTED


def test_verkeerde_resource_of_populatie_detecteerbaar():
    """Sector, teleenheid en capability zijn velden, geen tekst om te interpreteren."""
    p01 = c.get_dataset("duo:p01hoinges")
    assert p01["teldefinitie"]["teleenheid"] == "personen"
    assert p01["maat"] == {"status": c.SUPPORTED, "eenheid": "personen", "bron": "CKAN notes"}
    pdf = [r for r in c.get_dataset("duo:overzicht-erkenningen-ho")["resources"] if r["format"] != "CSV"]
    assert pdf and all(r["capabilities"] == ["metadata_only"] for r in pdf)
    sbb = c.get_dataset("sbb:kwalificatiedossiers-xml")
    assert "xml_download" in sbb["capabilities"]


def test_onbekend_nooit_als_lege_lijst():
    for r in c.catalog_records(compact=False):
        if r["geografie"]["status"] == c.UNKNOWN:
            assert r["geografie"]["niveaus"] is None
        for veld in ("populatie", "teldefinitie", "tijdsdekking"):
            if r[veld]["status"] == c.UNKNOWN:
                assert r[veld].get("reden")


def test_manifest_offline():
    m = c.catalog_manifest()
    assert m["aantal"] == 77 and sum(m["aantal_per_provider"].values()) == 77
    assert m["package_versie"] == riodata.__version__
    assert m["duo_resource_schemas"]["schema_versie"] == 1
    with pytest.raises(c.OnbekendSchema):
        c.catalog_records(schema_version=2)
