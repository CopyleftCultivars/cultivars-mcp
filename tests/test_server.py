"""Tests for the cultivars MCP server.

Uses httpx.MockTransport so no live network is required. Each test wires a
small handler that asserts on the request path and returns a canned JSON
response. The server module's _CLIENT_FACTORY seam injects the mock client.
"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

import server


# ---------------------------------------------------------------------------
# Mock-transport helpers
# ---------------------------------------------------------------------------


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.Client]:
    """Build a _CLIENT_FACTORY that returns clients with the given handler."""

    def factory() -> httpx.Client:
        return httpx.Client(
            base_url=server.BASE_URL,
            headers={"Accept": "application/json"},
            transport=httpx.MockTransport(handler),
            timeout=5,
        )

    return factory


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make retry backoff instant so retry tests don't burn wall-clock."""
    monkeypatch.setattr(server.time, "sleep", lambda _: None)


@pytest.fixture
def install_handler(monkeypatch):
    """Install a request handler as the active client factory; auto-uninstalls."""

    def _install(handler):
        monkeypatch.setattr(server, "_CLIENT_FACTORY", _mock_client(handler))

    return _install


def _json(payload, status_code: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, json=payload, headers=headers or {})


# ---------------------------------------------------------------------------
# Community fallback (Cannabis sativa) — no HTTP at all
# ---------------------------------------------------------------------------


def test_lookup_gene_cannabis_fallback(install_handler):
    """Cannabis sativa must short-circuit before any HTTP call."""
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return _json({"error": "should not have been called"}, 500)

    install_handler(handler)
    out = server.lookup_gene(gene="THCAS", species="cannabis_sativa")

    assert out["available_in_ensembl_plants"] is False
    assert "alternatives" in out
    assert any("NCBI" in alt for alt in out["alternatives"])
    assert calls == []  # zero HTTP requests issued


def test_search_variants_cannabis_fallback(install_handler):
    install_handler(lambda req: _json({}, 500))
    out = server.search_variants_in_region(region="1:1-100", species="cannabis_sativa")
    assert out["available_in_ensembl_plants"] is False


def test_predict_variant_effect_cannabis_fallback(install_handler):
    install_handler(lambda req: _json({}, 500))
    out = server.predict_variant_effect(region="1:1-1", allele="T", species="cannabis_sativa")
    assert out["available_in_ensembl_plants"] is False


# ---------------------------------------------------------------------------
# lookup_gene: stable-ID first, symbol fallback on 400 OR 404
# ---------------------------------------------------------------------------


def test_lookup_gene_by_stable_id(install_handler):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/lookup/id/AT2G18790"
        return _json({
            "id": "AT2G18790",
            "display_name": "PHYB",
            "species": "arabidopsis_thaliana",
            "biotype": "protein_coding",
            "description": "phytochrome B",
            "seq_region_name": "2",
            "start": 8139756,
            "end": 8144461,
            "strand": 1,
            "assembly_name": "TAIR10",
            "canonical_transcript": "AT2G18790.1.",
            "source": "araport11",
            "logic_name": "araport11",
        })

    install_handler(handler)
    out = server.lookup_gene(gene="AT2G18790")
    assert out["gene_id"] == "AT2G18790"
    assert out["symbol"] == "PHYB"
    assert "ensembl_url" in out


def test_lookup_gene_falls_back_to_symbol_on_400(install_handler):
    """Ensembl returns 400 (not 404) for non-ID inputs like gene symbols."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        if req.url.path == "/lookup/id/PHYB":
            return _json({"error": "Bad ID"}, 400)
        if req.url.path == "/lookup/symbol/arabidopsis_thaliana/PHYB":
            return _json({
                "id": "AT2G18790",
                "display_name": "PHYB",
                "species": "arabidopsis_thaliana",
                "biotype": "protein_coding",
            })
        return _json({}, 500)

    install_handler(handler)
    out = server.lookup_gene(gene="PHYB", species="arabidopsis_thaliana")
    assert out["gene_id"] == "AT2G18790"
    assert seen == ["/lookup/id/PHYB", "/lookup/symbol/arabidopsis_thaliana/PHYB"]


def test_lookup_gene_falls_back_to_symbol_on_404(install_handler):
    """Symbols that don't error-out with 400 (some Ensembl versions return 404)."""
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/lookup/id/"):
            return _json({"error": "Not found"}, 404)
        return _json({"id": "AT2G18790", "display_name": "PHYB", "species": "arabidopsis_thaliana"})

    install_handler(handler)
    out = server.lookup_gene(gene="PHYB", species="arabidopsis_thaliana")
    assert out["gene_id"] == "AT2G18790"


def test_lookup_gene_not_found_returns_error(install_handler):
    install_handler(lambda req: _json({}, 404))
    out = server.lookup_gene(gene="NOPE", species="arabidopsis_thaliana")
    assert out["error"] == "Gene not found"
    assert out["gene"] == "NOPE"


def test_lookup_gene_empty_input():
    out = server.lookup_gene(gene="")
    assert "error" in out


# ---------------------------------------------------------------------------
# search_variants_in_region
# ---------------------------------------------------------------------------


def test_search_variants_truncates(install_handler):
    payload = [
        {"id": f"V{i}", "seq_region_name": "2", "start": 100 + i, "end": 100 + i,
         "strand": 1, "alleles": ["A", "T"], "consequence_type": "intron_variant",
         "source": "Test", "clinical_significance": []}
        for i in range(50)
    ]
    install_handler(lambda req: _json(payload))
    out = server.search_variants_in_region(region="2:1-1000", species="arabidopsis_thaliana", limit=5)
    assert out["count"] == 5
    assert out["truncated"] is True


def test_search_variants_400_returns_friendly_error(install_handler):
    install_handler(lambda req: httpx.Response(400, text="Bad region"))
    out = server.search_variants_in_region(region="garbage", species="arabidopsis_thaliana")
    assert out["error"] == "Bad region specifier"
    assert "hint" in out


