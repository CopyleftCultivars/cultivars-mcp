"""
Cultivars MCP Server — Plant Genomics for the Commons

An open tool for grower-scientists exploring the genomic basis of plant
traits that matter to natural farming, regenerative agriculture, and
heritage seed stewardship: stress tolerance, root architecture, microbial
symbiosis, secondary metabolites, nutrient uptake, allelopathy.

Backed by the Ensembl Plants REST API (https://plants.ensembl.org/) —
chosen because it is free, no-auth, public-sector-funded, and serves all
~80 plant genomes uniformly. Tooling like Phytozome paywalls behind login;
this fork deliberately avoids those.

This is a fork of the EVEE MCP server (human clinical variants from the
Goodfire EVEE API). It is part of the Copyleft Cultivars ecosystem
(https://github.com/CopyleftCultivars), whose mission is to democratize
agricultural knowledge for resource-limited farmers and grower-scientists.
Companion projects:
  - TinyLLamaFarmer — an offline natural-farming AI assistant
  - gemma4-natural-farming — open-weight Gemma 4 fine-tuned on Korean
    Natural Farming, JADAM, and regenerative agriculture literature

Honest tension: Copyleft Cultivars's flagship tools are offline-first
(designed to work in the field, off-grid). This MCP server calls a remote
REST API and therefore needs connectivity. Treat it as the desk-side
research companion, not the field tool. Cache results locally where
possible.

Genomics is one lens. Indigenous knowledge, farmer observation, on-farm
trials, and natural-farming holism remain the other lenses. This tool
does not replace them.
"""

import time

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://rest.ensembl.org"
DEFAULT_SPECIES = "arabidopsis_thaliana"

# Species Ensembl Plants does NOT currently carry, but that matter to
# Copyleft Cultivars's audience. Hitting these returns a structured pointer
# to community resources rather than a confusing 404.
COMMUNITY_RESOURCES = {
    "cannabis_sativa": {
        "common_name": "Cannabis",
        "reason": "Cannabis sativa is not in Ensembl Plants (federal-research-funding constraints have historically kept Cannabis out of public plant-genomics infrastructure).",
        "alternatives": [
            "NCBI Genome: https://www.ncbi.nlm.nih.gov/genome/?term=cannabis+sativa",
            "Cannabis Genome DB (community): https://www.cannabisgenome.org/",
            "CS10 reference (Grassa et al. 2021): NCBI GCF_900626175.2",
            "JGI Phytozome has draft Cannabis sativa assemblies (login required).",
        ],
    },
    "cannabis": {
        "common_name": "Cannabis",
        "reason": "Cannabis sativa is not in Ensembl Plants. Use the Ensembl name 'cannabis_sativa' if Ensembl ever adds it; for now see alternatives.",
        "alternatives": [
            "NCBI Genome: https://www.ncbi.nlm.nih.gov/genome/?term=cannabis+sativa",
            "Cannabis Genome DB (community): https://www.cannabisgenome.org/",
        ],
    },
    "psilocybe_cubensis": {
        "common_name": "Psilocybe (fungi, not plants)",
        "reason": "Psilocybe is a fungus, not a plant, and is out of scope for Ensembl Plants. See Ensembl Fungi for fungal genomics.",
        "alternatives": [
            "Ensembl Fungi REST: https://rest.ensembl.org/ (use division=EnsemblFungi)",
            "MycoCosm (JGI): https://mycocosm.jgi.doe.gov/",
        ],
    },
}

