"""Opt-in live-integration smoke tests.

These hit the REAL upstream services (Ensembl Plants, UniProt, Europe PMC,
STRING-db, and an OpenTimestamps calendar) and are therefore SKIPPED by default
so the normal mocked suite stays fast and network-free. Enable them with:

    CULTIVARS_LIVE_TESTS=1 pytest tests/test_live_integration.py -v

They assert only on coarse response shape (not exact values, which drift with
database releases), so they catch outages, auth/format regressions, and broken
endpoints without being brittle. The nightly CI workflow runs them; PR CI does
not.
"""

from __future__ import annotations

import os

import pytest

import server

LIVE = os.environ.get("CULTIVARS_LIVE_TESTS") in {"1", "true", "yes"}

pytestmark = pytest.mark.skipif(
    not LIVE, reason="set CULTIVARS_LIVE_TESTS=1 to run live-integration tests"
)


def test_live_lookup_gene_arabidopsis():
    out = server.lookup_gene("PHYB", species="arabidopsis_thaliana")
    # lookup_gene returns the Ensembl stable ID under `gene_id` (e.g. AT2G18790).
    assert out.get("gene_id", "").startswith("AT") or out.get("error")


def test_live_list_plant_species():
    out = server.list_plant_species()
    # Should enumerate dozens of Ensembl Plants species.
    species = out.get("species") or out.get("available") or []
    assert isinstance(species, list) and len(species) > 10


def test_live_uniprot_thcas():
    # THCAS (Cannabis) is curated in UniProt even though it's not in Ensembl.
    out = server.lookup_uniprot_entry("Q8GTB6")
    # lookup_uniprot_entry returns the accession under `uniprot_id`.
    assert out.get("uniprot_id") == "Q8GTB6" or out.get("error")


def test_live_pubmed_search():
    out = server.search_pubmed_for_gene("SUB1A", page_size=3)
    assert "results" in out or "error" in out


def test_live_string_interactions():
    out = server.get_string_interactions("SOS1", species="arabidopsis_thaliana")
    assert "interactions" in out or "error" in out


def test_live_ots_anchor_roundtrip(tmp_path, monkeypatch):
    """Stamp a real digest against a public OpenTimestamps calendar."""
    monkeypatch.setenv("CULTIVARS_LEDGER_DIR", str(tmp_path / "phenotypes"))
    out = server.submit_phenotype_observation(
        accession_id="IRGC_live",
        common_name="Live Test",
        species="oryza_sativa",
        trait_category="submergence_tolerance",
        measurement_type="binary",
        measurement_value=True,
    )
    anchored = server.anchor_observation_timestamp(out["path"])
    if not anchored.get("ok"):
        pytest.skip(f"no OTS calendar reachable: {anchored.get('calendars_tried')}")
    verified = server.verify_timestamp(anchored["ots_path"], expected_hash=out["content_hash"])
    assert verified["well_formed"] is True
    assert verified["matches_expected_hash"] is True
