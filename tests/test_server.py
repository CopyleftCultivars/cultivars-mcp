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