mcp = FastMCP(
    "cultivars",
    instructions=(
        "Cultivars wraps the Ensembl Plants REST API to support "
        "grower-scientists, heritage breeders, and natural-farming "
        "researchers working with the open plant-genomics commons. "
        "It is part of the Copyleft Cultivars ecosystem alongside "
        "TinyLLamaFarmer (offline natural-farming assistant) and the "
        "gemma4-natural-farming model.\n\n"
        "It covers ~80 plant species. It is NOT clinical: there are no "
        "curated pathogenicity labels — variant effects come from VEP "
        "(rule-based predictor on Ensembl gene models), not a "
        "foundation model.\n\n"
        "Cannabis sativa is NOT currently in Ensembl Plants — when a user "
        "asks about cannabis, surface that gap honestly and point them to "
        "the NCBI Cannabis sativa reference (CS10) or community databases. "
        "The tools handle this gracefully: passing species='cannabis_sativa' "
        "returns a structured fallback with alternative resources.\n\n"
        "Typical workflows:\n"
        "1. list_plant_species — discover available species (returns the "
        "Ensembl 'name' you must pass as the species argument elsewhere, "
        "e.g. 'arabidopsis_thaliana', 'oryza_sativa', 'zea_mays', "
        "'solanum_lycopersicum', 'sorghum_bicolor', 'manihot_esculenta' "
        "for cassava).\n"
        "2. lookup_gene — find a gene by symbol (e.g. 'PHYB', 'DREB1A', "
        "'OsNRT1.1B') or stable ID (e.g. 'AT2G18790').\n"
        "3. search_variants_in_region — list known variants in a genomic "
        "region. Coverage is rich for crops studied at scale (1001 "
        "Genomes / Arabidopsis, 3K Rice Genomes / rice) and sparse or "
        "empty for orphan crops.\n"
        "4. get_variant — retrieve one known variant by stable ID.\n"
        "5. predict_variant_effect — run VEP for a region+allele or a "
        "known variant ID; returns per-transcript consequences and impact.\n"
        "6. compare_variants — summary across 2-10 variants in one call.\n"
        "7. get_orthologs — translate a finding from Arabidopsis (the "
        "model) into rice, maize, sorghum, common bean, cassava, etc. "
        "via the Ensembl Compara plant tree. Essential for grower-"
        "scientists working with heritage crops where the molecular "
        "literature is sparse.\n"
        "8. get_sequence — fetch genomic / cDNA / CDS / protein sequence.\n\n"
        "Coordinate convention: Ensembl is 1-based, fully-closed (same as "
        "VCF / GFF). Region strings are 'chrom:start-end' with optional "
        "':strand' (default +1). No 'chr' prefix on plant chromosomes — "
        "Arabidopsis TAIR10 uses '1'..'5', 'Mt', 'Pt'.\n\n"
        "Species names: lowercase underscored Ensembl form, e.g. "
        "'arabidopsis_thaliana'. Call list_plant_species if unsure.\n\n"
        "Honest framing: this tool needs internet (it hits a REST API). "
        "Copyleft Cultivars's offline-first tools — TinyLLamaFarmer, "
        "gemma4-natural-farming — are the field companions. Cultivars "
        "is the desk-side research companion. Genomics is one lens; "
        "farmer observation, indigenous knowledge, and on-farm trials "
        "remain the other lenses, and this tool does not replace them."
    ),
)


def _community_fallback(species: str, tool: str) -> dict | None:
    """If the species is one we don't serve from Ensembl Plants but matters
    to the Copyleft Cultivars audience, return a structured pointer."""
    info = COMMUNITY_RESOURCES.get(species)
    if not info:
        return None
    return {
        "species": species,
        "tool": tool,
        "available_in_ensembl_plants": False,
        "common_name": info["common_name"],
        "reason": info["reason"],
        "alternatives": info["alternatives"],
        "note": "Ensembl Plants does not carry this species. The Copyleft Cultivars project flags it explicitly because of the gap in public-sector plant-genomics infrastructure.",
    }


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_JSON_HEADERS = {"Accept": "application/json"}


def _get_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, headers=_JSON_HEADERS, timeout=30)


def _ensembl_gene_url(species: str, gene_id: str | None) -> str | None:
    if not gene_id:
        return None
    return f"https://plants.ensembl.org/{species}/Gene/Summary?g={gene_id}"