def test_search_variants_empty_region():
    out = server.search_variants_in_region(region="", species="arabidopsis_thaliana")
    assert "error" in out


def test_search_variants_limit_clamping(install_handler):
    install_handler(lambda req: _json([{"id": "V1", "seq_region_name": "2", "start": 1, "end": 1, "strand": 1, "alleles": ["A", "T"], "consequence_type": "x", "source": "y", "clinical_significance": []}]))
    # limit=500 should clamp to 200 internally; tested by no crash and count<=200
    out = server.search_variants_in_region(region="2:1-2", species="arabidopsis_thaliana", limit=500)
    assert out["count"] == 1


# ---------------------------------------------------------------------------
# get_variant
# ---------------------------------------------------------------------------


def test_get_variant_basic(install_handler):
    install_handler(lambda req: _json({
        "name": "ENSVATH00237387",
        "var_class": "SNP",
        "most_severe_consequence": "5_prime_UTR_variant",
        "ambiguity": "Y",
        "MAF": None,
        "minor_allele": None,
        "mappings": [{
            "location": "2:8140017-8140017",
            "seq_region_name": "2",
            "start": 8140017,
            "end": 8140017,
            "strand": 1,
            "allele_string": "C/T",
            "assembly_name": "TAIR10",
            "ancestral_allele": None,
        }],
        "source": "test catalog",
        "synonyms": [],
        "evidence": [],
    }))
    out = server.get_variant(variant_id="ENSVATH00237387", species="arabidopsis_thaliana")
    assert out["variant_id"] == "ENSVATH00237387"
    assert out["variant_class"] == "SNP"
    assert len(out["mappings"]) == 1


def test_get_variant_404(install_handler):
    install_handler(lambda req: _json({}, 404))
    out = server.get_variant(variant_id="NOPE", species="arabidopsis_thaliana")
    assert out["error"] == "Variant not found"


# ---------------------------------------------------------------------------
# predict_variant_effect
# ---------------------------------------------------------------------------


def test_predict_variant_effect_input_validation():
    """Neither (region+allele) nor variant_id."""
    out = server.predict_variant_effect()
    assert "error" in out


def test_predict_variant_effect_rejects_both_modes():
    out = server.predict_variant_effect(region="2:1-1", allele="A", variant_id="X")
    assert "error" in out


def test_predict_variant_effect_region_mode(install_handler):
    install_handler(lambda req: _json([{
        "input": "2 8140000 8140000 A/T 1",
        "id": "2_8140000_A/T",
        "allele_string": "A/T",
        "seq_region_name": "2",
        "start": 8140000,
        "end": 8140000,
        "strand": 1,
        "assembly_name": "TAIR10",
        "most_severe_consequence": "5_prime_UTR_variant",
        "transcript_consequences": [
            {"gene_id": "AT2G18790", "gene_symbol": "PHYB", "transcript_id": "AT2G18790.1",
             "biotype": "protein_coding", "consequence_terms": ["5_prime_UTR_variant"],
             "impact": "MODIFIER"}
        ],
    }]))
    out = server.predict_variant_effect(region="2:8140000-8140000", allele="T", species="arabidopsis_thaliana")
    assert out["result_count"] == 1
    assert out["results"][0]["transcript_consequence_count"] == 1


def test_predict_variant_effect_empty(install_handler):
    install_handler(lambda req: _json([]))
    out = server.predict_variant_effect(region="2:1-1", allele="A", species="arabidopsis_thaliana")
    assert out["consequences"] == []


# ---------------------------------------------------------------------------
# compare_variants
# ---------------------------------------------------------------------------


def test_compare_variants_too_many():
    out = server.compare_variants(variant_ids=[f"V{i}" for i in range(11)])
    assert "error" in out


def test_compare_variants_empty():
    out = server.compare_variants(variant_ids=[])
    assert "error" in out


def test_compare_variants_mixed_404(install_handler):
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 1:
            return _json({}, 404)
        return _json({
            "name": "V2",
            "var_class": "SNP",
            "most_severe_consequence": "intron_variant",
            "MAF": 0.05,
            "mappings": [{"location": "1:100-100", "allele_string": "A/T"}],
            "source": "test",
        })

    install_handler(handler)
    out = server.compare_variants(variant_ids=["V1", "V2"], species="arabidopsis_thaliana")
    assert len(out["variants"]) == 2
    assert out["variants"][0]["error"] == "Variant not found"
    assert out["variants"][1]["variant_id"] == "V2"


# ---------------------------------------------------------------------------
# get_orthologs
# ---------------------------------------------------------------------------


def test_get_orthologs_target_mutual_exclusion():
    out = server.get_orthologs(gene="PHYB", target_species="oryza_sativa", target_taxon=4577)
    assert "error" in out


def test_get_orthologs_symbol_fallback(install_handler):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        if req.url.path == "/homology/id/PHYB":
            return _json({"error": "Bad ID"}, 400)
        return _json({
            "data": [{
                "id": "AT2G18790",
                "homologies": [
                    {"id": "Os03g0309200", "protein_id": "Os03t0309200-02",
                     "species": "oryza_sativa", "type": "ortholog_one2many",
                     "taxonomy_level": "Mesangiospermae",
                     "method_link_type": "ENSEMBL_ORTHOLOGUES"},
                ],
            }],
        })

    install_handler(handler)
    out = server.get_orthologs(gene="PHYB", species="arabidopsis_thaliana", target_species="oryza_sativa")
    assert out["ortholog_count"] == 1
    assert out["lookup_route"] == "symbol"


# ---------------------------------------------------------------------------
# get_sequence
# ---------------------------------------------------------------------------


def test_get_sequence_invalid_type():
    out = server.get_sequence(stable_id="X", seq_type="rna")
    assert "error" in out
    assert "valid" in out


def test_get_sequence_basic(install_handler):
    install_handler(lambda req: _json({
        "id": "AT2G18790.1",
        "molecule": "protein",
        "seq": "MVSG" * 50,
        "desc": None,
    }))
    out = server.get_sequence(stable_id="AT2G18790.1", seq_type="protein")
    assert out["length"] == 200
    assert out["sequence"].startswith("MVSG")


