"""SBB-dossierlaag: veilig parsen, hiërarchie, CREBO-koppeling en passages (fixtures volgen het XSD)."""
import pytest

from riodata import sbb_xml

XML = """<?xml version="1.0" encoding="utf-8"?>
<sbb>
  <domeinen><domein nr="1" titel="Bouw en infra" crebo="79000" prijsfactor="1.0"/></domeinen>
  <sectorkamers><sectorkamer nr="3" titel="Sectorkamer Bouw"/></sectorkamers>
  <competenties><competentie nr="7" titel="Samenwerken" code="A1"/></competenties>
  <dossiers>
    <dossier nr="23045" titel="Betonboren" versie="1.0" status="vastgesteld" referentiedomein="1">
      <dossiercrebos><dossiercrebo ministerie="OCW" prijsfactor="1.3" Geldig_vanaf="2026-08-01"
        Datum_einde_instroom="" Datum_einde_opleiding="">23045</dossiercrebo></dossiercrebos>
      <kennisenvaardigheden><kennisofvaardigheid nr="11" titel="Betonkennis"/></kennisenvaardigheden>
      <voorblad><omschrijving><penvoerder><sectorkamer referentie="3"/></penvoerder></omschrijving></voorblad>
      <basis><basistaken><basiskerntaken>
        <kerntaak nr="1" titel="Werkt veilig" hoofdstuk="3.1">
          <complexiteit>Complex</complexiteit>
          <verantwoordelijkheid>Zelfstandig</verantwoordelijkheid>
          <basiswerkprocessen>
            <werkproces nr="11" titel="Bereidt voor" hoofdstuk="3.1.1">
              <werkprocesomschrijving>Bereidt het werk voor</werkprocesomschrijving>
              <werkprocesresultaat>Werkplek gereed</werkprocesresultaat>
              <werkprocesgedrag>Zorgvuldig</werkprocesgedrag>
              <werkprocescompetenties><competentie referentie="7"/></werkprocescompetenties>
            </werkproces>
          </basiswerkprocessen>
        </kerntaak>
      </basiskerntaken></basistaken></basis>
      <profielen>
        <profiel nr="2" titel="Betonboorder" niveau="3" beroepsgroep="Bouw">
          <omschrijving><soortopleiding>Vakopleiding</soortopleiding></omschrijving>
          <creboinformatie><crebo ministerie="OCW" Geldig_vanaf="2026-08-01">25078</crebo></creboinformatie>
          <profielkerntaken><kerntaak nr="5" titel="Boort beton">
            <complexiteit>Hoog</complexiteit><verantwoordelijkheid>Eigen</verantwoordelijkheid>
            <profielwerkprocessen><werkproces nr="51" titel="Boort"><werkprocesomschrijving>Boort gaten</werkprocesomschrijving>
            </werkproces></profielwerkprocessen></kerntaak></profielkerntaken>
        </profiel>
      </profielen>
    </dossier>
    <dossier nr="23046" titel="Ander dossier" versie="2.0" status="vastgesteld">
      <profielen><profiel nr="9" titel="X" niveau="4"><creboinformatie><crebo>25078</crebo></creboinformatie></profiel></profielen>
    </dossier>
  </dossiers>
</sbb>"""


def parse(xml=XML, **kw):
    return sbb_xml.parse_dossiers(xml.encode("utf-8") if isinstance(xml, str) else xml, "test", **kw)