def _ensembl_variant_url(species: str, variant_id: str | None) -> str | None:
    if not variant_id:
        return None
    return f"https://plants.ensembl.org/{species}/Variation/Explore?v={variant_id}"


def _normalize_species(species: str | None) -> str:
    s = (species or DEFAULT_SPECIES).strip().lower().replace(" ", "_")
    return s


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_plant_species(query: str | None = None) -> dict:
    """List plant species available in Ensembl Plants.

    Returns each species' Ensembl name (the value you pass as `species` to
    other tools), display name, common name, assembly, and taxon id.

    Args:
        query: Optional case-insensitive substring filter, matched against
               name / display_name / common_name / aliases. Example: 'rice'
               returns Oryza sativa indica/japonica and wild rice species.
               Omit to list all ~80 plant species (the response is large).
    """
    with _get_client() as client:
        resp = client.get("/info/species", params={"division": "EnsemblPlants"})
        resp.raise_for_status()
        all_species = resp.json().get("species", [])

    if query:
        q = query.strip().lower()

        def match(sp: dict) -> bool:
            fields = [
                sp.get("name") or "",
                sp.get("display_name") or "",
                sp.get("common_name") or "",
            ] + list(sp.get("aliases") or [])
            return any(q in (f or "").lower() for f in fields)

        all_species = [sp for sp in all_species if match(sp)]

    return {
        "count": len(all_species),
        "species": [
            {
                "name": sp.get("name"),
                "display_name": sp.get("display_name"),
                "common_name": sp.get("common_name"),
                "assembly": sp.get("assembly"),
                "taxon_id": sp.get("taxon_id"),
                "release": sp.get("release"),
                "accession": sp.get("accession"),
            }
            for sp in all_species
        ],
    }


@mcp.tool()
def lookup_gene(gene: str, species: str | None = None, expand: bool = False) -> dict:
    """Look up a plant gene by symbol or Ensembl stable ID.

    Tries stable-ID lookup first (e.g. 'AT2G18790', 'Os01g0100100'), then
    falls back to symbol lookup in the given species (e.g. 'PHYB', 'OsCKX2').

    Args:
        gene: Gene symbol or Ensembl Plants stable ID.
        species: Ensembl species name (default 'arabidopsis_thaliana').
        expand: If True, include transcripts / exons / translations in the
                response. Significantly larger payload.
    """
    species = _normalize_species(species)
    g = (gene or "").strip()
    if not g:
        return {"error": "gene argument is required"}

    fallback = _community_fallback(species, "lookup_gene")
    if fallback:
        return fallback

    params = {"expand": "1" if expand else "0"}

    with _get_client() as client:
        # Try stable-ID lookup first (works across species without specifying).
        # Ensembl returns 400 (not 404) when the value isn't a valid stable ID
        # at all (e.g. a gene symbol like "PHYB") — treat 400 and 404 alike.
        resp = client.get(f"/lookup/id/{g}", params=params)
        if resp.status_code in (400, 404):
            # Fall back to symbol lookup, which requires species.
            resp = client.get(f"/lookup/symbol/{species}/{g}", params=params)
            if resp.status_code in (400, 404):
                return {
                    "error": "Gene not found",
                    "gene": g,
                    "species": species,
                    "detail": "Neither stable-ID nor symbol lookup matched. Check spelling and species; symbol lookup is case-sensitive in some species.",
                }
        resp.raise_for_status()
        data = resp.json()

    gene_id = data.get("id")
    sp = data.get("species") or species
    return {
        "gene_id": gene_id,
        "symbol": data.get("display_name"),
        "species": sp,
        "biotype": data.get("biotype"),
        "description": data.get("description"),
        "seq_region": data.get("seq_region_name"),
        "start": data.get("start"),
        "end": data.get("end"),
        "strand": data.get("strand"),
        "assembly": data.get("assembly_name"),
        "canonical_transcript": data.get("canonical_transcript"),
        "source": data.get("source"),
        "logic_name": data.get("logic_name"),
        "ensembl_url": _ensembl_gene_url(sp, gene_id),
        # Only present when expand=True.
        "transcripts": data.get("Transcript"),
    }