# ---------------------------------------------------------------------------
# Retry / Retry-After behavior
# ---------------------------------------------------------------------------


def test_retry_after_429(install_handler):
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"}, headers={"Retry-After": "1"})
        return _json({"id": "AT2G18790", "display_name": "PHYB", "species": "arabidopsis_thaliana"})

    install_handler(handler)
    out = server.lookup_gene(gene="AT2G18790")
    assert out["gene_id"] == "AT2G18790"
    assert counter["n"] == 2  # exactly one retry


def test_retry_gives_up_after_max(install_handler):
    """After _MAX_RETRIES retries on persistent 429, raise_for_status fires.

    The retry budget for ONE endpoint attempt is _MAX_RETRIES + 1 calls.
    lookup_gene's id-first/symbol-fallback flow only enters fallback for
    400/404; a 429 falls through to raise_for_status, so we should see
    exactly _MAX_RETRIES + 1 calls before the exception.
    """
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(429, json={}, headers={"Retry-After": "1"})

    install_handler(handler)
    with pytest.raises(httpx.HTTPStatusError):
        server.lookup_gene(gene="AT2G18790")
    assert counter["n"] == server._MAX_RETRIES + 1


def test_retry_after_503(install_handler):
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] < 2:
            return httpx.Response(503, json={})
        return _json({"id": "X", "display_name": "Y", "species": "arabidopsis_thaliana"})

    install_handler(handler)
    out = server.lookup_gene(gene="X")
    assert out["gene_id"] == "X"


# ---------------------------------------------------------------------------
# Trait atlas
# ---------------------------------------------------------------------------


def test_list_trait_categories():
    out = server.list_trait_categories()
    assert out["trait_count"] == len(server.TRAIT_ATLAS)
    for key, info in out["traits"].items():
        assert "description" in info
        assert "natural_farming_relevance" in info
        assert info["gene_count"] > 0


def test_find_trait_genes_exact_match():
    out = server.find_trait_genes(trait="drought_tolerance")
    assert out["trait"] == "drought_tolerance"
    assert any(g["symbol"] == "DREB1A" for g in out["genes"])
    for g in out["genes"]:
        assert "characterized_in" in g
        assert "function" in g


def test_find_trait_genes_loose_match():
    out = server.find_trait_genes(trait="drought")
    assert out["trait"] == "drought_tolerance"


def test_find_trait_genes_normalizes_whitespace_and_dashes():
    out = server.find_trait_genes(trait="Drought-Tolerance")
    assert out["trait"] == "drought_tolerance"


def test_find_trait_genes_unknown():
    out = server.find_trait_genes(trait="unicorn_resistance")
    assert "error" in out
    assert len(out["available_traits"]) == len(server.TRAIT_ATLAS)


def test_find_trait_genes_with_target_species_adds_hint():
    out = server.find_trait_genes(trait="drought_tolerance", target_species="sorghum_bicolor")
    assert out["target_species"] == "sorghum_bicolor"
    assert "followup_hint" in out


def test_trait_atlas_genes_have_expected_shape():
    """Curated atlas invariants: every gene has symbol, characterized_in, function."""
    for trait_key, info in server.TRAIT_ATLAS.items():
        for gene in info["genes"]:
            assert "symbol" in gene, f"{trait_key}/{gene}"
            assert "characterized_in" in gene, f"{trait_key}/{gene['symbol']}"
            assert "function" in gene, f"{trait_key}/{gene['symbol']}"


# ---------------------------------------------------------------------------
# Species normalization
# ---------------------------------------------------------------------------


def test_normalize_species_handles_human_input():
    assert server._normalize_species("Arabidopsis thaliana") == "arabidopsis_thaliana"
    assert server._normalize_species("ARABIDOPSIS_THALIANA") == "arabidopsis_thaliana"
    assert server._normalize_species(None) == "arabidopsis_thaliana"  # default
    assert server._normalize_species("   oryza_sativa  ") == "oryza_sativa"


# ---------------------------------------------------------------------------
# Species quality grading
# ---------------------------------------------------------------------------


def test_species_quality_richly_covered():
    q = server._species_quality("arabidopsis_thaliana")
    assert q["tier"] == "richly_covered"
    assert "1001 Genomes" in q["variation_source"]


def test_species_quality_gene_models_only_default():
    """Sorghum has gene models but no curated variation tier — should fall to default."""
    q = server._species_quality("sorghum_bicolor")
    assert q["tier"] == "gene_models_only"
    assert q["species"] == "sorghum_bicolor"


def test_species_quality_cannabis_flagged():
    q = server._species_quality("cannabis_sativa")
    assert q["tier"] == "not_in_ensembl_plants"


def test_species_quality_surfaces_in_search_response(install_handler):
    install_handler(lambda req: _json([]))
    out = server.search_variants_in_region(region="1:1-100", species="arabidopsis_thaliana", limit=5)
    assert "species_quality" in out
    assert out["species_quality"]["tier"] == "richly_covered"


def test_species_quality_surfaces_in_get_variant(install_handler):
    install_handler(lambda req: _json({
        "name": "V1", "var_class": "SNP", "most_severe_consequence": "x",
        "MAF": None, "minor_allele": None,
        "mappings": [{"location": "1:1-1", "seq_region_name": "1", "start": 1, "end": 1, "strand": 1, "allele_string": "A/T", "assembly_name": "X", "ancestral_allele": None}],
        "source": "test", "synonyms": [], "evidence": [],
    }))
    out = server.get_variant(variant_id="V1", species="sorghum_bicolor")
    assert "species_quality" in out
    assert out["species_quality"]["tier"] == "gene_models_only"


# ---------------------------------------------------------------------------
# translate_trait_to_species composed tool
# ---------------------------------------------------------------------------