def test_hierarchie_en_officiele_ids_blijven_behouden():
    d = parse()
    assert len(d.dossiers) == 2 and d.waarschuwingen == ()
    dos = d.dossiers[0]
    assert (dos["nr"], dos["titel"], dos["versie"], dos["status"]) == ("23045", "Betonboren", "1.0", "vastgesteld")
    assert dos["sectorkamer_ref"] == "3" and d.sectorkamers[0]["titel"] == "Sectorkamer Bouw"
    kt = dos["basiskerntaken"][0]
    assert kt["nr"] == "1" and kt["hoofdstuk"] == "3.1" and kt["werkprocessen"][0]["nr"] == "11"
    assert kt["werkprocessen"][0]["competentie_refs"] == ["7"] and d.competenties["7"]["titel"] == "Samenwerken"
    assert dos["profielen"][0]["profielkerntaken"][0]["werkprocessen"][0]["omschrijving"] == "Boort gaten"
    assert d.kennis[("23045", "11")] == "Betonkennis" and d.domeinen[0]["crebo"] == "79000"


def test_crebo_wordt_op_exacte_code_gekoppeld_met_editie_en_geldigheid():
    d = parse()
    r = sbb_xml.koppel_crebo("23045", d)
    assert r["status"] == "found" and r["editie"] == "test"
    assert r["matches"][0]["dossier_nr"] == "23045" and r["matches"][0]["geldig_vanaf"] == "2026-08-01"
    assert sbb_xml.koppel_crebo("99999", d)["status"] == "not_found"
    # naamgelijkenis telt niet: de naam van het dossier is geen sleutel
    assert sbb_xml.koppel_crebo("Betonboren", d)["status"] == "not_found"


def test_code_in_meerdere_dossiers_is_ambiguous():
    r = sbb_xml.koppel_crebo("25078", parse())
    assert r["status"] == "ambiguous"
    assert {m["dossier_nr"] for m in r["matches"]} == {"23045", "23046"}


def test_passages_houden_dossiercontext_en_pad():
    ps = sbb_xml.passages(parse())
    wp = next(p for p in ps if p["niveau"] == "werkproces" and p["nr"] == "11")
    assert wp["dossier_nr"] == "23045" and wp["editie"] == "test"
    assert "dossier 23045 Betonboren > kerntaak 1 Werkt veilig > werkproces 11 Bereidt voor" == wp["pad"]
    assert "Bereidt het werk voor" in wp["tekst"] and "Werkplek gereed" in wp["tekst"]
    assert all(p["dossier_nr"] and p["editie"] for p in ps)


def test_namespace_wordt_genegeerd():
    d = parse(XML.replace("<sbb>", '<sbb xmlns="urn:sbb:test">'))
    assert d.dossiers[0]["nr"] == "23045" and d.dossiers[0]["basiskerntaken"][0]["werkprocessen"]


def test_gewijzigde_structuur_geeft_fout_of_waarschuwing():
    with pytest.raises(sbb_xml.SbbXmlFout, match="Verwachte wortel"):
        parse("<root><dossiers/></root>")
    with pytest.raises(sbb_xml.SbbXmlFout, match="Geen <dossiers>"):
        parse("<sbb><iets/></sbb>")
    d = parse("<sbb><dossiers><dossier titel='zonder nr'/></dossiers></sbb>")
    assert any("zonder nr" in w for w in d.waarschuwingen)
    assert parse("<sbb><dossiers/></sbb>").waarschuwingen == ("<dossiers> bevat geen <dossier>",)


def test_onveilige_invoer_wordt_geweigerd():
    xxe = '<?xml version="1.0"?><!DOCTYPE sbb [<!ENTITY x SYSTEM "file:///etc/passwd">]><sbb><dossiers>&x;</dossiers></sbb>'
    with pytest.raises(sbb_xml.SbbXmlFout, match="DOCTYPE/ENTITY"):
        parse(xxe)
    bom = '<!DOCTYPE sbb [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><sbb><dossiers>&b;</dossiers></sbb>'
    with pytest.raises(sbb_xml.SbbXmlFout, match="DOCTYPE/ENTITY"):
        parse(bom)


def test_te_grote_en_kapotte_invoer():
    with pytest.raises(sbb_xml.SbbXmlFout, match="limiet"):
        parse(XML, max_bytes=100)
    with pytest.raises(sbb_xml.SbbXmlFout, match="niet te parseren"):
        parse("<sbb><dossiers>")