@mcp.tool()
def search_variants_in_region(
    region: str,
    species: str | None = None,
    limit: int = 25,
) -> dict:
    """List known variants overlapping a genomic region.

    Backed by Ensembl Plants variation catalogs — e.g. the 1001 Genomes
    Project for Arabidopsis, the 3K Rice Genomes Project for rice. Not all
    plant species in Ensembl have variation data; species without a
    variation database return an empty list (not an error).

    Args:
        region: Genomic region as 'chrom:start-end' (1-based, inclusive).
                Examples: '2:8140000-8140100' (Arabidopsis), '1:1000-2000'
                (rice). Use the assembly's native chromosome names — for
                Arabidopsis TAIR10 use '1'..'5', 'Mt', 'Pt' (no 'chr').
        species: Ensembl species name (default 'arabidopsis_thaliana').
        limit: Maximum variants to return (default 25, max 200). The
               Ensembl API itself caps overlap responses; this is a
               client-side truncation.
    """
    species = _normalize_species(species)
    r = (region or "").strip()
    if not r:
        return {"error": "region argument is required (format 'chrom:start-end')"}
    limit = min(max(1, limit), 200)

    fallback = _community_fallback(species, "search_variants_in_region")
    if fallback:
        return fallback

    with _get_client() as client:
        resp = client.get(
            f"/overlap/region/{species}/{r}",
            params={"feature": "variation"},
        )
        if resp.status_code == 400:
            return {
                "error": "Bad region specifier",
                "detail": resp.text,
                "hint": "Ensembl regions are 'chrom:start-end' (1-based). For Arabidopsis use chromosome '1'..'5' without 'chr'.",
            }
        if resp.status_code == 404:
            return {
                "error": "Region not found",
                "region": r,
                "species": species,
            }
        resp.raise_for_status()
        variants = resp.json()

    truncated = len(variants) > limit
    variants = variants[:limit]

    return {
        "region": r,
        "species": species,
        "count": len(variants),
        "truncated": truncated,
        "variants": [
            {
                "variant_id": v.get("id"),
                "ensembl_url": _ensembl_variant_url(species, v.get("id")),
                "seq_region": v.get("seq_region_name"),
                "start": v.get("start"),
                "end": v.get("end"),
                "strand": v.get("strand"),
                "alleles": v.get("alleles"),
                "consequence": v.get("consequence_type"),
                "source": v.get("source"),
                "clinical_significance": v.get("clinical_significance") or None,
            }
            for v in variants
        ],
    }


@mcp.tool()
def get_variant(variant_id: str, species: str | None = None) -> dict:
    """Get full information for a known plant variant by stable ID.

    Args:
        variant_id: Variant stable ID, e.g. 'ENSVATH00237387' (Arabidopsis)
                    or '1001genomes_snp:1:12345' style IDs depending on the
                    catalog.
        species: Ensembl species name (default 'arabidopsis_thaliana').
                 Must match the species whose variation database holds the
                 ID; Ensembl variant IDs are not unique across species.
    """
    species = _normalize_species(species)
    vid = (variant_id or "").strip()
    if not vid:
        return {"error": "variant_id is required"}

    fallback = _community_fallback(species, "get_variant")
    if fallback:
        return fallback

    with _get_client() as client:
        resp = client.get(f"/variation/{species}/{vid}")
        if resp.status_code == 404:
            return {
                "error": "Variant not found",
                "variant_id": vid,
                "species": species,
            }
        resp.raise_for_status()
        data = resp.json()

    return {
        "variant_id": data.get("name") or vid,
        "ensembl_url": _ensembl_variant_url(species, data.get("name") or vid),
        "species": species,
        "variant_class": data.get("var_class"),
        "most_severe_consequence": data.get("most_severe_consequence"),
        "ambiguity": data.get("ambiguity"),
        "minor_allele": data.get("minor_allele"),
        "minor_allele_frequency": data.get("MAF"),
        "ancestral_allele": (data.get("mappings") or [{}])[0].get("ancestral_allele"),
        "source": data.get("source"),
        "synonyms": data.get("synonyms") or [],
        "evidence": data.get("evidence") or [],
        "mappings": [
            {
                "location": m.get("location"),
                "seq_region": m.get("seq_region_name"),
                "start": m.get("start"),
                "end": m.get("end"),
                "strand": m.get("strand"),
                "allele_string": m.get("allele_string"),
                "assembly": m.get("assembly_name"),
            }
            for m in (data.get("mappings") or [])
        ],
    }