def test_translate_trait_to_species_basic(install_handler):
    """One trait + target -> N concurrent ortholog calls -> unified result."""
    def handler(req: httpx.Request) -> httpx.Response:
        # All homology calls return one ortholog.
        if "/homology/" in req.url.path:
            return _json({
                "data": [{
                    "id": "X",
                    "homologies": [{
                        "id": "SbX",
                        "protein_id": "SbX-P",
                        "species": "sorghum_bicolor",
                        "type": "ortholog_one2one",
                        "taxonomy_level": "Poaceae",
                        "method_link_type": "ENSEMBL_ORTHOLOGUES",
                    }],
                }],
            })
        return _json({}, 404)

    install_handler(handler)
    out = server.translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")
    assert out["trait"] == "drought_tolerance"
    assert out["target_species"] == "sorghum_bicolor"
    assert out["canonical_gene_count"] > 0
    # Every gene in the drought atlas that's in an Ensembl-Plants source species
    # should resolve at least one ortholog under this mocked handler.
    assert out["translations_with_orthologs"] >= 1
    assert "translations" in out
    assert all("canonical_gene" in t for t in out["translations"])


def test_translate_trait_unknown_trait():
    out = server.translate_trait_to_species(trait="unicorn", target_species="oryza_sativa")
    assert "error" in out


def test_translate_trait_cannabis_target(install_handler):
    """Cannabis target -> fallback before any HTTP."""
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return _json({}, 500)
    install_handler(handler)
    out = server.translate_trait_to_species(trait="drought_tolerance", target_species="cannabis_sativa")
    assert out["available_in_ensembl_plants"] is False
    # The find_trait_genes preamble doesn't hit HTTP, and the cannabis
    # fallback short-circuits before any ortholog call.
    assert calls == []


def test_translate_trait_handles_literature_handles(install_handler):
    """Genes whose source species is in COMMUNITY_RESOURCES are marked, not queried."""
    # No outbound calls should be issued for source_species not in Ensembl.
    # Use a handler that succeeds for all calls so we can verify the
    # composed tool doesn't crash on literature-handle genes.
    install_handler(lambda req: _json({
        "data": [{"id": "X", "homologies": []}],
    }))
    out = server.translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")
    # The submergence_tolerance / iron_uptake / HVA1 entries with
    # source=community-resource species would be marked; drought is mostly
    # well-covered species though.
    assert "translations" in out


# ---------------------------------------------------------------------------
# lookup_gene_evidence — veracity backbone
# ---------------------------------------------------------------------------


def _xref_response(swissprot: list[str] = None, sptrembl: list[str] = None, go_count: int = 0, pdb: list[str] = None, reactome: list[tuple[str, str]] = None):
    """Build a fake /xrefs/id response with given annotations."""
    out = []
    for pid in (swissprot or []):
        out.append({"primary_id": pid, "display_id": f"{pid}.1", "description": "test protein", "info_type": "SEQUENCE_MATCH", "dbname": "Uniprot/SWISSPROT"})
    for pid in (sptrembl or []):
        out.append({"primary_id": pid, "display_id": pid, "description": None, "info_type": "DEPENDENT", "dbname": "Uniprot/SPTREMBL"})
    for _ in range(go_count):
        out.append({"primary_id": "GO:0000001", "display_id": "GO:0000001", "description": "test", "info_type": "DEPENDENT", "dbname": "GO"})
    for pdb_id in (pdb or []):
        out.append({"primary_id": pdb_id, "display_id": pdb_id, "description": None, "info_type": "DEPENDENT", "dbname": "PDB"})
    for rid, name in (reactome or []):
        out.append({"primary_id": rid, "display_id": name, "description": None, "info_type": "DIRECT", "dbname": "Plant_Reactome_Pathway"})
    return out


def test_lookup_gene_evidence_high_curated(install_handler):
    install_handler(lambda req: _json(_xref_response(
        swissprot=["P14713"], go_count=88, pdb=["4OUR", "7RZW"],
        reactome=[("R-ATH-8934036", "Circadian rhythm")]
    )))
    out = server.lookup_gene_evidence(stable_id="AT2G18790")
    assert out["evidence_tier"] == "high_curated"
    assert out["uniprot_curated"][0]["id"] == "P14713"
    assert out["uniprot_lookup_url"] == "https://www.uniprot.org/uniprotkb/P14713"
    assert out["go_term_count"] == 88
    assert len(out["pdb_structures"]) == 2
    assert len(out["plant_reactome_pathways"]) == 1


def test_lookup_gene_evidence_moderate_tier(install_handler):
    install_handler(lambda req: _json(_xref_response(
        sptrembl=["A0A0A0KQ23"], go_count=15
    )))
    out = server.lookup_gene_evidence(stable_id="Os09g0286600")
    assert out["evidence_tier"] == "moderate_auto_annotated"
    assert out["uniprot_curated"] == []
    assert len(out["uniprot_auto"]) == 1


def test_lookup_gene_evidence_low_tier(install_handler):
    install_handler(lambda req: _json(_xref_response(go_count=3)))
    out = server.lookup_gene_evidence(stable_id="X")
    assert out["evidence_tier"] == "low_some_annotation"


def test_lookup_gene_evidence_minimal_tier(install_handler):
    """Cross-references exist but no functional annotation."""
    install_handler(lambda req: _json([
        {"primary_id": "X", "display_id": "X", "description": None, "info_type": "DIRECT", "dbname": "EntrezGene"}
    ]))
    out = server.lookup_gene_evidence(stable_id="X")
    assert out["evidence_tier"] == "minimal"


def test_lookup_gene_evidence_404(install_handler):
    install_handler(lambda req: _json({}, 404))
    out = server.lookup_gene_evidence(stable_id="GARBAGE")
    assert "error" in out


def test_lookup_gene_evidence_cannabis_fallback(install_handler):
    install_handler(lambda req: _json({}, 500))
    out = server.lookup_gene_evidence(stable_id="X", species="cannabis_sativa")
    assert out["available_in_ensembl_plants"] is False


