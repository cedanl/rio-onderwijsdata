"""ROA/UWV-loaders: aparte fouten per stap, geen stille eenkolomstabel, herleidbare snapshot."""
import io
import zipfile

import pytest

pytest.importorskip("pandas")

from riodata import _lezen, roa, uwv  # noqa: E402

UWV_CSV = (
    "PEILDATUM;BEROEP_CD;REC_TYPE;AANTAL;OPLNIV_GEM\n"
    "2023-05-16;1;Vacature;5;3,5\n2023-05-16;2;Werkzoekende;7;2,5\n2023-05-09;3;Vacature;1;3,0\n"
).encode()


class Resp:
    def __init__(self, content, url="https://x/f"):
        self.content, self.url = content, url

    def raise_for_status(self):
        pass


def zip_van(naam, inhoud):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(naam, inhoud)
    return buf.getvalue()


def test_roa_leest_csv_met_herkomst(monkeypatch):
    csv = "opleiding;aantal\nA;1\nB;2\n".encode("utf-8")
    monkeypatch.setattr(roa.httpx, "get", lambda *a, **k: Resp(csv, "https://dv/1"))
    df = roa.load("ais2030", 0)
    assert list(df.columns) == ["opleiding", "aantal"]
    bron = df.attrs["bron"]
    assert bron["bron_url"] == "https://dv/1" and len(bron["sha256"]) == 64 and bron["encoding"] == "utf-8-sig"


def test_roa_latin1_wordt_nog_gedecodeerd(monkeypatch):
    csv = "naam;waarde\nCafé;1\n".encode("latin-1")
    monkeypatch.setattr(roa.httpx, "get", lambda *a, **k: Resp(csv))
    assert roa.load("ais2030", 0)["naam"][0] == "Café"


def test_verkeerde_separator_is_geen_succes(monkeypatch):
    csv = b"opleiding,aantal\nA,1\nB,2\n"
    monkeypatch.setattr(roa.httpx, "get", lambda *a, **k: Resp(csv))
    with pytest.raises(_lezen.SchemaFout, match="separator"):
        roa.load("ais2030", 0)


def test_parserfout_wordt_niet_als_decodeerfout_gemeld():
    kapot = b'a;b\n"niet gesloten;1\n'
    with pytest.raises(_lezen.ParserFout):
        _lezen.lees_csv(kapot, sep=";", engine="python")
    with pytest.raises(_lezen.ParserFout, match="niet te parseren"):
        _lezen.lees_csv(b"", sep=";")


def test_echt_ondecodeerbaar_geeft_decodeerfout(monkeypatch):
    monkeypatch.setattr(_lezen, "ENCODINGS", ("utf-8",))
    with pytest.raises(_lezen.DecodeerFout):
        _lezen.lees_csv(b"a;b\n\xff;1\n", sep=";")


def test_verwachte_kolommen_worden_afgedwongen():
    with pytest.raises(_lezen.SchemaFout, match="ontbreken"):
        _lezen.lees_csv(b"a;b\n1;2\n", sep=";", verwacht=("REC_TYPE",))


def test_oude_exceptietypes_blijven_bruikbaar():
    assert issubclass(_lezen.DecodeerFout, RuntimeError) and issubclass(_lezen.SchemaFout, ValueError)


def _uwv(monkeypatch, zipbytes):
    snap = {"naam": "n", "url": "https://x/uwv_20230516.zip", "created": "2023-05-16T00:00:00"}
    monkeypatch.setattr(uwv, "_get_snapshots", lambda: [snap])
    monkeypatch.setattr(uwv.httpx, "get", lambda *a, **k: Resp(zipbytes, snap["url"]))


def test_uwv_latest_geeft_werkelijke_peildatum_en_archiefstatus(monkeypatch):
    _uwv(monkeypatch, zip_van("data.csv", UWV_CSV))
    df = uwv.load()
    s = df.attrs["snapshot"]
    assert s["peildatum"] == "2023-05-16" and s["status"] == "historisch_archief"
    assert "geen actuele vacatures" in s["opmerking"]
    assert s["gevraagd"] == "latest" and s["bron_url"].endswith(".zip") and len(s["sha256"]) == 64


def test_uwv_rec_type_filter_behoudt_snapshotinfo(monkeypatch):
    _uwv(monkeypatch, zip_van("data.csv", UWV_CSV))
    df = uwv.load(rec_type="vacature")
    assert set(df["REC_TYPE"]) == {"Vacature"} and df.attrs["snapshot"]["peildatum"] == "2023-05-16"


def test_uwv_ontbrekende_csv_en_kapotte_zip(monkeypatch):
    _uwv(monkeypatch, zip_van("leesmij.txt", "x"))
    with pytest.raises(_lezen.ParserFout, match="Geen CSV"):
        uwv.load()
    _uwv(monkeypatch, b"geen zip")
    with pytest.raises(_lezen.ParserFout, match="geldige ZIP"):
        uwv.load()


def test_uwv_rec_type_zonder_kolom_is_schemafout(monkeypatch):
    _uwv(monkeypatch, zip_van("data.csv", "A;B\n1;2\n"))
    with pytest.raises(_lezen.SchemaFout, match="REC_TYPE"):
        uwv.load(rec_type="Vacature")


def test_uwv_limiet_op_uitgepakte_omvang(monkeypatch):
    monkeypatch.setattr(_lezen, "MAX_BYTES", 10)
    _uwv(monkeypatch, zip_van("data.csv", UWV_CSV))
    with pytest.raises(_lezen.LimietFout):
        uwv.load()