@mcp.tool()
def predict_variant_effect(
    region: str | None = None,
    allele: str | None = None,
    variant_id: str | None = None,
    species: str | None = None,
) -> dict:
    """Predict the effect of a variant using Ensembl VEP.

    Two input modes (provide exactly one):
      - region + allele: a novel/unknown variant, e.g. region='2:8140000-8140000',
        allele='T'. Strand defaults to +1; append ':-1' to region for minus
        strand (e.g. '2:8140000-8140000:-1'). For insertions, start = end + 1.
      - variant_id: a known stable ID in the species' variation database.

    Returns per-transcript consequences from Ensembl's VEP (the classical
    rule-based predictor — not a deep-learning model). Each transcript hit
    includes consequence terms (e.g. 'missense_variant'), impact level
    (HIGH/MODERATE/LOW/MODIFIER), and HGVS where applicable.

    Args:
        region: Ensembl region string ('chrom:start-end' or 'chrom:start-end:strand').
        allele: Alternate allele (single nucleotide, multi-nucleotide,
                or '-' for deletions; insertions are encoded by setting
                start = end + 1).
        variant_id: Known variant stable ID, e.g. 'ENSVATH00237387'.
        species: Ensembl species name (default 'arabidopsis_thaliana').
    """
    species = _normalize_species(species)

    if (region is None or allele is None) and not variant_id:
        return {
            "error": "Provide either (region AND allele) for a novel variant, or variant_id for a known variant.",
        }

    if variant_id and (region or allele):
        return {
            "error": "Provide variant_id OR (region+allele), not both.",
        }

    fallback = _community_fallback(species, "predict_variant_effect")
    if fallback:
        return fallback

    with _get_client() as client:
        if variant_id:
            path = f"/vep/{species}/id/{variant_id.strip()}"
        else:
            r = region.strip()
            a = allele.strip()
            path = f"/vep/{species}/region/{r}/{a}"

        resp = client.get(path)
        if resp.status_code == 400:
            return {
                "error": "VEP rejected the request",
                "detail": resp.text,
                "hint": "Check region format (1-based, 'chrom:start-end'), allele case (uppercase nucleotides), and species name.",
            }
        if resp.status_code == 404:
            return {
                "error": "Variant not found (VEP)",
                "variant_id": variant_id,
                "region": region,
                "species": species,
            }
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return {
            "species": species,
            "region": region,
            "variant_id": variant_id,
            "consequences": [],
            "detail": "VEP returned an empty result. The variant may not overlap any annotated transcripts.",
        }

    out_results = []
    for vep in results:
        transcript_hits = []
        for tc in vep.get("transcript_consequences") or []:
            transcript_hits.append({
                "gene_id": tc.get("gene_id"),
                "gene_symbol": tc.get("gene_symbol"),
                "transcript_id": tc.get("transcript_id"),
                "biotype": tc.get("biotype"),
                "consequence_terms": tc.get("consequence_terms"),
                "impact": tc.get("impact"),
                "amino_acids": tc.get("amino_acids"),
                "codons": tc.get("codons"),
                "protein_start": tc.get("protein_start"),
                "protein_end": tc.get("protein_end"),
                "cdna_start": tc.get("cdna_start"),
                "cdna_end": tc.get("cdna_end"),
                "cds_start": tc.get("cds_start"),
                "cds_end": tc.get("cds_end"),
                "distance": tc.get("distance"),
                "strand": tc.get("strand"),
                "hgvsc": tc.get("hgvsc"),
                "hgvsp": tc.get("hgvsp"),
                "sift_prediction": tc.get("sift_prediction"),
                "sift_score": tc.get("sift_score"),
                "polyphen_prediction": tc.get("polyphen_prediction"),
                "polyphen_score": tc.get("polyphen_score"),
            })

        out_results.append({
            "input": vep.get("input"),
            "id": vep.get("id"),
            "allele_string": vep.get("allele_string"),
            "seq_region": vep.get("seq_region_name"),
            "start": vep.get("start"),
            "end": vep.get("end"),
            "strand": vep.get("strand"),
            "assembly": vep.get("assembly_name"),
            "most_severe_consequence": vep.get("most_severe_consequence"),
            "transcript_consequence_count": len(transcript_hits),
            "transcript_consequences": transcript_hits,
            "regulatory_feature_consequences": vep.get("regulatory_feature_consequences") or [],
            "intergenic_consequences": vep.get("intergenic_consequences") or [],
        })

    return {
        "species": species,
        "result_count": len(out_results),
        "results": out_results,
    }