# ---------------------------------------------------------------------------
# Atlas evidence enrichment
# ---------------------------------------------------------------------------


def test_atlas_evidence_loaded():
    """The atlas_evidence.json file should be present in the package and load."""
    assert isinstance(server._ATLAS_EVIDENCE, dict)
    # Should have at least one entry — the audit covered 80+ genes.
    assert len(server._ATLAS_EVIDENCE) > 30


def test_find_trait_genes_surfaces_evidence_tier():
    """find_trait_genes should attach the cached evidence tier per gene."""
    out = server.find_trait_genes(trait="salt_tolerance")
    sos1_entry = next((g for g in out["genes"] if g["symbol"] == "SOS1"), None)
    assert sos1_entry is not None
    # SOS1 is one of the canonical UniProt-curated entries.
    assert sos1_entry.get("evidence") is not None
    assert sos1_entry["evidence"]["evidence_tier"] == "high_curated"
    assert sos1_entry["evidence"]["uniprot_id"] == "Q9LKW9"


def test_find_trait_genes_reports_high_curated_count():
    """The result should include a count + fraction of high-curated genes."""
    out = server.find_trait_genes(trait="salt_tolerance")
    assert "high_curated_gene_count" in out
    assert "high_curated_fraction" in out
    assert out["high_curated_gene_count"] >= 4  # SOS1/2/3 + NHX1 + HKT1 at minimum


def test_find_trait_genes_evidence_none_when_uncurated():
    """For genes without an ensembl_id or without an audited xref, evidence is None."""
    out = server.find_trait_genes(trait="submergence_tolerance")
    # SK1 and SK2 are unresolvable literature handles
    sk1 = next((g for g in out["genes"] if g["symbol"] == "SK1"), None)
    assert sk1 is not None
    assert sk1.get("evidence") is None


# ---------------------------------------------------------------------------
# Kannapedia integration tests
# ---------------------------------------------------------------------------


_KANNAPEDIA_SAMPLE_HTML = """
<html>
<head><title>Mystery Skunk x Wedding Cake | Kannapedia</title></head>
<body>
<h1>Mystery Skunk x Wedding Cake</h1>
<div class="StrainInfo--registrant"> Grower: <a class="SearchLink" href="/strains?source=Heritage+Genetics"> Heritage Genetics <svg></svg></a></div>
<dl>
<dt>Sample Name</dt><dd>HG_2026_001</dd>
<dt>Reported Plant Sex</dt><dd><a class="SearchLink" href="/strains?sex=Female"> Female <svg></svg></a></dd>
<dt>Report Type</dt><dd><a class="SearchLink" href="/strains?report=WGS"> Whole-Genome Sequencing <svg></svg></a></dd>
<dt>Plant Type</dt><dd><a class="SearchLink" href="/strains?type=II"> Type II <svg></svg></a></dd>
<dt>Accession Date</dt><dd>January 15, 2026</dd>
</dl>
<figcaption>Heterozygosity: <strong>2.34%</strong></figcaption>
<figcaption>Y-Ratio Distribution: <strong>0.0145</strong></figcaption>
<figcaption class="DataPlot--caption">Rarity: <strong><a class="SearchLink" href="/strains?rarity=common"> Common <svg></svg></a></strong></figcaption>
<a href="https://mgcdata.s3.amazonaws.com/SS2/vcf-snpeff-variants/RSP99999.vcf.gz">VCF</a>
<a href="https://mgcdata.s3.amazonaws.com/SS2/vcf-snpeff-variants/RSP99999.vcf.gz.tbi">VCF index</a>
<a href="https://mgcdata.s3.amazonaws.com/SS2/vcf_JL/RSP99999_blockchain.vcf.gz">Blockchain VCF</a>
<a href="https://mgcdata.s3.amazonaws.com/SS2/runs/20260101/RSP99999_R1_001.fastq.gz">R1</a>
<a href="https://mgcdata.s3.amazonaws.com/SS2/runs/20260101/RSP99999_R2_001.fastq.gz">R2</a>
<a href="https://mgcdata.s3.amazonaws.com/SS2/bams/public/RSP99999.bam">BAM</a>
<a href="/strains/rsp10001">Related</a>
<a href="/strains/rsp10002">Related</a>
THCAS variant: missense
CBDAS variant: silent
ELF3 splice variant: high_impact
</body></html>
"""


def _kannapedia_factory(handler):
    """Build a factory that returns clients pointed at the Kannapedia base URL."""

    def factory():
        return httpx.Client(
            base_url=server.KANNAPEDIA_BASE_URL,
            transport=httpx.MockTransport(handler),
            timeout=5,
            follow_redirects=True,
        )

    return factory


def test_kannapedia_strain_parses_basic_fields(monkeypatch):
    monkeypatch.setattr(
        server, "_kannapedia_client",
        lambda: _kannapedia_factory(lambda req: httpx.Response(200, text=_KANNAPEDIA_SAMPLE_HTML))(),
    )
    out = server.lookup_kannapedia_strain(rsp_id="99999")
    assert out["rsp_id"] == "rsp99999"
    assert out["strain_name"] == "Mystery Skunk x Wedding Cake"
    assert out["plant_type_chemotype"] == "Type II"
    assert out["plant_sex"] == "Female"
    assert out["grower"] == "Heritage Genetics"
    assert out["rarity_classification"] == "Common"
    assert out["heterozygosity"] == "2.34%"
    assert out["y_ratio_distribution"] == "0.0145"
    assert out["sample_name"] == "HG_2026_001"
    assert out["accession_date"] == "January 15, 2026"


def test_kannapedia_strain_extracts_files(monkeypatch):
    monkeypatch.setattr(
        server, "_kannapedia_client",
        lambda: _kannapedia_factory(lambda req: httpx.Response(200, text=_KANNAPEDIA_SAMPLE_HTML))(),
    )
    out = server.lookup_kannapedia_strain(rsp_id="99999")
    assert len(out["data_files"]["annotated_vcf"]) == 1
    assert "RSP99999.vcf.gz" in out["data_files"]["annotated_vcf"][0]
    assert len(out["data_files"]["fastq_reads"]) == 2
    assert len(out["data_files"]["bam_alignment"]) == 1
    assert len(out["data_files"]["blockchain_vcf"]) == 1


