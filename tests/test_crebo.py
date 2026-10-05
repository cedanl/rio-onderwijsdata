"""CREBO-loader: XLSX-fixture, normalisatie, cache en lookup (zonder netwerk)."""
import datetime as dt
import io

import pytest

openpyxl = pytest.importorskip("openpyxl")

from riodata import crebo, sbb  # noqa: E402


def xlsx(rijen, koppen=("Crebocode", "Naam", "Niveau", "Ingangsdatum", "Einddatum")):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(koppen))
    for r in rijen:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def groot(extra=()):
    basis = [(f"{25000 + i}", f"Opleiding {i}", 4, dt.date(2020, 8, 1), None) for i in range(120)]
    return xlsx(basis + list(extra))


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("RIODATA_CACHE", str(tmp_path))


class FakeClient:
    def __init__(self, content, ctype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        self.content, self.ctype = content, ctype

    def get(self, url, **kw):
        c = self

        class R:
            content = c.content
            headers = {"content-type": c.ctype}

            def raise_for_status(self):
                pass
        return R()


def test_voorloopnullen_ontbrekende_waarden_en_dubbelen_blijven():
    inhoud = xlsx([
        ("01234", "Met nul", None, None, None),       # string met voorloopnul
        (25604.0, "Numeriek", "3", dt.date(2021, 8, 1), dt.date(2024, 7, 31)),
        ("25604", "Numeriek v2", "3", dt.date(2024, 8, 1), None),   # dubbele code, ander cohort
        ("30000", None, None, None, None),            # ontbrekende naam
    ])
    lijst = crebo.parse_xlsx(inhoud, "test")
    codes = [r["crebo"] for r in lijst.rijen]
    assert codes == ["01234", "25604", "25604", "30000"]
    assert lijst.rijen[0]["niveau"] is None and lijst.rijen[3]["naam"] is None
    assert lijst.rijen[1]["geldig_tot"] == "2024-07-31"
    assert lijst.rijen[0]["bron"]["Crebocode"] == "01234"   # bronkolommen bewaard


def test_onbekende_kolommen_geven_schemafout_met_kolomnamen():
    with pytest.raises(crebo.CreboSchemaFout, match="Aanwezige kolommen"):
        crebo.parse_xlsx(xlsx([("1", "x")], koppen=("A", "B")), "test")


def test_lookup_found_not_found_ambiguous():
    lijst = crebo.parse_xlsx(xlsx([
        ("25604", "Oud", "3", dt.date(2021, 8, 1), dt.date(2024, 7, 31)),
        ("25604", "Nieuw", "3", dt.date(2024, 8, 1), None),
        ("25000", "Enkel", "4", None, None),
    ]), "test")
    assert crebo.zoek("99999", lijst)["status"] == "not_found"
    assert crebo.zoek("25000", lijst)["status"] == "found"
    amb = crebo.zoek("25604", lijst)
    assert amb["status"] == "ambiguous" and [m["naam"] for m in amb["matches"]] == ["Oud", "Nieuw"]
    # met peildatum wordt het precies één geldige rij
    r = crebo.zoek("25604", lijst, peildatum="2022-01-01")
    assert r["status"] == "found" and r["matches"][0]["naam"] == "Oud"
    assert r["editie"] == "test"


def test_latest_zonder_gevalideerde_editie_valt_niet_terug():
    with pytest.raises(crebo.CreboEditieOnbekend, match="ververs"):
        crebo.laad("latest")
    with pytest.raises(crebo.CreboEditieOnbekend):
        crebo.zoek("25604")


def test_ververs_cachet_en_latest_is_nieuwste_gecontroleerde():
    crebo.ververs("codelijst_2025_april", client=FakeClient(groot([("77777", "Speciaal", 2, None, None)])))
    m = crebo.manifest()["codelijst_2025_april"]
    assert m["rijen"] == 121 and len(m["sha256"]) == 64 and m["bron_url"].endswith("/58136")
    r = crebo.zoek("77777")
    assert r["status"] == "found" and r["editie"] == "codelijst_2025_april" and r["gecontroleerd_op"]


def test_afgekeurde_editie_komt_niet_in_manifest():
    kort = xlsx([("25604", "Te klein", 3, None, None)])
    with pytest.raises(crebo.CreboSchemaFout, match="rijen"):
        crebo.ververs("codelijst_2025_april", client=FakeClient(kort))
    assert crebo.manifest() == {}
    with pytest.raises(crebo.CreboSchemaFout, match="contenttype"):
        crebo.ververs("codelijst_2025_april", client=FakeClient(groot(), ctype="text/html"))
    with pytest.raises(crebo.CreboSchemaFout, match="signatuur|leesbaar"):
        crebo.ververs("codelijst_2025_april", client=FakeClient(b"<html>fout</html>"))
    assert crebo.manifest() == {}


def test_onbekende_editie():
    with pytest.raises(crebo.CreboEditieOnbekend, match="Bekend"):
        crebo.ververs("codelijst_1999", client=FakeClient(b""))


def test_gewijzigd_cachebestand_wordt_geweigerd():
    crebo.ververs("codelijst_2025_april", client=FakeClient(groot()))
    (crebo.cache_dir() / "codelijst_2025_april.xlsx").write_bytes(groot([("1", "x", 1, None, None)]))
    with pytest.raises(crebo.CreboSchemaFout, match="checksum"):
        crebo.laad("latest")


def test_loaderconfig_komt_uit_catalogus():
    cat = {r["_sbb_id"]: {x["naam"]: x["output_id"] for x in r["_resources"]} for r in sbb.catalog()}
    for ds, res in cat.items():
        assert {r["naam"]: r["output_id"] for r in sbb.resources(ds)} == res


@pytest.mark.skipif(not __import__("os").environ.get("RIODATA_LIVE"), reason="live-test: zet RIODATA_LIVE=1")
def test_live_smoke_nieuwe_editie_wordt_pas_vrijgegeven_na_validatie():
    """Niet lokaal gedraaid (geen netwerk bij ontwikkeling): controleert contenttype, kolommen en omvang."""
    lijst = crebo.ververs("codelijst_2025_april")
    assert lijst.rijen and crebo.manifest()["codelijst_2025_april"]["rijen"] == len(lijst.rijen)