@mcp.tool()
def compare_variants(variant_ids: list[str], species: str | None = None) -> dict:
    """Compare multiple known plant variants side-by-side.

    Issues one /variation lookup per ID and condenses the result. Use this
    instead of looping `get_variant`. Does NOT deduplicate input IDs — strip
    duplicates client-side.

    Args:
        variant_ids: List of Ensembl variant stable IDs (max 10).
        species: Ensembl species name (default 'arabidopsis_thaliana'). All
                 IDs must be from the same species' variation database.
    """
    species = _normalize_species(species)
    if not variant_ids:
        return {"error": "variant_ids must be a non-empty list"}
    if len(variant_ids) > 10:
        return {"error": "compare_variants accepts at most 10 variant IDs per call."}

    fallback = _community_fallback(species, "compare_variants")
    if fallback:
        return fallback

    rows = []
    with _get_client() as client:
        for vid in variant_ids:
            vid = (vid or "").strip()
            if not vid:
                rows.append({"variant_id": vid, "error": "empty ID"})
                continue
            resp = client.get(f"/variation/{species}/{vid}")
            if resp.status_code == 404:
                rows.append({"variant_id": vid, "error": "Variant not found"})
                continue
            resp.raise_for_status()
            data = resp.json()
            mapping = (data.get("mappings") or [{}])[0]
            rows.append({
                "variant_id": data.get("name") or vid,
                "ensembl_url": _ensembl_variant_url(species, data.get("name") or vid),
                "variant_class": data.get("var_class"),
                "most_severe_consequence": data.get("most_severe_consequence"),
                "location": mapping.get("location"),
                "allele_string": mapping.get("allele_string"),
                "minor_allele_frequency": data.get("MAF"),
                "source": data.get("source"),
            })

    return {"species": species, "variants": rows}