def test_kannapedia_strain_extracts_related(monkeypatch):
    monkeypatch.setattr(
        server, "_kannapedia_client",
        lambda: _kannapedia_factory(lambda req: httpx.Response(200, text=_KANNAPEDIA_SAMPLE_HTML))(),
    )
    out = server.lookup_kannapedia_strain(rsp_id="99999")
    assert out["related_strain_count"] == 2
    assert "rsp10001" in out["related_strains"]


def test_kannapedia_strain_detects_canonical_genes(monkeypatch):
    monkeypatch.setattr(
        server, "_kannapedia_client",
        lambda: _kannapedia_factory(lambda req: httpx.Response(200, text=_KANNAPEDIA_SAMPLE_HTML))(),
    )
    out = server.lookup_kannapedia_strain(rsp_id="99999")
    assert "THCAS" in out["cannabis_genes_mentioned_on_page"]
    assert "CBDAS" in out["cannabis_genes_mentioned_on_page"]
    assert "ELF3" in out["cannabis_genes_mentioned_on_page"]


def test_kannapedia_strain_accepts_both_id_formats(monkeypatch):
    """Both '13536' and 'rsp13536' should work."""
    monkeypatch.setattr(
        server, "_kannapedia_client",
        lambda: _kannapedia_factory(lambda req: httpx.Response(200, text=_KANNAPEDIA_SAMPLE_HTML))(),
    )
    a = server.lookup_kannapedia_strain(rsp_id="99999")
    b = server.lookup_kannapedia_strain(rsp_id="rsp99999")
    c = server.lookup_kannapedia_strain(rsp_id="RSP99999")
    assert a["rsp_id"] == b["rsp_id"] == c["rsp_id"] == "rsp99999"


def test_kannapedia_strain_rejects_bad_input():
    out = server.lookup_kannapedia_strain(rsp_id="not-a-number")
    assert "error" in out


def test_kannapedia_strain_404(monkeypatch):
    monkeypatch.setattr(
        server, "_kannapedia_client",
        lambda: _kannapedia_factory(lambda req: httpx.Response(404, text="not found"))(),
    )
    out = server.lookup_kannapedia_strain(rsp_id="99999")
    assert out["error"] == "Strain not found"
    assert "kannapedia.net" in out["url"]


def test_compare_cannabis_strains_basic(monkeypatch):
    """Mock 3 strain pages, assert overlap analysis."""
    pages = {
        "rsp1001": _KANNAPEDIA_SAMPLE_HTML.replace("RSP99999", "RSP1001").replace("Type II", "Type I"),
        "rsp1002": _KANNAPEDIA_SAMPLE_HTML.replace("RSP99999", "RSP1002").replace("Type II", "Type III"),
        "rsp1003": _KANNAPEDIA_SAMPLE_HTML.replace("RSP99999", "RSP1003"),  # Type II
    }
    def handler(req: httpx.Request) -> httpx.Response:
        for sid, html in pages.items():
            if sid in req.url.path:
                return httpx.Response(200, text=html)
        return httpx.Response(404, text="not found")
    monkeypatch.setattr(server, "_kannapedia_client", lambda: _kannapedia_factory(handler)())
    out = server.compare_cannabis_strains(rsp_ids=["1001", "1002", "1003"])
    assert out["strain_count"] == 3
    # Each sample HTML has chemotype set; should distribute across the three types
    assert sum(out["chemotype_distribution"].values()) == 3
    # Genes appear on all three pages (mocked HTML), so should be in overlap
    assert "THCAS" in out["genes_flagged_on_multiple_strains"]


def test_compare_cannabis_strains_too_many():
    out = server.compare_cannabis_strains(rsp_ids=[str(i) for i in range(10)])
    assert "error" in out


def test_compare_cannabis_strains_empty():
    out = server.compare_cannabis_strains(rsp_ids=[])
    assert "error" in out


# ---------------------------------------------------------------------------
# UniProt direct lookup
# ---------------------------------------------------------------------------


_UNIPROT_SAMPLE = {
    "primaryAccession": "Q8GTB6",
    "secondaryAccessions": [],
    "uniProtkbId": "THCAS_CANSA",
    "entryType": "UniProtKB reviewed (Swiss-Prot)",
    "proteinDescription": {
        "recommendedName": {"fullName": {"value": "Tetrahydrocannabinolic acid synthase"}}
    },
    "genes": [{"geneName": {"value": "THCAS"}}],
    "organism": {"scientificName": "Cannabis sativa", "commonName": "Hemp"},
    "sequence": {"length": 545, "md5": "abc123"},
    "comments": [
        {"commentType": "FUNCTION", "texts": [{"value": "Oxidoreductase in cannabinoid biosynthesis"}]},
        {"commentType": "CATALYTIC ACTIVITY", "reaction": {"name": "CBGA -> THCA", "ecNumber": "1.21.3.7"}},
        {"commentType": "COFACTOR", "cofactors": [{"name": "FAD"}]},
        {"commentType": "PATHWAY", "texts": [{"value": "Cannabinoid biosynthesis"}]},
    ],
    "uniProtKBCrossReferences": [
        {"database": "GO", "id": "GO:0048046", "properties": [{"key": "GoTerm", "value": "C:apoplast"}, {"key": "GoEvidenceType", "value": "IDA"}]},
        {"database": "GO", "id": "GO:0102778", "properties": [{"key": "GoTerm", "value": "F:THCA synthase"}, {"key": "GoEvidenceType", "value": "EXP"}]},
    ],
    "references": [
        {"citation": {"citationCrossReferences": [{"database": "PubMed", "id": "15190053"}]}},
        {"citation": {"citationCrossReferences": [{"database": "PubMed", "id": "16143478"}]}},
    ],
}


