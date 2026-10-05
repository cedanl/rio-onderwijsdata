"""Tijdmetadata: gesplitste velden met bronzin, conflicten expliciet, geen verzonnen claims."""
import riodata


def duo(i):
    return next(r for r in riodata.catalog("duo") if r["_ckan_id"] == i)


def test_prognose_horizon_komt_uit_de_bron_en_oude_claim_blijft_zichtbaar():
    r = duo("studentprognoses-mbo-per-instelling")
    t = r["_tijd"]
    assert r["periode"] == "2021-2040" == t["periode"]["waarde"] and t["periode"]["soort"] == "prognose"
    assert "2021-2040" in t["periode"]["bronzin"]
    assert {"veld": "periode", "waarde": "2021-2030", "reviewstatus": "onjuist volgens bron (2021-2040)"} in t["eerdere_catalogusclaims"]


def test_editie_is_niet_het_voorspelde_jaar():
    t = duo("studentprognoses-mbo-per-instelling")["_tijd"]
    assert t["editie"]["publicatiedatum"] == "2026-04-29"
    assert "versie 1" in t["editie"]["versies"] and "versie 2" in t["editie"]["versies"]
    assert not t["periode"]["waarde"].startswith("2026")          # editiejaar != prognosehorizon
    assert "peildatum 01-10-2025" in t["peildatum"]["bronzin"]    # peildatum van de bron, apart veld


def test_verversingsconflict_is_expliciet():
    r = duo("studentprognoses-mbo-per-instelling")
    t = r["_tijd"]
    assert t["verversing"]["waarde"] == "twee keer per jaar" and "Twee keer" in r["frequentie"]
    (c,) = t["claims_in_conflict"]
    assert c["waarde"] == "jaarlijks" and "ANNUAL" in c["bron"] and c["reviewstatus"].startswith("conflict")


def test_mbo_aanbod_frequentie_is_dagelijks_met_bronzin():
    r = duo("mbo_opleidingsaanbod")
    assert r["frequentie"] == "Dagelijks" and r["_tijd"]["verversing"]["waarde"] == "dagelijks"
    assert "dagelijks geactualiseerd" in r["_tijd"]["verversing"]["bronzin"]
    assert r["_tijd"]["periode"]["waarde"] is None       # actueel overzicht, geen waarnemingsperiode
    assert r["_tijd"]["editie"] is None


def test_andere_records_hebben_geen_verzonnen_tijdclaims():
    met = {r["_ckan_id"] for r in riodata.catalog("duo") if "_tijd" in r}
    assert met == {"studentprognoses-mbo-per-instelling", "mbo_opleidingsaanbod"}


def test_elke_claim_heeft_herkomst():
    for i in ("studentprognoses-mbo-per-instelling", "mbo_opleidingsaanbod"):
        t = duo(i)["_tijd"]
        assert t["bron"]["url"].startswith("https://onderwijsdata.duo.nl/api/3/action/package_show")
        assert t["bron"]["opgehaald_op"] and t["reviewstatus"].startswith("bronverificatie")