@mcp.tool()
def get_orthologs(
    gene: str,
    species: str | None = None,
    target_species: str | None = None,
    target_taxon: int | None = None,
) -> dict:
    """Find orthologs of a plant gene in other plant species.

    The Ensembl Compara plant-species tree powers cross-species translation
    (e.g. 'this Arabidopsis gene I just characterized — what's the rice
    counterpart?'). Returns ortholog stable IDs, target species, ortholog
    type (one2one / one2many / many2many), and taxonomy level of the
    homology call.

    Args:
        gene: Gene symbol or Ensembl stable ID of the source gene.
        species: Ensembl species of the source gene (default 'arabidopsis_thaliana').
        target_species: Optional — restrict to one target species, e.g.
                        'oryza_sativa'. Mutually exclusive with target_taxon.
        target_taxon: Optional — restrict by NCBI taxon ID, e.g. 4577 for
                      Zea mays, 4565 for wheat (Triticum aestivum), 33090
                      for all green plants (Viridiplantae).
    """
    species = _normalize_species(species)
    g = (gene or "").strip()
    if not g:
        return {"error": "gene argument is required"}
    if target_species and target_taxon:
        return {"error": "Provide target_species OR target_taxon, not both."}

    fallback = _community_fallback(species, "get_orthologs")
    if fallback:
        return fallback

    params = {"type": "orthologues", "format": "condensed"}
    if target_species:
        params["target_species"] = _normalize_species(target_species)
    if target_taxon is not None:
        params["target_taxon"] = str(target_taxon)

    with _get_client() as client:
        # Stable-ID first, fall back to symbol. Ensembl returns 400 for
        # non-ID inputs (gene symbols); treat 400 and 404 alike.
        resp = client.get(f"/homology/id/{g}", params=params)
        used_route = "id"
        if resp.status_code in (400, 404):
            resp = client.get(f"/homology/symbol/{species}/{g}", params=params)
            used_route = "symbol"
            if resp.status_code in (400, 404):
                return {
                    "error": "Gene not found for homology lookup",
                    "gene": g,
                    "species": species,
                }
        resp.raise_for_status()
        data = resp.json()

    entries = data.get("data") or []
    orthologs = []
    source_id = None
    for entry in entries:
        source_id = entry.get("id") or source_id
        for h in entry.get("homologies") or []:
            orthologs.append({
                "ortholog_id": h.get("id"),
                "protein_id": h.get("protein_id"),
                "species": h.get("species"),
                "type": h.get("type"),
                "taxonomy_level": h.get("taxonomy_level"),
                "method_link_type": h.get("method_link_type"),
            })

    return {
        "source_gene": g,
        "source_gene_id": source_id,
        "source_species": species,
        "lookup_route": used_route,
        "target_species": target_species,
        "target_taxon": target_taxon,
        "ortholog_count": len(orthologs),
        "orthologs": orthologs,
    }


@mcp.tool()
def get_sequence(
    stable_id: str,
    seq_type: str = "genomic",
    species: str | None = None,
) -> dict:
    """Fetch a sequence by Ensembl Plants stable ID.

    Args:
        stable_id: Gene, transcript, exon, or protein stable ID. Note that
                   gene IDs can yield multiple sequences for non-genomic
                   types — for protein/cdna/cds prefer a transcript ID like
                   'AT2G18790.1' rather than the gene ID 'AT2G18790'.
        seq_type: One of 'genomic', 'cdna', 'cds', 'protein'.
        species: Ensembl species name (default 'arabidopsis_thaliana').
                 Only used as a hint; stable IDs are globally unique.
    """
    species = _normalize_species(species)
    sid = (stable_id or "").strip()
    if not sid:
        return {"error": "stable_id is required"}
    if seq_type not in {"genomic", "cdna", "cds", "protein"}:
        return {
            "error": f"Unknown seq_type {seq_type!r}",
            "valid": ["genomic", "cdna", "cds", "protein"],
        }

    with _get_client() as client:
        resp = client.get(f"/sequence/id/{sid}", params={"type": seq_type})
        if resp.status_code == 404:
            return {"error": "Stable ID not found", "stable_id": sid}
        if resp.status_code == 400:
            return {
                "error": "Bad sequence request",
                "detail": resp.text,
                "hint": "For 'cdna'/'cds'/'protein', pass a transcript ID (e.g. 'AT2G18790.1'), not a gene ID. For 'genomic', a gene ID is fine.",
            }
        resp.raise_for_status()
        data = resp.json()

    return {
        "stable_id": data.get("id") or sid,
        "species": species,
        "seq_type": seq_type,
        "molecule": data.get("molecule"),
        "length": len(data.get("seq") or ""),
        "sequence": data.get("seq"),
        "description": data.get("desc"),
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()