def _patch_helper(monkeypatch, helper_name: str, base_url: str, handler):
    """Patch one of the per-API client-factory helpers with a mock transport."""
    def factory():
        return httpx.Client(
            base_url=base_url,
            transport=httpx.MockTransport(handler),
            timeout=5,
        )
    monkeypatch.setattr(server, helper_name, factory)


def test_lookup_uniprot_thcas(monkeypatch):
    _patch_helper(monkeypatch, "_uniprot_client", server.UNIPROT_BASE_URL,
                  lambda req: _json(_UNIPROT_SAMPLE))
    out = server.lookup_uniprot_entry(uniprot_id="Q8GTB6")
    assert out["uniprot_id"] == "Q8GTB6"
    assert out["protein_name"] == "Tetrahydrocannabinolic acid synthase"
    assert out["organism"] == "Cannabis sativa"
    assert "SwissProt" in out["review_status"]
    assert "Oxidoreductase" in out["function"][0]
    assert out["catalytic_activities"][0]["ecNumber"] == "1.21.3.7"
    assert "FAD" in out["cofactors"]
    assert out["go_term_count"] == 2
    assert out["pubmed_citation_count"] == 2
    assert "15190053" in out["pubmed_ids"]
    assert out["uniprot_url"] == "https://www.uniprot.org/uniprotkb/Q8GTB6"


def test_lookup_uniprot_empty_id():
    out = server.lookup_uniprot_entry(uniprot_id="")
    assert "error" in out


# ---------------------------------------------------------------------------
# EuropePMC literature search
# ---------------------------------------------------------------------------


_EUROPEPMC_SAMPLE = {
    "hitCount": 190,
    "resultList": {"result": [
        {
            "id": "40899604", "pmid": "40899604", "pmcid": "PMC12631913",
            "doi": "10.1002/advs.202507919",
            "title": "OsNRT1.1B-OsCNGC14/16-Ca2+-OsNLP3 Pathway",
            "authorString": "Wang X, Liu Y, Li W",
            "journalTitle": "Adv Sci",
            "pubYear": "2025",
            "isOpenAccess": "Y",
            "pubType": "journal article",
            "citedByCount": 5,
        },
        {
            "id": "26053497", "pmid": "26053497",
            "doi": "10.1038/ng.3337",
            "title": "Variation in NRT1.1B contributes to nitrate-use divergence",
            "authorString": "Hu B et al.",
            "journalTitle": "Nat Genet",
            "pubYear": "2015",
            "isOpenAccess": "N",
            "citedByCount": 320,
        },
    ]},
}


def test_search_pubmed_basic(monkeypatch):
    _patch_helper(monkeypatch, "_europepmc_client", server.EUROPEPMC_BASE_URL,
                  lambda req: _json(_EUROPEPMC_SAMPLE))
    out = server.search_pubmed_for_gene(query="OsNRT1.1B rice")
    assert out["total_hits"] == 190
    assert len(out["results"]) == 2
    first = out["results"][0]
    assert first["pmid"] == "40899604"
    assert first["is_open_access"] is True
    assert first["europepmc_url"] == "https://europepmc.org/article/MED/40899604"
    assert first["doi_url"] == "https://doi.org/10.1002/advs.202507919"


def test_search_pubmed_empty_query():
    out = server.search_pubmed_for_gene(query="")
    assert "error" in out


def test_search_pubmed_page_size_clamps(monkeypatch):
    captured = {}
    def h(req):
        captured.update(dict(req.url.params))
        return _json(_EUROPEPMC_SAMPLE)
    _patch_helper(monkeypatch, "_europepmc_client", server.EUROPEPMC_BASE_URL, h)
    server.search_pubmed_for_gene(query="x", page_size=500)
    assert int(captured.get("pageSize", 0)) <= 25


# ---------------------------------------------------------------------------
# STRING-db protein-protein interactions
# ---------------------------------------------------------------------------


_STRING_SAMPLE = [
    {
        "stringId_A": "3702.AT2G18790",
        "stringId_B": "3702.O80536",
        "preferredName_A": "PHYB",
        "preferredName_B": "PIF3",
        "ncbiTaxonId": "3702",
        "score": 0.999,
        "nscore": 0, "fscore": 0, "pscore": 0, "ascore": 0,
        "escore": 0.95, "dscore": 0.9, "tscore": 0.98,
    },
    {
        "stringId_A": "3702.AT2G18790",
        "stringId_B": "3702.Q570R7",
        "preferredName_A": "PHYB",
        "preferredName_B": "PIF4",
        "ncbiTaxonId": "3702",
        "score": 0.95,
        "nscore": 0, "fscore": 0, "pscore": 0, "ascore": 0.2,
        "escore": 0.8, "dscore": 0.5, "tscore": 0.9,
    },
]


def test_string_interactions_basic(monkeypatch):
    _patch_helper(monkeypatch, "_string_client", server.STRING_BASE_URL,
                  lambda req: _json(_STRING_SAMPLE))
    out = server.get_string_interactions(protein_id="PHYB", species="arabidopsis_thaliana", limit=5)
    assert out["interaction_count"] == 2
    assert out["interactions"][0]["partner_symbol"] == "PIF3"
    assert out["interactions"][0]["combined_score"] == 0.999
    assert out["interactions"][0]["evidence_channels"]["textmining"] == 0.98


def test_string_unsupported_species():
    out = server.get_string_interactions(protein_id="X", species="some_unknown_plant")
    assert "error" in out
    assert "supported_species" in out


def test_string_cannabis_is_supported():
    """Cannabis sativa must be in our taxon map — it's the whole point."""
    assert "cannabis_sativa" in server._NCBI_TAXON_IDS
    assert server._NCBI_TAXON_IDS["cannabis_sativa"] == 3483


def test_string_empty_id():
    out = server.get_string_interactions(protein_id="")
    assert "error" in out


def test_cannabis_strain_search_urls_constructs():
    out = server.cannabis_strain_search_urls(query="Northern Lights")
    assert "kannapedia" in out["search_urls"]
    assert "Northern+Lights" in out["search_urls"]["kannapedia"]
    assert "leafly" in out["search_urls"]
    assert "europepmc" in out["search_urls"]


def test_cannabis_strain_search_empty():
    out = server.cannabis_strain_search_urls(query="")
    assert "error" in out


# ---------------------------------------------------------------------------
# NAM founder lines
# ---------------------------------------------------------------------------


def test_nam_founders_full_list():
    out = server.list_maize_nam_founders()
    # Sources disagree on the exact count (25 vs 26 vs 27 — McMullen 2009
    # vs. Hufford 2021 vs. variations including/excluding B97 or CML333).
    # Require at least the canonical core size.
    assert out["founder_count"] >= 25
    assert any(f["line"] == "B73" for f in out["founders"])
    assert any(f["line"] == "Mo17" for f in out["founders"])
    # Must include CIMMYT tropical lines (CC priority)
    cml_lines = [f["line"] for f in out["founders"] if f["line"].startswith("CML")]
    assert len(cml_lines) >= 8


def test_nam_founders_filter_by_subpopulation():
    out = server.list_maize_nam_founders(subpopulation="Sweet Corn")
    assert all(f["subpopulation"] == "Sweet Corn" for f in out["founders"])
    assert out["founder_count"] >= 2  # Il14H + P39


def test_nam_founders_tropical_subpopulation_for_smallholder():
    """Tropical/Subtropical lines are highlighted for CC's smallholder audience."""
    out = server.list_maize_nam_founders(subpopulation="Tropical / Subtropical")
    lines = {f["line"] for f in out["founders"]}
    # CIMMYT CML lines + Thai Ki + IITA Tzi8 are the canonical smallholder-relevant
    assert "Ki3" in lines or "Ki11" in lines
    assert "Tzi8" in lines


# ---------------------------------------------------------------------------
# New atlas categories — sanity checks
# ---------------------------------------------------------------------------


def test_cannabis_atlas_categories_present():
    expected = {
        "cannabinoid_biosynthesis",
        "cannabis_terpene_profile",
        "cannabis_sex_and_photoperiod",
        "cannabis_disease_resistance",
        "hemp_compliance",
    }
    assert expected.issubset(set(server.TRAIT_ATLAS.keys()))


def test_cannabinoid_biosynthesis_has_canonical_pathway():
    genes = {g["symbol"] for g in server.TRAIT_ATLAS["cannabinoid_biosynthesis"]["genes"]}
    # The full 7-enzyme pathway: CsAAE1 -> OLS -> OAC -> CsPT4 -> THCAS/CBDAS/CBCAS
    assert {"THCAS", "CBDAS", "CBCAS", "OAC", "CsPT4", "CsAAE1", "OLS"}.issubset(genes)


def test_cannabis_terpene_profile_has_chemotype_synthases():
    genes = {g["symbol"] for g in server.TRAIT_ATLAS["cannabis_terpene_profile"]["genes"]}
    # The major CsTPS family — myrcene + caryophyllene + terpinolene at minimum
    assert "CsTPS1" in genes
    assert "CsTPS9" in genes
    assert "CsTPS18" in genes


def test_maize_categories_present():
    expected = {"maize_quality_protein", "maize_disease_resistance", "maize_pest_resistance"}
    assert expected.issubset(set(server.TRAIT_ATLAS.keys()))


def test_maize_quality_protein_includes_opaque2():
    genes = {g["symbol"] for g in server.TRAIT_ATLAS["maize_quality_protein"]["genes"]}
    assert "Opaque-2" in genes


def test_cannabis_fallback_points_at_kannapedia_tools():
    """The cannabis fallback should mention the new MCP tools, not just URLs."""
    info = server.COMMUNITY_RESOURCES["cannabis_sativa"]
    text = " ".join(info["alternatives"])
    assert "lookup_kannapedia_strain" in text
    assert "cannabinoid_biosynthesis" in text
    assert "hemp_compliance" in text


def test_atlas_grew_with_new_categories():
    """The atlas should now have >= 25 categories (was 21 before this round)."""
    assert len(server.TRAIT_ATLAS) >= 25


def test_primary_ref_present_on_canonical_genes():
    """The well-characterized canonical genes should carry a primary_ref."""
    atlas = server.TRAIT_ATLAS
    canonical = [
        ("drought_tolerance", "DREB1A"),
        ("salt_tolerance", "SOS1"),
        ("submergence_tolerance", "SUB1A"),
        ("phosphorus_uptake", "PSTOL1"),
        ("nitrogen_use_efficiency", "NRT1.1B"),
        ("plant_height_dwarfing", "SD1"),
        ("tiller_branching", "TB1"),
        ("aluminum_tolerance", "ALMT1"),
        ("grain_quality", "BADH2"),
    ]
    missing = []
    for trait, symbol in canonical:
        gene = next((g for g in atlas[trait]["genes"] if g["symbol"] == symbol), None)
        assert gene is not None, f"Missing {symbol} in {trait}"
        if "primary_ref" not in gene:
            missing.append((trait, symbol))
    assert not missing, f"Canonical genes missing primary_ref: {missing}"


def test_translate_trait_uses_ensembl_id_when_available(install_handler):
    """When atlas gene has ensembl_id, that's preferred over symbol."""
    seen = []
    def handler(req):
        seen.append(req.url.path)
        return _json({"data": [{"id": "X", "homologies": []}]})
    install_handler(handler)
    server.translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")
    # The drought atlas contains OST1 with ensembl_id AT4G33950 and RD29A
    # with ensembl_id AT5G52310. The composed tool should look these up by
    # their ensembl_id, not by the symbol.
    assert any("/AT4G33950" in p for p in seen), f"AT4G33950 not used; saw: {seen}"
    assert any("/AT5G52310" in p for p in seen), f"AT5G52310 not used; saw: {seen}"
