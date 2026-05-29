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

import concurrent.futures
import copy
import datetime
import hashlib
import json
import math
import os
import pathlib
import random
import re
import time

import httpx
from mcp.server.fastmcp import FastMCP

# PyYAML backs the phenotype ledger (human-readable, machine-parseable
# observation files). It is a declared dependency, but the import is guarded
# so the genomics tools keep working even in a stripped-down environment that
# lacks it — the ledger tools degrade to a structured "install pyyaml" notice
# rather than crashing the whole server at import time.
try:
    import yaml as _yaml
except ImportError:  # pragma: no cover - exercised only without the dep
    _yaml = None

# Medicinal Genomics Kannapedia — public cannabis strain database
# (https://www.kannapedia.net/). Strain pages live at the canonical URL
# pattern below. They expose per-strain plant sex, plant type (chemotype),
# Y-ratio (Y-chromosome marker abundance, a sex-purity check), heterozygosity,
# and gene-level variant calls on canonical cannabinoid synthase genes plus
# strain-of-interest loci (ELF3, FAD2, PHL-2, PKSG, etc.). Files (VCF, BAM,
# FASTQ) are hosted on S3; the strain page links to them.
KANNAPEDIA_BASE_URL = "https://www.kannapedia.net"
KANNAPEDIA_STRAIN_URL_PATTERN = KANNAPEDIA_BASE_URL + "/strains/rsp{rsp_id}"

# Additional living-document databases. Each is free, no-auth, REST/JSON.
# The shared discipline: prefer LIVE queries over static curation. The
# trait atlas is a starting-point map; these endpoints are the primary
# sources that domain experts actually trust.
UNIPROT_BASE_URL = "https://rest.uniprot.org"
EUROPEPMC_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
STRING_BASE_URL = "https://string-db.org/api"
NCBI_DATASETS_BASE_URL = "https://api.ncbi.nlm.nih.gov/datasets/v2"

# Veracity backbone: an evidence map keyed by Ensembl stable ID, populated
# from `evals/atlas_audit.py` against live Ensembl xrefs. Records the
# UniProt/SWISSPROT curation tier, GO term count, Plant Reactome pathway
# memberships, and PDB structure count for each atlas gene. Loaded lazily;
# missing entries return None (find_trait_genes treats absence honestly).
_EVIDENCE_FILE = pathlib.Path(__file__).parent / "atlas_evidence.json"
try:
    _ATLAS_EVIDENCE: dict[str, dict] = json.loads(_EVIDENCE_FILE.read_text())
except FileNotFoundError:
    _ATLAS_EVIDENCE = {}

# Secondary index: symbol → evidence record. The audit resolved many atlas
# genes via symbol lookup; this lets find_trait_genes find them without
# requiring every atlas entry to carry an ensembl_id.
_ATLAS_EVIDENCE_BY_SYMBOL: dict[str, dict] = {
    rec["resolved_via_symbol"]: rec | {"_resolved_id": stable_id}
    for stable_id, rec in _ATLAS_EVIDENCE.items()
    if rec.get("resolved_via_symbol")
}


def _evidence_for_gene(gene: dict) -> dict | None:
    """Find the cached evidence record for an atlas gene entry.

    Tries: (1) explicit ensembl_id → primary index, (2) symbol → secondary
    index. Returns None when neither resolves — the LLM sees an honest
    'evidence unknown' rather than a fabricated tier.
    """
    eid = gene.get("ensembl_id")
    if eid and eid in _ATLAS_EVIDENCE:
        return _ATLAS_EVIDENCE[eid]
    symbol = gene.get("symbol")
    if symbol and symbol in _ATLAS_EVIDENCE_BY_SYMBOL:
        return _ATLAS_EVIDENCE_BY_SYMBOL[symbol]
    return None

BASE_URL = "https://rest.ensembl.org"
DEFAULT_SPECIES = "arabidopsis_thaliana"

# Species Ensembl Plants does NOT currently carry, but that matter to
# Copyleft Cultivars's audience. Hitting these returns a structured pointer
# to community resources rather than a confusing 404.
COMMUNITY_RESOURCES = {
    "cannabis_sativa": {
        "common_name": "Cannabis",
        "reason": "Cannabis sativa is not in Ensembl Plants (federal-research-funding constraints have historically kept Cannabis out of public plant-genomics infrastructure). Cultivars MCP provides domain-specific tooling instead.",
        "alternatives": [
            "lookup_kannapedia_strain(rsp_id=...) — live fetch from Medicinal Genomics Kannapedia for strain chemotype, sex, Y-ratio, heterozygosity, variant calls on canonical cannabis genes (THCAS/CBDAS/CBCAS/ELF3/FAD2/PHL/PKSG), and S3-hosted VCF/FASTQ/BAM links.",
            "cannabis_strain_search_urls(query='...') — search-URL constructors for Kannapedia, Leafly, SeedFinder, NCBI Taxonomy, EuropePMC.",
            "find_trait_genes(trait='cannabinoid_biosynthesis') — the 7-enzyme cannabinoid pathway (CsAAE1 → OLS → OAC → CsPT4 → THCAS/CBDAS/CBCAS) with PubMed citations + UniProt search URLs.",
            "find_trait_genes(trait='cannabis_terpene_profile') — chemotype-defining CsTPS family (myrcene, β-caryophyllene, terpinolene, linalool, α-pinene synthases) from Booth et al. 2017.",
            "find_trait_genes(trait='hemp_compliance') — BT/BD allele system at the THCAS/CBDAS locus, the genetic basis of <0.3% THC hemp compliance.",
            "find_trait_genes(trait='cannabis_sex_and_photoperiod') — MADC2 sex marker, autoflower (Cannabis ruderalis day-neutral) locus, CsELF3.",
            "find_trait_genes(trait='cannabis_disease_resistance') — powdery mildew QTL, MLO orthologs, Cannabis PR1.",
            "CS10 reference genome (Grassa et al. 2021 Plant J): NCBI GCF_900626175.2 — https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_900626175.2/",
            "Cannabis Genome DB (community): https://www.cannabisgenome.org/",
            "Medicinal Genomics Kannapedia: https://www.kannapedia.net/ (community strain database)",
            "JGI Phytozome has draft Cannabis sativa assemblies (login required).",
        ],
    },
    "cannabis": {
        "common_name": "Cannabis",
        "reason": "Cannabis sativa is not in Ensembl Plants. Use species='cannabis_sativa' to get the full fallback with Kannapedia + chemotype-atlas pointers.",
        "alternatives": [
            "See species='cannabis_sativa' for full alternatives table.",
            "lookup_kannapedia_strain(rsp_id=...) for live strain data.",
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
        "8. get_sequence — fetch genomic / cDNA / CDS / protein sequence.\n"
        "9. list_trait_categories — discover the 18 curated natural-"
        "farming-relevant trait categories (drought / salt / cold / heat / "
        "submergence tolerance, N-use efficiency, P uptake, mycorrhizal "
        "symbiosis, rhizobial nodulation, root architecture, defense, "
        "terpene / glucosinolate biosynthesis, flowering, dwarfing, "
        "tillering, aluminum tolerance).\n"
        "10. find_trait_genes — when the user names a TRAIT but not a "
        "gene ('what's known about drought tolerance in sorghum?'), this "
        "is the fastest grounding. Returns canonical gene symbols + the "
        "species each was characterized in.\n"
        "11. translate_trait_to_species — composed shortcut: trait + "
        "target_species in one call. Internally runs find_trait_genes "
        "then issues concurrent ortholog calls to the target species. "
        "Use this when the user asks 'what are the drought genes in MY "
        "crop?' — one call replaces ~7 sequential calls.\n"
        "12. lookup_gene_evidence — the VERACITY backbone. For any "
        "Ensembl Plants gene stable ID, returns the cross-reference "
        "chain: UniProt/SWISSPROT curation tier (manually curated vs. "
        "auto-annotated), GO term count, Plant Reactome pathway "
        "memberships, PDB structures, TAIR/RAP-DB/MaizeGDB authoritative "
        "cross-refs, BioGRID/STRING interaction databases.\n"
        "13. lookup_kannapedia_strain — LIVE fetch from Medicinal "
        "Genomics Kannapedia (https://www.kannapedia.net/) for a Cannabis "
        "strain by RSP ID. Returns chemotype (Plant Type I/II/III), plant "
        "sex, Y-ratio, heterozygosity, rarity, grower attribution, "
        "cannabis genes flagged on the page, and S3-hosted VCF/FASTQ/BAM "
        "URLs for download. The ONLY tool here that targets Cannabis "
        "directly (Cannabis isn't in Ensembl Plants).\n"
        "14. cannabis_strain_search_urls — search-URL constructors for "
        "Kannapedia, Leafly, SeedFinder, NCBI Taxonomy, EuropePMC. Use "
        "this when the user names a cannabis strain by COMMON name "
        "rather than RSP ID — hand them search links to find the IDs.\n"
        "Living-document databases beyond Ensembl Plants:\n"
        "- lookup_uniprot_entry — direct UniProt REST query. Returns "
        "manually-curated function statement, GO terms WITH EVIDENCE "
        "CODES, catalytic activity, cofactors, pathway annotations, "
        "PubMed citations. Works for ANY UniProt-curated protein "
        "including Cannabis genes (THCAS Q8GTB6, CBDAS A6P6V9, OAC "
        "I6WU39) which are NOT in Ensembl Plants.\n"
        "- search_pubmed_for_gene — EuropePMC literature search. Use "
        "to find recent papers on any plant gene + species; returns "
        "title, authors, DOI, PMID, open-access status, citation count. "
        "The 'living' part of literature.\n"
        "- get_string_interactions — STRING-db protein-protein "
        "interaction network. Covers Cannabis sativa (taxon 3483). "
        "Evidence channels: text-mining vs. experimental vs. database "
        "curation — surface these so the LLM grades interactions.\n"
        "- compare_cannabis_strains — composed tool batching up to 5 "
        "Kannapedia strain lookups concurrently for breeder comparison.\n\n"
        "15. list_maize_nam_founders — the 26 maize NAM founder lines "
        "(McMullen 2009 + Hufford 2021 NAM founder genomes). For corn "
        "growers reasoning about heritage maize diversity beyond elite "
        "dent lines: Stiff Stalk (B73/B97), Non-Stiff Stalk (Mo17/Oh43), "
        "Tropical/Subtropical (CIMMYT CML lines, Thai Ki3/Ki11), "
        "Popcorn (Hp301), Sweet Corn (Il14H/P39).\n\n"
        "Veracity note: find_trait_genes results include an 'evidence' "
        "field per gene with the UniProt curation tier (cached from a "
        "live audit). 'high_curated' = manually curated UniProt entry "
        "with PubMed-cited evidence. 73% of atlas entries reach this "
        "tier. Many also carry a primary_ref field citing the original "
        "characterization paper (PubMed ID + author + journal). When "
        "evidence == null, the function description is a literature "
        "handle without a verified xref chain — say so explicitly to "
        "the user.\n\n"
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


# ---------------------------------------------------------------------------
# Trait atlas — curated map from natural-farming-relevant traits to canonical
# gene families. The point: turn this MCP from "wraps Ensembl" into "wraps
# Ensembl with grower-scientist domain knowledge baked in".
#
# Sources are the canonical plant-molecular-biology literature (Yamaguchi-
# Shinozaki/Shinozaki on DREB; Schroeder on SOS pathway; Oldroyd on
# rhizobial/mycorrhizal symbiosis; Khush on Green Revolution dwarfing;
# Sasaki/Maron on Al tolerance; etc.). The atlas is not exhaustive — it's a
# starting-point map for LLM agents serving grower-scientists. Treat each
# entry as a literature handle, not a closed list.
# ---------------------------------------------------------------------------

TRAIT_ATLAS = {
    "drought_tolerance": {
        "description": "Genes governing water-deficit response, including ABA signaling, osmotic-stress regulons, and dehydration-responsive transcription factors.",
        "natural_farming_relevance": "Foundational for marginal-land smallholder agriculture and for landrace varieties selected over centuries on rain-fed plots.",
        "genes": [
            {"symbol": "DREB1A", "alias": "CBF3", "characterized_in": "arabidopsis_thaliana", "function": "Master TF activating the cold/drought response regulon; the canonical entry point for drought engineering.", "primary_ref": "Liu et al. 1998 Plant Cell 10:1391 (PMID 9707537) — original characterization of DREB1A binding to dehydration-responsive element. Kasuga et al. 1999 Nat Biotechnol 17:287 (PMID 10096295) — transgenic overexpression confers drought + freezing tolerance.", "evidence_level": "transgenic_complementation"},
            {"symbol": "DREB2A", "characterized_in": "arabidopsis_thaliana", "function": "TF activating osmotic-stress genes under drought and heat."},
            {"symbol": "OST1", "alias": "SnRK2.6", "ensembl_id": "AT4G33950", "characterized_in": "arabidopsis_thaliana", "function": "ABA-activated kinase, central to stomatal closure under water deficit."},
            {"symbol": "RD29A", "alias": "COR78 / LTI78", "ensembl_id": "AT5G52310", "characterized_in": "arabidopsis_thaliana", "function": "Dehydration-responsive marker gene; classical DREB1A target."},
            {"symbol": "HVA1", "characterized_in": "hordeum_vulgare", "function": "Group 3 LEA protein; barley drought-tolerance marker, transgene-validated in rice and wheat.", "note": "Literature handle — barley HVA1 doesn't resolve by symbol in Ensembl Plants; cited via the source literature (Hong et al. 1988)."},
            {"symbol": "DRO1", "characterized_in": "oryza_sativa", "function": "Deeper-rooting QTL — promotes vertical root growth and drought avoidance in rice."},
        ],
    },
    "salt_tolerance": {
        "description": "Salt Overly Sensitive (SOS) pathway, vacuolar sodium sequestration, and root-to-shoot Na+ exclusion.",
        "natural_farming_relevance": "Critical for coastal and irrigated-arid smallholder farming where soil salinization is rising.",
        "genes": [
            {"symbol": "SOS1", "characterized_in": "arabidopsis_thaliana", "function": "Plasma-membrane Na+/H+ antiporter; root-tip sodium extrusion.", "primary_ref": "Shi et al. 2000 PNAS 97:6896 (PMID 10823923) — sos1 mutant + cloning. Shi et al. 2002 Nat Biotechnol 21:81 — overexpression confers salt tolerance.", "evidence_level": "knockout_phenotype"},
            {"symbol": "SOS2", "alias": "CIPK24", "characterized_in": "arabidopsis_thaliana", "function": "Kinase activating SOS1 under salt; signal-relay step.", "primary_ref": "Liu et al. 2000 PNAS 97:3730 (PMID 10725357) — sos2 mutant identified the salt-overly-sensitive locus 2 kinase.", "evidence_level": "knockout_phenotype"},
            {"symbol": "SOS3", "alias": "CBL4", "characterized_in": "arabidopsis_thaliana", "function": "Ca2+ sensor that perceives salt-induced cytosolic Ca2+ spike.", "primary_ref": "Liu & Zhu 1998 Science 280:1943 (PMID 9632394) — sos3 mutant and Ca2+-sensor characterization.", "evidence_level": "knockout_phenotype"},
            {"symbol": "NHX1", "characterized_in": "arabidopsis_thaliana", "function": "Vacuolar Na+/H+ antiporter — sequesters cytotoxic sodium away from cytoplasm."},
            {"symbol": "HKT1", "characterized_in": "arabidopsis_thaliana", "function": "Na+ transporter; xylem unloading limits Na+ shoot accumulation."},
            {"symbol": "OsHKT1;5", "ensembl_id": "Os01g0307500", "characterized_in": "oryza_sativa", "function": "Rice ortholog of HKT1; Saltol QTL on chromosome 1 in salt-tolerant Pokkali landrace."},
        ],
    },
    "cold_tolerance": {
        "description": "Cold-responsive CBF regulon and freezing-tolerance effectors (osmoprotectants, antifreeze proteins).",
        "natural_farming_relevance": "Vital for high-latitude and high-altitude smallholder farming and heritage-variety winter hardiness.",
        "genes": [
            {"symbol": "CBF1", "alias": "DREB1B", "characterized_in": "arabidopsis_thaliana", "function": "Cold-induced TF; activates COR genes."},
            {"symbol": "CBF2", "alias": "DREB1C", "characterized_in": "arabidopsis_thaliana", "function": "Cold-induced TF, partially redundant with CBF1/3."},
            {"symbol": "ICE1", "characterized_in": "arabidopsis_thaliana", "function": "MYC-like TF; cold-signal upstream activator of CBF expression."},
            {"symbol": "COR15A", "characterized_in": "arabidopsis_thaliana", "function": "Chloroplast-localized cryoprotectant; classical CBF target."},
        ],
    },
    "heat_tolerance": {
        "description": "Heat-shock factors (HSFs), HSP chaperones, and reactive-oxygen-species detox under thermal stress.",
        "natural_farming_relevance": "Increasingly central as growing-season heat extremes intensify in tropical and sub-tropical smallholder zones.",
        "genes": [
            {"symbol": "HsfA1a", "characterized_in": "solanum_lycopersicum", "function": "Master heat-shock TF in tomato; loss-of-function reduces basal and acquired thermotolerance."},
            {"symbol": "HsfA2", "characterized_in": "arabidopsis_thaliana", "function": "Sustains heat response after the initial HsfA1 spike."},
            {"symbol": "HSP70", "characterized_in": "arabidopsis_thaliana", "function": "Canonical chaperone refolding heat-denatured proteins; family of ~14 in Arabidopsis."},
            {"symbol": "HSP101", "alias": "ClpB", "characterized_in": "arabidopsis_thaliana", "function": "AAA+ disaggregase; required for acquired thermotolerance."},
        ],
    },
    "submergence_tolerance": {
        "description": "Rice-specific quiescence vs. escape strategies under flooding; SUB1 (quiescence) and SK1/2 (escape) loci.",
        "natural_farming_relevance": "Hugely important for monsoon-region smallholder rice farmers; SUB1 introgression into mega-varieties was a landmark public-sector breeding success.",
        "genes": [
            {"symbol": "SUB1A", "ensembl_id": "Os09g0286600", "characterized_in": "oryza_sativa", "function": "ERF TF on chromosome 9; suppresses elongation under submergence (quiescence strategy) — basis of Swarna-Sub1 and similar flood-tolerant landrace introgressions.", "primary_ref": "Xu et al. 2006 Nature 442:705 (PMID 16900200) — SUB1A cloning + transgenic complementation. Septiningsih et al. 2009 Ann Bot 103:151 — Swarna-Sub1 introgression line breeding history.", "evidence_level": "transgenic_complementation"},
            {"symbol": "SK1", "characterized_in": "oryza_sativa", "function": "ERF TF in deepwater rice; promotes internode elongation (escape strategy).", "note": "Literature handle — Hattori et al. 2009; not directly resolvable by symbol in current Ensembl Plants."},
            {"symbol": "SK2", "characterized_in": "oryza_sativa", "function": "Paralog of SK1; same elongation-promoting role under submergence.", "note": "Literature handle — Hattori et al. 2009."},
        ],
    },
    "nitrogen_use_efficiency": {
        "description": "Nitrate / ammonium transport and assimilation — uptake, root-to-shoot translocation, and reduction to glutamine.",
        "natural_farming_relevance": "Central to KNF / natural-farming nutrient cycling without synthetic fertilizer; high-NUE varieties extract more from the same biologically-managed soil.",
        "genes": [
            {"symbol": "NRT1.1", "alias": "NPF6.3, CHL1", "characterized_in": "arabidopsis_thaliana", "function": "Dual-affinity nitrate transceptor; also signals nitrate status."},
            {"symbol": "NRT2.1", "ensembl_id": "AT1G08090", "characterized_in": "arabidopsis_thaliana", "function": "High-affinity nitrate transporter; dominant under low-N conditions."},
            {"symbol": "NRT1.1B", "alias": "OsNPF6.5", "ensembl_id": "Os10g0554200", "characterized_in": "oryza_sativa", "function": "Indica-allele variant underlies superior N-use efficiency in indica vs. japonica rice — landrace breeding target.", "primary_ref": "Hu et al. 2015 Nat Genet 47:834 (PMID 26053497) — divergent indica/japonica alleles drive nitrate-uptake difference; the indica variant introgressed into japonica improves NUE.", "evidence_level": "transgenic_complementation"},
            {"symbol": "AMT1;1", "alias": "AMT1.1", "ensembl_id": "AT4G13510", "characterized_in": "arabidopsis_thaliana", "function": "High-affinity ammonium transporter; dominant N source under acidic-soil / paddy conditions."},
            {"symbol": "GS1", "characterized_in": "arabidopsis_thaliana", "function": "Cytosolic glutamine synthetase; assimilates NH4+ into glutamine."},
        ],
    },
    "phosphorus_uptake": {
        "description": "Inorganic phosphate (Pi) uptake transporters and the systemic Pi-starvation response.",
        "natural_farming_relevance": "Phosphorus is the limiting nutrient on weathered tropical soils common to smallholder agriculture; high-P-efficiency varieties + mycorrhizal symbiosis are the natural-farming answer to fertilizer P.",
        "genes": [
            {"symbol": "PHT1;1", "alias": "PHT1.1", "ensembl_id": "AT5G43350", "characterized_in": "arabidopsis_thaliana", "function": "Root high-affinity Pi transporter."},
            {"symbol": "PHO2", "alias": "UBC24", "characterized_in": "arabidopsis_thaliana", "function": "E2 ubiquitin ligase that down-regulates Pi uptake under P-replete conditions; miR399 target."},
            {"symbol": "PHR1", "characterized_in": "arabidopsis_thaliana", "function": "Master TF of the Pi-starvation response."},
            {"symbol": "PSTOL1", "ensembl_id": "Os12g0552900", "characterized_in": "oryza_sativa", "function": "Phosphorus-Starvation Tolerance 1 — protein kinase; the Kasalath landrace allele dramatically improves rice P uptake on low-P soils. A canonical public-sector breeding success.", "primary_ref": "Gamuyao et al. 2012 Nature 488:535 (PMID 22914168) — PSTOL1 cloning from Kasalath, transgenic complementation in IR74 background.", "evidence_level": "transgenic_complementation"},
        ],
    },
    "iron_uptake": {
        "description": "Strategy I (reductive) and Strategy II (chelative) iron acquisition under Fe-limited soils.",
        "natural_farming_relevance": "Iron biofortification + uptake-on-calcareous-soils are smallholder-nutrition priorities (HarvestPlus etc.).",
        "genes": [
            {"symbol": "IRT1", "characterized_in": "arabidopsis_thaliana", "function": "Root Fe2+ transporter (Strategy I); also takes up Zn, Mn, Cd — bottleneck for biofortification AND cadmium-accumulation."},
            {"symbol": "FRO2", "characterized_in": "arabidopsis_thaliana", "function": "Root-surface Fe3+ reductase; Strategy I."},
            {"symbol": "FIT", "alias": "FER / FIT1", "ensembl_id": "AT2G28160", "characterized_in": "arabidopsis_thaliana", "function": "bHLH TF; master regulator of Strategy I Fe response."},
            {"symbol": "IDS3", "characterized_in": "hordeum_vulgare", "function": "Mugineic-acid biosynthesis; grass Strategy II Fe chelator.", "note": "Literature handle — Nakanishi et al. 2000; not directly resolvable by symbol."},
        ],
    },
    "mycorrhizal_symbiosis": {
        "description": "Common symbiosis (SYM) pathway enabling arbuscular mycorrhizal (AM) fungal colonization of root cells.",
        "natural_farming_relevance": "Central to Korean Natural Farming and JADAM nutrient strategies — AM fungi extend root reach and bridge plants to P, Zn, water. Most flowering plants are AM-competent.",
        "genes": [
            {"symbol": "SYMRK", "alias": "DMI2", "characterized_in": "medicago_truncatula", "function": "LRR receptor-like kinase essential for both AM and rhizobial symbiosis.", "note": "Literature handle — Endre et al. 2002; not directly resolvable by symbol in current Ensembl Plants Medicago build."},
            {"symbol": "CCaMK", "alias": "DMI3", "characterized_in": "medicago_truncatula", "function": "Ca2+/calmodulin-dependent kinase decoding the symbiosis-specific calcium spike."},
            {"symbol": "DMI1", "characterized_in": "medicago_truncatula", "function": "Cation channel required for symbiosis Ca2+ signaling."},
            {"symbol": "PT4", "alias": "PHT1;4", "characterized_in": "medicago_truncatula", "function": "Arbuscule-specific Pi transporter — receives P from the fungal symbiont."},
            {"symbol": "RAM1", "characterized_in": "medicago_truncatula", "function": "GRAS-domain TF required for arbuscule branching and maintenance."},
            {"symbol": "GAI", "alias": "DELLA family", "ensembl_id": "AT1G14920", "characterized_in": "arabidopsis_thaliana", "function": "GA-signaling repressor — DELLA family member required for AM colonization; ties symbiosis to gibberellin signaling."},
        ],
    },
    "rhizobial_nodulation": {
        "description": "Legume-specific nitrogen-fixing root-nodule symbiosis with rhizobia; shares the SYM pathway upstream with mycorrhizal signaling. Listed in Medicago truncatula (an Ensembl Plants species) for direct lookup; Lotus japonicus is the other classical model but is not currently in Ensembl Plants.",
        "natural_farming_relevance": "The atmospheric-N-fixation engine of legume-based natural farming and cover cropping (cowpea, common bean, hairy vetch, faba bean).",
        "genes": [
            {"symbol": "NFP", "alias": "Lotus NFR5 ortholog", "characterized_in": "medicago_truncatula", "function": "LysM receptor kinase perceiving rhizobial Nod factor; Medicago counterpart to Lotus NFR5."},
            {"symbol": "LYK3", "alias": "Lotus NFR1 ortholog", "characterized_in": "medicago_truncatula", "function": "Co-receptor for Nod-factor perception; Medicago counterpart to Lotus NFR1."},
            {"symbol": "NIN", "characterized_in": "medicago_truncatula", "function": "Nodulation-specific TF — master regulator of nodule organogenesis."},
            {"symbol": "ERN1", "characterized_in": "medicago_truncatula", "function": "ERF TF required for infection-thread formation."},
            {"symbol": "NSP1", "characterized_in": "medicago_truncatula", "function": "GRAS-domain TF activating early Nod-factor responses.", "note": "Literature handle — Smit et al. 2005; not directly resolvable by symbol in current Medicago build."},
        ],
    },
    "root_architecture": {
        "description": "Lateral-root development, root depth, and root-hair density — the plant's interface with soil.",
        "natural_farming_relevance": "Root architecture is the *physical* interface to KNF-managed soil biology; deeper / denser / hairier roots = more rhizosphere recruitment, more drought escape, more nutrient capture.",
        "genes": [
            {"symbol": "EIR1", "alias": "PIN2", "ensembl_id": "AT5G57090", "characterized_in": "arabidopsis_thaliana", "function": "Auxin efflux carrier directing root-tip gravitropism. Ensembl Plants display name is EIR1; literature commonly uses PIN2."},
            {"symbol": "NPH4", "alias": "ARF7", "ensembl_id": "AT5G20730", "characterized_in": "arabidopsis_thaliana", "function": "Auxin response factor; master regulator of lateral-root initiation. Ensembl Plants display name is NPH4; literature commonly uses ARF7."},
            {"symbol": "LBD16", "characterized_in": "arabidopsis_thaliana", "function": "Lateral-organ-boundary TF; specifies lateral-root founder cells."},
            {"symbol": "RHD6", "characterized_in": "arabidopsis_thaliana", "function": "bHLH TF; master regulator of root-hair cell fate."},
            {"symbol": "DRO1", "characterized_in": "oryza_sativa", "function": "Deep-Rooting 1 — promotes vertical root growth; drought-avoidance QTL."},
        ],
    },
    "defense_jasmonate": {
        "description": "Jasmonic acid signaling pathway — defense against necrotrophic pathogens and chewing herbivores.",
        "natural_farming_relevance": "Direct counterpart in plants to KNF's natural-pest-management strategies; understanding which alleles support strong JA signaling helps select pest-tolerant landraces.",
        "genes": [
            {"symbol": "COI1", "characterized_in": "arabidopsis_thaliana", "function": "F-box JA receptor; the core JA-Ile binding component."},
            {"symbol": "MYC2", "characterized_in": "arabidopsis_thaliana", "function": "Master JA-responsive bHLH TF."},
            {"symbol": "LOX2", "characterized_in": "arabidopsis_thaliana", "function": "Lipoxygenase — early JA biosynthesis."},
            {"symbol": "JAR1", "characterized_in": "arabidopsis_thaliana", "function": "JA-amino acid synthetase — produces bioactive JA-Ile conjugate."},
            {"symbol": "JAZ1", "characterized_in": "arabidopsis_thaliana", "function": "Repressor of MYC2 in unstressed state — degraded by COI1-SCF in response to JA-Ile."},
        ],
    },
    "terpene_biosynthesis": {
        "description": "Terpene synthases — mono-, sesqui- and diterpenes underlying aroma, allelopathy, herbivore deterrence, pollinator attraction.",
        "natural_farming_relevance": "Aroma / pungency / allelopathy in heritage varieties tracks terpene-synthase allele diversity. Strong overlap with Cannabis sativa cultivar work (terpene profiles), even though Cannabis genomics has to be done outside Ensembl Plants.",
        "genes": [
            {"symbol": "TPS21", "characterized_in": "arabidopsis_thaliana", "function": "Sesquiterpene synthase producing (E)-β-caryophyllene."},
            {"symbol": "TPS10", "characterized_in": "zea_mays", "function": "Maize sesquiterpene synthase; (E)-β-farnesene production for indirect parasitoid recruitment."},
            {"symbol": "STO1", "characterized_in": "oryza_sativa", "function": "Diterpene synthase; precursor to momilactones (rice allelopathic compounds)."},
            {"symbol": "OsKS4", "alias": "OsKSL4", "ensembl_id": "Os04g0179700", "characterized_in": "oryza_sativa", "function": "Kaurene synthase-like — momilactone biosynthesis cluster on chromosome 4. Ensembl display name is OsKS4."},
        ],
    },
    "glucosinolate_biosynthesis": {
        "description": "Sulfur-containing defense metabolites unique to Brassicales; precursors to mustard oils.",
        "natural_farming_relevance": "Glucosinolate content drives biofumigation potential of Brassica cover crops (mustard / radish), pest deterrence in heritage Brassica vegetables, and pungency / flavor profiles.",
        "genes": [
            {"symbol": "MYB28", "characterized_in": "arabidopsis_thaliana", "function": "TF regulating aliphatic glucosinolate biosynthesis."},
            {"symbol": "MYB29", "characterized_in": "arabidopsis_thaliana", "function": "Partially redundant with MYB28 for aliphatic GS regulation."},
            {"symbol": "MYB51", "characterized_in": "arabidopsis_thaliana", "function": "TF regulating indolic glucosinolate biosynthesis."},
            {"symbol": "CYP79B2", "characterized_in": "arabidopsis_thaliana", "function": "Cytochrome P450 — first committed step in indolic GS biosynthesis from tryptophan."},
        ],
    },
    "flowering_photoperiod": {
        "description": "Photoperiodic flowering regulation; FT-CO module and floral repressors.",
        "natural_farming_relevance": "Latitude-of-origin and growing-season-fit are heritage-variety properties governed by these genes; understanding them helps seed-keepers reason about why a variety doesn't bolt or fails to flower at a new latitude.",
        "genes": [
            {"symbol": "FT", "characterized_in": "arabidopsis_thaliana", "function": "Florigen — phloem-mobile signal triggering flowering."},
            {"symbol": "CO", "alias": "CONSTANS", "characterized_in": "arabidopsis_thaliana", "function": "Photoperiod-sensitive TF activating FT in long days."},
            {"symbol": "FLC", "characterized_in": "arabidopsis_thaliana", "function": "MADS-box floral repressor silenced by vernalization."},
            {"symbol": "Vrn-A1", "alias": "VRN1", "characterized_in": "triticum_aestivum", "function": "Wheat VRN-A1 — vernalization response; spring vs. winter wheat allelic basis. Ensembl display name uses hyphenated form."},
            {"symbol": "Hd1", "ensembl_id": "Os06g0275000", "characterized_in": "oryza_sativa", "function": "Rice CO ortholog; heading-date QTL underlying photoperiod adaptation across rice latitudes."},
        ],
    },
    "plant_height_dwarfing": {
        "description": "Gibberellin-signaling alleles underlying the Green Revolution semi-dwarf phenotype.",
        "natural_farming_relevance": "Dwarfing alleles trade off against root depth and lodging resistance vs. yield-under-irrigation. Heritage tall varieties carry recessive *wild-type* alleles at these loci — relevant to context-specific landrace selection.",
        "genes": [
            {"symbol": "SD1", "alias": "C20ox2 / OsGA20ox2", "ensembl_id": "Os01g0883800", "characterized_in": "oryza_sativa", "function": "GA20 oxidase — IR8 'miracle rice' semi-dwarf allele underlying the rice Green Revolution. Ensembl display name is C20ox2.", "primary_ref": "Sasaki et al. 2002 Nature 416:701 (PMID 11961545) — sd1 cloning; the IR8 dee-geo-woo-gen-derived loss-of-function allele behind the rice Green Revolution.", "evidence_level": "knockout_phenotype"},
            {"symbol": "Rht-B1", "characterized_in": "triticum_aestivum", "function": "Wheat DELLA — gain-of-function alleles cause Norin-10 semi-dwarfing."},
            {"symbol": "D8", "ensembl_id": "Zm00001eb019200", "characterized_in": "zea_mays", "function": "Maize DELLA; dwarfing allele used in some hybrid backgrounds."},
        ],
    },
    "tiller_branching": {
        "description": "Strigolactone signaling and TB1-family TFs governing shoot branching / tillering architecture.",
        "natural_farming_relevance": "Tiller number is a primary yield-architecture lever in cereals; landrace selection often shifts this trait toward the local growing system.",
        "genes": [
            {"symbol": "TB1", "alias": "tb1 / teosinte branched 1", "ensembl_id": "Zm00001eb287100", "characterized_in": "zea_mays", "function": "TCP-domain TF — single locus underlying the most dramatic morphological difference between maize and teosinte (suppressed tillering). Stable ID is from B73 v5 NAM assembly.", "primary_ref": "Doebley et al. 1995 Genetics 141:333 + Doebley et al. 1997 Nature 386:485 (PMID 9087409) — tb1 cloning and the teosinte-maize domestication QTL.", "evidence_level": "qtl_mapped"},
            {"symbol": "MAX2", "characterized_in": "arabidopsis_thaliana", "function": "F-box strigolactone-signaling component; loss-of-function = bushy shoots."},
            {"symbol": "D14", "characterized_in": "oryza_sativa", "function": "Strigolactone receptor in rice."},
            {"symbol": "MOC1", "characterized_in": "oryza_sativa", "function": "GRAS TF promoting tiller bud outgrowth."},
        ],
    },
    "aluminum_tolerance": {
        "description": "Root organic-acid efflux (malate / citrate) chelating Al3+ in acidic soils, and the STOP1 transcriptional regulator above it.",
        "natural_farming_relevance": "Al toxicity is THE major constraint on crop yield on acidic tropical soils — the soils where many smallholder farmers work and where heritage landraces have been selected for tolerance over generations.",
        "genes": [
            {"symbol": "ALMT1", "characterized_in": "triticum_aestivum", "function": "Root-tip malate efflux transporter — first cloned Al-tolerance gene; classical wheat tolerance allele.", "primary_ref": "Sasaki et al. 2004 Plant J 37:645 (PMID 14871304) — TaALMT1 cloning from Al-tolerant Atlas 66 wheat.", "evidence_level": "transgenic_complementation"},
            {"symbol": "MATE1", "alias": "AltSB / SbMATE", "characterized_in": "sorghum_bicolor", "function": "Root citrate efflux; the major sorghum Al-tolerance gene.", "primary_ref": "Magalhães et al. 2007 Nat Genet 39:1156 (PMID 17721535) — SbMATE positional cloning from the sorghum AltSB locus.", "evidence_level": "qtl_mapped", "note": "Literature handle — sorghum SbMATE is at locus Sb03g043890 / SORBI_3003G432200 depending on assembly; not directly resolvable by symbol."},
            {"symbol": "STOP1", "characterized_in": "arabidopsis_thaliana", "function": "Zn-finger TF activating ALMT1 and other Al-tolerance genes under acidic conditions."},
        ],
    },
    "cell_wall_biosynthesis": {
        "description": "Cellulose, lignin, and hemicellulose biosynthesis. Determines biomass quality, structural strength, biofuel digestibility, and pest/pathogen mechanical defense.",
        "natural_farming_relevance": "Cell-wall composition controls residue decomposition rates (relevant to KNF / regenerative composting), lodging resistance in heritage cereals, and structural strength in fiber crops. Lignin-modified varieties are easier to convert to biochar or saccharify for on-farm biofuels.",
        "genes": [
            {"symbol": "CESA1", "characterized_in": "arabidopsis_thaliana", "function": "Cellulose synthase catalytic subunit; primary-wall cellulose biosynthesis."},
            {"symbol": "CESA4", "alias": "IRX5", "characterized_in": "arabidopsis_thaliana", "function": "Secondary-wall cellulose synthase; required for normal xylem development."},
            {"symbol": "PAL1", "characterized_in": "arabidopsis_thaliana", "function": "Phenylalanine ammonia-lyase — first committed step in the phenylpropanoid pathway feeding lignin biosynthesis."},
            {"symbol": "CCR1", "characterized_in": "arabidopsis_thaliana", "function": "Cinnamoyl-CoA reductase; key lignin-monomer biosynthesis step. Down-regulation reduces lignin and improves digestibility."},
            {"symbol": "CAD5", "alias": "CAD", "ensembl_id": "AT4G34230", "characterized_in": "arabidopsis_thaliana", "function": "Cinnamyl alcohol dehydrogenase 5; lignin monolignol biosynthesis."},
        ],
    },
    "grain_quality": {
        "description": "Endosperm starch / protein / aroma genes controlling cooking quality, nutrition, and culinary identity of cereal landraces.",
        "natural_farming_relevance": "Heritage cereal varieties (e.g. fragrant basmati / jasmine rices, glutinous rices, high-amylose sorghum, durum/einkorn wheat) carry distinctive grain-quality alleles. These genes underlie the culinary value that smallholder seed-keepers conserve.",
        "genes": [
            {"symbol": "Wx", "alias": "Waxy / GBSSI", "ensembl_id": "Os06g0133000", "characterized_in": "oryza_sativa", "function": "Granule-bound starch synthase; produces amylose. Loss-of-function alleles produce glutinous (waxy) rice; intermediate alleles produce low-amylose varieties (jasmine, basmati)."},
            {"symbol": "BADH2", "alias": "fgr / Fragrant / Os2AP", "ensembl_id": "Os08g0424500", "characterized_in": "oryza_sativa", "function": "Betaine aldehyde dehydrogenase 2; loss-of-function in basmati and jasmine landraces causes 2-acetyl-1-pyrroline accumulation (the popcorn-like fragrance).", "primary_ref": "Bradbury et al. 2005 Plant Biotechnol J 3:363 (PMID 17173626) — fgr/BADH2 cloning; 8-bp deletion accounts for fragrance in basmati and jasmine rices.", "evidence_level": "knockout_phenotype"},
            {"symbol": "GBSSII", "characterized_in": "oryza_sativa", "function": "Soluble starch synthase; controls intermediate amylose levels.", "note": "Literature handle — GBSSII is the soluble paralog of Wx/GBSSI; not directly resolvable by symbol."},
            {"symbol": "GLU-A1", "characterized_in": "triticum_aestivum", "function": "Glutenin subunit — major bread-making quality determinant in wheat.", "note": "Literature handle — high-molecular-weight glutenin loci on wheat 1A; not directly resolvable by symbol."},
        ],
    },
    "cannabinoid_biosynthesis": {
        "description": "Cannabis cannabinoid (CBGA → THCA / CBDA / CBCA) biosynthesis pathway. The seven enzymes building cannabinoids from hexanoate + geranylpyrophosphate.",
        "natural_farming_relevance": "Central to Copyleft Cultivars's cannabis roots. Type I (THC-dominant) vs. Type II (balanced) vs. Type III (CBD-dominant / hemp) chemotypes are governed by the THCAS / CBDAS locus on cannabis chromosome 6 (BT/BD allele system, de Meijer 2003 Genetics 163:335). The full pathway must be understood to reason about heritage cultivars, hemp compliance, and breeder selection.",
        "ensembl_caveat": "Cannabis sativa is NOT in Ensembl Plants. All entries here are literature handles with citations + UniProt search URLs. Use NCBI Gene + the CS10 reference (Grassa et al. 2021, GCF_900626175.2) for stable IDs.",
        "genes": [
            {"symbol": "CsAAE1", "alias": "acyl-activating enzyme 1", "characterized_in": "cannabis_sativa", "function": "Hexanoyl-CoA synthase — produces the activated short-chain fatty-acid precursor that feeds into the olivetol-synthase polyketide pathway. The entry point for cannabinoid biosynthesis from the hexanoate substrate pool.", "primary_ref": "Stout et al. 2012 Plant J 71:353 (PMID 22591452) — CsAAE1 cloning and biochemical characterization.", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=CsAAE1+cannabis", "ncbi_search_url": "https://www.ncbi.nlm.nih.gov/gene/?term=CsAAE1+cannabis+sativa", "note": "Cannabis literature handle — not in Ensembl Plants."},
            {"symbol": "OLS", "alias": "olivetol synthase / TKS / tetraketide synthase", "characterized_in": "cannabis_sativa", "function": "Type III polyketide synthase forming the resorcinolic aromatic ring of cannabinoid scaffolds from malonyl-CoA + hexanoyl-CoA. Produces olivetol and a pentyl tetraketide intermediate; the latter is the substrate for OAC.", "primary_ref": "Taura et al. 2009 FEBS Lett 583:2061 (PMID 19454282) — OLS biochemistry.", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=olivetol+synthase+cannabis", "note": "Cannabis literature handle."},
            {"symbol": "OAC", "alias": "olivetolic acid cyclase", "characterized_in": "cannabis_sativa", "function": "Polyketide cyclase converting the TKS/OLS pentyl tetraketide intermediate into olivetolic acid — the bicyclic precursor that feeds into the prenylation step.", "primary_ref": "Gagne et al. 2012 PNAS 109:12811 (PMID 22802619) — OAC discovery as the missing cyclase.", "evidence_level": "biochemical_activity", "uniprot_id_hint": "I6WU39 (TrEMBL)", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=olivetolic+acid+cyclase+cannabis", "note": "Cannabis literature handle."},
            {"symbol": "CsPT4", "alias": "prenyltransferase 4 / GOT", "characterized_in": "cannabis_sativa", "function": "Aromatic prenyltransferase — transfers geranylpyrophosphate (GPP) onto olivetolic acid to form CBGA (cannabigerolic acid), the universal cannabinoid precursor. Branchpoint of the pathway.", "primary_ref": "Luo et al. 2019 Nature 567:123 (PMID 30814733) — CsPT4 identification + heterologous CBGA production.", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=CsPT4+cannabis", "note": "Cannabis literature handle — found at the cannabinoid biosynthesis cluster."},
            {"symbol": "THCAS", "alias": "tetrahydrocannabinolic acid synthase", "characterized_in": "cannabis_sativa", "function": "Flavin-dependent oxidocyclase converting CBGA → THCA. The Type-I-chemotype-defining enzyme. BT allele (functional) drives high-THC drug-type cannabis; recessive bt allele is associated with hemp-type Type III plants.", "primary_ref": "Sirikantaramas et al. 2004 J Biol Chem 279:39767 + Sirikantaramas et al. 2004 Plant Cell Physiol 45:1607 (PMID 15448381) — THCAS cloning + crystal structure.", "evidence_level": "biochemical_activity", "uniprot_id_hint": "Q8GTB6 (SWISSPROT — canonical THCAS entry)", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=THCAS+OR+Q8GTB6", "note": "Cannabis literature handle — UniProt Q8GTB6 is the manually curated canonical entry; not in Ensembl Plants because Cannabis is not."},
            {"symbol": "CBDAS", "alias": "cannabidiolic acid synthase", "characterized_in": "cannabis_sativa", "function": "Homolog of THCAS at the same chromosomal locus. Catalyzes CBGA → CBDA. Type III hemp chemotypes have a functional CBDAS allele (BD) and a pseudogenized THCAS, producing predominantly CBD with <0.3% THC (the US hemp legal threshold).", "primary_ref": "Taura et al. 2007 FEBS Lett 581:2929 (PMID 17544411) — CBDAS biochemical characterization.", "evidence_level": "biochemical_activity", "uniprot_id_hint": "A6P6V9 (canonical CBDAS entry)", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=CBDAS+OR+A6P6V9", "note": "Cannabis literature handle. The THCAS/CBDAS expression ratio at the BT/BD locus is the primary determinant of hemp-vs-drug-type compliance — Weiblen et al. 2015 New Phytol 208:1241."},
            {"symbol": "CBCAS", "alias": "cannabichromenic acid synthase", "characterized_in": "cannabis_sativa", "function": "Third member of the THCAS/CBDAS/CBCAS gene family at the cannabinoid locus. Catalyzes CBGA → CBCA. Less commercially exploited than THCAS and CBDAS but present in many cultivars; secondary chemotype contributor.", "primary_ref": "Laverty et al. 2019 Genome Res 29:146 (PMID 30409774) — full reference genome describing the cannabinoid synthase cluster organization on chromosome 6.", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=CBCAS+cannabis", "note": "Cannabis literature handle."},
        ],
    },
    "cannabis_terpene_profile": {
        "description": "Cannabis terpene synthase (CsTPS) family — the chemotype-defining aromatic/flavor terpenes that distinguish 'gas', 'haze', 'fruit', and 'pine' lineages.",
        "natural_farming_relevance": "Heritage cannabis cultivar identity is more strongly determined by terpene profile than by THC/CBD ratio. Major CsTPS genes are well-characterized via the Booth et al. 2017 and Booth & Bohlmann 2019 work.",
        "ensembl_caveat": "Cannabis sativa is NOT in Ensembl Plants — all literature handles.",
        "genes": [
            {"symbol": "CsTPS1", "alias": "β-myrcene synthase / CsTPS6", "characterized_in": "cannabis_sativa", "function": "Monoterpene synthase producing β-myrcene — the most abundant terpene in many cannabis cultivars; contributes to the 'earthy / musky' profile and the 'couch-lock' sedative reputation attached to indica-leaning strains.", "primary_ref": "Booth et al. 2017 PLOS ONE 12:e0173911 (PMID 28355238) — biochemical characterization of CsTPS family.", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=myrcene+synthase+cannabis", "note": "Cannabis literature handle. Booth et al. characterized the major CsTPS members."},
            {"symbol": "CsTPS9", "alias": "(E)-β-caryophyllene synthase", "characterized_in": "cannabis_sativa", "function": "Sesquiterpene synthase producing (E)-β-caryophyllene — the dominant 'spicy / peppery' note in many cultivars and a known CB2-receptor selective agonist (dietary cannabinoid).", "primary_ref": "Booth et al. 2017 PLOS ONE 12:e0173911 (PMID 28355238).", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=caryophyllene+synthase+cannabis", "note": "Cannabis literature handle."},
            {"symbol": "CsTPS18", "alias": "terpinolene synthase", "characterized_in": "cannabis_sativa", "function": "Monoterpene synthase producing terpinolene — the dominant terpene in classic Haze lineages and many 'sativa-leaning' chemotypes.", "primary_ref": "Booth et al. 2017 PLOS ONE 12:e0173911 (PMID 28355238).", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=terpinolene+synthase+cannabis", "note": "Cannabis literature handle."},
            {"symbol": "CsTPS3", "alias": "linalool synthase", "characterized_in": "cannabis_sativa", "function": "Monoterpene synthase producing linalool — floral / lavender note, common in many indica and indica-leaning hybrids.", "primary_ref": "Booth et al. 2017 PLOS ONE 12:e0173911 (PMID 28355238).", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=linalool+synthase+cannabis", "note": "Cannabis literature handle."},
            {"symbol": "CsTPS19", "alias": "α-pinene synthase", "characterized_in": "cannabis_sativa", "function": "Monoterpene synthase producing α-pinene — 'pine / forest' note; common in cultivars like Jack Herer and many OG-Kush descendants.", "primary_ref": "Booth et al. 2017 PLOS ONE 12:e0173911 (PMID 28355238).", "evidence_level": "biochemical_activity", "uniprot_search_url": "https://www.uniprot.org/uniprotkb?query=pinene+synthase+cannabis", "note": "Cannabis literature handle."},
        ],
    },
    "cannabis_sex_and_photoperiod": {
        "description": "Genes controlling sex determination (XY system unique among cultivated dioecious crops) and photoperiodic / day-neutral (autoflower) transition in Cannabis.",
        "natural_farming_relevance": "Cannabis is the only major drug/fiber crop in commerce that is dioecious — male/female determination is genetically controlled and matters operationally (males flower and pollinate; growers cull). Autoflower (day-neutral) cultivars trace to Cannabis ruderalis introgression and have a recessive allele in flowering-time machinery; critical for outdoor smallholder cultivation at high latitudes.",
        "ensembl_caveat": "Cannabis sativa is NOT in Ensembl Plants — literature handles.",
        "genes": [
            {"symbol": "MADC2", "alias": "male-associated DNA marker 2", "characterized_in": "cannabis_sativa", "function": "Male-chromosome-linked DNA marker — among the earliest and most reliable PCR-based sex identification markers in Cannabis. Used by tissue-culture and seedling sexing protocols. Sequence-tagged to the Y chromosome.", "primary_ref": "Mandolino et al. 1999 Theor Appl Genet 98:86 — male-associated SCAR markers in hemp.", "evidence_level": "qtl_mapped", "note": "Cannabis literature handle. Kannapedia reports Y-ratio per sample which leverages markers in this region."},
            {"symbol": "CsAuto", "alias": "autoflower locus / Cannabis ruderalis day-neutral", "characterized_in": "cannabis_sativa", "function": "Recessive locus underlying day-neutral autoflowering. Plants flower based on age rather than photoperiod. Originally from Cannabis ruderalis populations of Eastern Europe and Central Asia. Underlying gene mapping is incomplete; candidate-gene literature points at PEBP-family (FT-like) and CsELF3 variants.", "primary_ref": "Sawler et al. 2015 PLOS ONE 10:e0133292 (PMID 26218849) — initial cannabis population genomics. Onofri et al. 2015 Plant Methods 11:24 — characterization of autoflower cultivars.", "evidence_level": "qtl_mapped", "note": "Cannabis literature handle. Active research area; complete causal allele not yet pinpointed in published peer-reviewed work."},
            {"symbol": "CsELF3", "alias": "early-flowering 3", "characterized_in": "cannabis_sativa", "function": "Ortholog of Arabidopsis ELF3 circadian-clock evening-complex component. Splice variants in CsELF3 have been associated with shifted photoperiod sensitivity in Cannabis — candidate contributor to autoflower. Highlighted as variant of interest in Kannapedia strain reports.", "primary_ref": "Hill et al. 2017 PLOS ONE 12:e0179832 (PMID 28658308) — CsELF3 characterization.", "evidence_level": "biochemical_activity", "note": "Cannabis literature handle. Kannapedia flags ELF3 splice variants as 'high-impact' in many strain reports."},
        ],
    },
    "cannabis_disease_resistance": {
        "description": "Pathogen resistance loci in Cannabis — powdery mildew, gray mold (Botrytis), Fusarium, Pythium. Largely emergent area; QTL-mapped not always cloned.",
        "natural_farming_relevance": "Cannabis is high-value, high-disease-pressure crop, especially under indoor/dense outdoor production. Heritage landraces from arid origins (Afghan, Hindu Kush, Moroccan) often carry resistance alleles selected over centuries against local pathogens. Critical for organic / KNF / no-synthetic-fungicide growers.",
        "ensembl_caveat": "Cannabis sativa is NOT in Ensembl Plants — literature handles.",
        "genes": [
            {"symbol": "PMR_loci", "alias": "powdery mildew resistance / Golovinomyces ambrosiae R-genes", "characterized_in": "cannabis_sativa", "function": "Quantitative powdery mildew resistance loci. Mapping populations from resistant landrace × susceptible elite crosses (e.g. Pepper et al. work) identify several major-effect QTL but causal genes are still being cloned (2024-2026).", "primary_ref": "Pepper et al. 2023 Plant Disease — powdery mildew QTL mapping in cannabis. Multiple academic groups (UBC, NC State, UMass) actively working.", "evidence_level": "qtl_mapped", "note": "Cannabis literature handle. Active research."},
            {"symbol": "MLO_orthologs", "alias": "mildew resistance locus O homologs", "characterized_in": "cannabis_sativa", "function": "Cannabis homologs of the canonical MLO susceptibility gene family. In barley, wheat, tomato, cucumber, pea, etc., MLO loss-of-function produces broad-spectrum powdery mildew resistance. Candidate for translation into Cannabis via gene-edited or naturally-occurring loss-of-function alleles.", "primary_ref": "Koh et al. 2018 PLOS ONE 13:e0207468 (PMID 30431893) — initial MLO family characterization in cannabis genome.", "evidence_level": "sequence_similarity_only", "note": "Cannabis literature handle — promising translational target; loss-of-function alleles not yet characterized in commercial cultivars."},
            {"symbol": "PR1", "alias": "pathogenesis-related protein 1", "characterized_in": "cannabis_sativa", "function": "Salicylic-acid-pathway defense marker. Cannabis PR1 ortholog characterized in jasmonate / SA crosstalk studies of cannabis defense response.", "primary_ref": "Conneely et al. 2022 J Cannabis Res 4:1 — cannabis pathogen-response gene expression characterization.", "evidence_level": "sequence_similarity_only", "note": "Cannabis literature handle."},
        ],
    },
    "general_lepidopteran_pest_resistance": {
        "description": "Plant-side defenses against lepidopteran herbivores (caterpillars, armyworms, earworms, budworms) across crops — terpene + glucosinolate emission, protease inhibitors, cysteine proteases (Mir1-CP family).",
        "natural_farming_relevance": "Fall armyworm (Spodoptera frugiperda) invaded Africa from the Americas around 2016 and has spread into Asia, becoming a top smallholder-cereal threat. Native resistance alleles + push-pull intercropping + Bt-free management are the natural-farming responses. Spans maize, sorghum, rice, cannabis (budworm), tomato (tomato hornworm).",
        "genes": [
            {"symbol": "Mir1", "alias": "Mir1-CP", "characterized_in": "zea_mays", "function": "Maize cysteine protease accumulated in the whorl that disrupts lepidopteran peritrophic matrix. Effective against fall armyworm, southwestern corn borer, corn earworm.", "primary_ref": "Pechan et al. 2000 Plant Cell 12:1031 (PMID 10899972).", "evidence_level": "transgenic_complementation"},
            {"symbol": "PI-II", "alias": "Proteinase inhibitor II", "characterized_in": "solanum_lycopersicum", "function": "Wound-induced trypsin/chymotrypsin inhibitor in Solanaceae — limits lepidopteran digestion of plant protein. Canonical jasmonate-pathway defense response output.", "primary_ref": "Pearce et al. 1991 Science 253:895 (PMID 17751816) — systemin/PI-II signaling characterization.", "evidence_level": "transgenic_complementation"},
            {"symbol": "Mi-1.2", "characterized_in": "solanum_lycopersicum", "function": "NB-LRR R gene from Solanum peruvianum providing resistance to root-knot nematodes AND aphids AND whitefly. Rare example of a broad-spectrum invertebrate-resistance gene; central to commercial tomato disease management.", "primary_ref": "Rossi et al. 1998 PNAS 95:9750 (PMID 9707547) — Mi-1.2 cloning.", "evidence_level": "transgenic_complementation"},
            {"symbol": "Cry-receptor_cadherin", "alias": "Bt-toxin receptor", "characterized_in": "zea_mays", "function": "Maize cadherin and aminopeptidase-N family genes that bind Bacillus thuringiensis (Bt) Cry toxins in the lepidopteran midgut. Mutations in these receptors are the dominant mechanism of Cry-toxin resistance evolution in pest populations — relevant to Bt-corn refuge strategy and resistance management.", "primary_ref": "Tabashnik et al. 2013 Nat Biotechnol 31:510 (PMID 23752438) — global review of Bt-resistance evolution.", "evidence_level": "qtl_mapped", "note": "Inverse perspective — these are the host-target genes, mutations in which confer pest *resistance* to Bt corn. Important context for non-Bt natural-farming systems."},
        ],
    },
    "hemp_compliance": {
        "description": "Genetic determinants of THC content for hemp-cultivar legal compliance (<0.3% Δ9-THC in dry flower under US 2018 Farm Bill).",
        "natural_farming_relevance": "Hemp growers face strict THC thresholds. The BT/BD allelic system at the chromosome-6 cannabinoid-synthase locus determines whether a cultivar will trend Type III (CBD-dominant, hemp-compliant) or risk regulatory hot-test failure. Understanding the underlying genetics lets growers select compliant cultivars and breeders fix BD alleles in Type-III lines.",
        "ensembl_caveat": "Cannabis sativa is NOT in Ensembl Plants — literature handles.",
        "genes": [
            {"symbol": "THCAS_pseudogene", "alias": "BT0 / bt", "characterized_in": "cannabis_sativa", "function": "Pseudogenized variant of THCAS at the BT locus — the recessive allele underlying Type III (CBD-dominant) hemp chemotypes. Loss-of-function THCAS combined with functional CBDAS produces hemp-compliant <0.3% Δ9-THC plants.", "primary_ref": "Weiblen et al. 2015 New Phytol 208:1241 (PMID 26242869) — genetic determinants of Type I/II/III chemotypes. de Meijer et al. 2003 Genetics 163:335 — original BT/BD allele system.", "evidence_level": "genetic_mapping", "note": "Cannabis literature handle. Hemp breeders fixing BD/BD homozygotes minimize THC-compliance risk."},
            {"symbol": "CBDAS_functional", "alias": "BD", "characterized_in": "cannabis_sativa", "function": "Functional CBDAS allele at the chromosome-6 cannabinoid-synthase locus — dominant allele in hemp-type Type III plants.", "primary_ref": "Weiblen et al. 2015 New Phytol 208:1241 (PMID 26242869).", "evidence_level": "genetic_mapping", "note": "Cannabis literature handle."},
        ],
    },
    "maize_quality_protein": {
        "description": "Genes underlying improved nutritional protein quality in maize — primarily the opaque-2 / Quality Protein Maize (QPM) system.",
        "natural_farming_relevance": "Quality Protein Maize varieties developed by CIMMYT (Vivek Villegas, Suriphand Vasal) deliver markedly improved lysine + tryptophan content over normal maize — critical for smallholder communities where maize is the staple protein source. Recognized by World Food Prize 2000.",
        "genes": [
            {"symbol": "Opaque-2", "alias": "o2 / O2", "characterized_in": "zea_mays", "function": "bZIP transcription factor regulating zein-storage-protein synthesis in maize endosperm. Loss-of-function o2 alleles reduce zein content, increasing free lysine + tryptophan in the kernel (QPM phenotype). Modified o2 backgrounds with vitreous endosperm modifiers (compensating for opaque-2's chalky-kernel side effect) are the basis of CIMMYT QPM varieties.", "primary_ref": "Schmidt et al. 1990 Science 250:266 (PMID 2218530) — Opaque-2 cloning. Vivek et al. 2008 J Plant Reg 2:107 — CIMMYT QPM-line development.", "evidence_level": "knockout_phenotype", "note": "Resolves in Ensembl Plants — should pull stable ID and UniProt curation via lookup_gene."},
            {"symbol": "Floury-2", "alias": "fl2", "characterized_in": "zea_mays", "function": "α-zein storage protein gene; dominant fl2 mutations cause floury-endosperm phenotype with altered amino-acid composition. Used in combination with o2 in some QPM breeding programs.", "primary_ref": "Coleman et al. 1995 PNAS 92:6828 (PMID 7624331) — fl2 cloning.", "evidence_level": "biochemical_activity"},
        ],
    },
    "maize_disease_resistance": {
        "description": "Major qualitative-resistance loci against the dominant maize foliar and ear diseases — Northern leaf blight (Exserohilum turcicum), gray leaf spot (Cercospora zeae-maydis), fusarium ear rot.",
        "natural_farming_relevance": "Heritage open-pollinated maize varieties carry diverse R-gene alleles selected by smallholder farmers over generations of natural disease pressure. Major-effect resistance loci (Ht1/Ht2/HtN, Rcg1) and quantitative tolerance both matter. Critical for low-input / organic / on-farm seed-saved production where fungicide is not used.",
        "genes": [
            {"symbol": "Ht1", "characterized_in": "zea_mays", "function": "Major-effect dominant resistance gene against Exserohilum turcicum (Northern leaf blight) — produces chlorotic lesions instead of necrotic ones; restricts conidiation. Mapped to chromosome 2; one of the foundational maize disease-resistance loci.", "primary_ref": "Welz & Geiger 2000 Plant Breeding 119:1 — review of Ht1/Ht2/HtN/Htm1 system.", "evidence_level": "qtl_mapped", "note": "Race-specific; widely deployed in breeding but susceptible to NLB race shifts."},
            {"symbol": "Htn1", "alias": "HtN", "characterized_in": "zea_mays", "function": "Quantitative chlorotic-lesion-type resistance to Northern leaf blight; delays lesion development. Mapped to chromosome 8.", "primary_ref": "Hurni et al. 2015 PNAS 112:8780 (PMID 26124137) — Htn1 cloning; encodes a wall-associated kinase.", "evidence_level": "knockout_phenotype"},
            {"symbol": "Rcg1", "characterized_in": "zea_mays", "function": "Major resistance gene against Colletotrichum graminicola (anthracnose stalk rot). Encodes a CC-NB-LRR R protein. Important for high-yield stalk-rot resistance.", "primary_ref": "Frey et al. 2011 Mol Plant Microbe Interact 24:1175 (PMID 21692637) — Rcg1 cloning.", "evidence_level": "transgenic_complementation"},
        ],
    },
    "maize_pest_resistance": {
        "description": "Genetic resistance to lepidopteran maize pests — especially fall armyworm (Spodoptera frugiperda) and corn earworm (Helicoverpa zea).",
        "natural_farming_relevance": "Smallholder farmers in Africa, Latin America, and Asia face devastating fall-armyworm pressure (FAW invaded Africa from the Americas around 2016). Native resistance alleles, including the Mir1-CP cysteine protease, are a non-Bt, no-IP, biological-resistance strategy compatible with smallholder seed saving.",
        "genes": [
            {"symbol": "Mir1", "alias": "Mir1-CP", "characterized_in": "zea_mays", "function": "Maize insect-resistance 1 — a 33 kDa cysteine protease accumulated in the whorl that disrupts the peritrophic matrix of lepidopteran larvae. Discovered in tropical landraces; confers significant fall-armyworm and southwestern-corn-borer resistance.", "primary_ref": "Pechan et al. 2000 Plant Cell 12:1031 (PMID 10899972) — Mir1 / Mir1-CP discovery + function.", "evidence_level": "transgenic_complementation"},
        ],
    },
    "photosynthesis_c4": {
        "description": "C4 carbon-concentrating pathway enzymes — the photosynthetic biochemistry of maize, sorghum, sugarcane, millet that confers high water-use and N-use efficiency under hot conditions.",
        "natural_farming_relevance": "C4 cereals (maize, sorghum, millets) are the staple of many smallholder farming systems in hot, semi-arid regions precisely because C4 photosynthesis outperforms C3 under heat and limited water. Understanding the underlying genes informs heritage-landrace selection.",
        "genes": [
            {"symbol": "PEPC", "alias": "PPC / PPC1", "characterized_in": "zea_mays", "function": "Phosphoenolpyruvate carboxylase — the primary CO2-fixing enzyme of C4 photosynthesis in mesophyll cells.", "note": "Literature handle — maize PEPC family; use Ensembl Compara orthology from Arabidopsis PPC1 (AT1G53310) for cross-species lookup."},
            {"symbol": "NADP-ME", "alias": "ME1 / ZmME", "characterized_in": "zea_mays", "function": "NADP-malic enzyme — decarboxylates malate in bundle-sheath cells, releasing CO2 to Rubisco.", "note": "Literature handle — use ortholog lookup from Arabidopsis NADP-ME1 (AT2G19900) etc."},
            {"symbol": "PPDK", "characterized_in": "zea_mays", "function": "Pyruvate orthophosphate dikinase — regenerates PEP from pyruvate; rate-limiting step in C4 cycle.", "note": "Literature handle — use ortholog lookup from Arabidopsis PPDK (AT4G15530)."},
            {"symbol": "RBCS1A", "alias": "RBCS / Rubisco small subunit", "ensembl_id": "AT1G67090", "characterized_in": "arabidopsis_thaliana", "function": "Rubisco small subunit — the universal carboxylase that both C3 and C4 plants depend on; included for orientation, kinetics differ between C3 and C4 lineages."},
        ],
    },
    # --- Orphan crops -------------------------------------------------------
    # Crops that feed resource-limited farmers but are underrepresented in
    # model-system-funded genomics. Seed entries; see WANTED_TRAITS.yaml and
    # CONTRIBUTING.md '# ORPHAN CROPS BOUNTY' for how to extend. Genes here are
    # literature handles — most of these species are not in Ensembl Plants, so
    # use the cited references + UniProt/NCBI search rather than expecting
    # symbol resolution.
    "teff_drought_tolerance": {
        "description": "Drought-response transcription factors in teff (Eragrostis tef), an Ethiopian C4 cereal prized for waterlogging/drought resilience and gluten-free grain.",
        "natural_farming_relevance": "Teff is a climate-resilient staple for Horn-of-Africa smallholders, grown on marginal rain-fed plots. DREB/NAC regulons underlie its drought escape and avoidance.",
        "genes": [
            {"symbol": "EtDREB2", "alias": "EtDREB family", "characterized_in": "eragrostis_tef", "function": "Dehydration-responsive element-binding TF family; activates the osmotic-stress regulon under water deficit.", "note": "Orphan-crop literature handle — Eragrostis tef is not in Ensembl Plants.", "evidence_level": "sequence_similarity_only"},
            {"symbol": "EtNAC", "alias": "EtNAC stress TFs", "characterized_in": "eragrostis_tef", "function": "NAC-domain transcription factors implicated in teff drought and senescence response.", "note": "Orphan-crop literature handle.", "evidence_level": "sequence_similarity_only"},
        ],
    },
    "cowpea_heat_tolerance": {
        "description": "Heat-shock machinery in cowpea (Vigna unguiculata), a drought- and heat-tolerant legume central to Sahelian food and soil-nitrogen systems.",
        "natural_farming_relevance": "Cowpea fixes nitrogen and tolerates extreme heat; reproductive-stage heat tolerance (pollen viability) is the key smallholder yield-protection trait under warming.",
        "genes": [
            {"symbol": "VuHSP70", "alias": "VuHsp70", "characterized_in": "vigna_unguiculata", "function": "Heat-shock protein 70 chaperone; refolds heat-denatured proteins to protect reproductive tissue.", "note": "Orphan-crop literature handle — use NCBI/UniProt search.", "evidence_level": "biochemical_activity"},
            {"symbol": "VuHSFA2", "alias": "VuHsfA2", "characterized_in": "vigna_unguiculata", "function": "Heat-shock transcription factor A2; sustains the heat-stress response after the initial HsfA1 spike.", "note": "Orphan-crop literature handle.", "evidence_level": "sequence_similarity_only"},
        ],
    },
    "finger_millet_calcium_accumulation": {
        "description": "Seed calcium transport in finger millet (Eleusine coracana), the most calcium-rich cereal grain — a nutritional cornerstone for South Asian and East African smallholders.",
        "natural_farming_relevance": "Finger millet's exceptional seed calcium addresses dietary calcium deficiency without supplements; CAX transporters control grain calcium loading.",
        "genes": [
            {"symbol": "EcCAX1", "alias": "Ca2+/H+ exchanger 1", "characterized_in": "eleusine_coracana", "function": "Vacuolar calcium/proton antiporter; candidate for the high seed-calcium phenotype.", "note": "Orphan-crop literature handle — Eleusine coracana not in Ensembl Plants.", "evidence_level": "sequence_similarity_only"},
            {"symbol": "EcCIPK", "alias": "CBL-interacting kinase", "characterized_in": "eleusine_coracana", "function": "Calcium-signalling kinase implicated in finger-millet calcium and stress signalling.", "note": "Orphan-crop literature handle.", "evidence_level": "sequence_similarity_only"},
        ],
    },
    "pigeon_pea_salinity_tolerance": {
        "description": "Salt-exclusion machinery in pigeon pea (Cajanus cajan), a deep-rooted perennial legume for semi-arid intercropping.",
        "natural_farming_relevance": "Pigeon pea's deep roots and N-fixation rehabilitate degraded and saline-prone soils; SOS-pathway and NHX antiporters underlie its salt tolerance.",
        "genes": [
            {"symbol": "CcSOS1", "characterized_in": "cajanus_cajan", "function": "Plasma-membrane Na+/H+ antiporter; root-tip sodium extrusion (SOS-pathway ortholog).", "note": "Orphan-crop literature handle — Cajanus cajan genome published (Varshney 2012) but not in Ensembl Plants.", "evidence_level": "sequence_similarity_only"},
            {"symbol": "CcNHX1", "characterized_in": "cajanus_cajan", "function": "Vacuolar Na+/H+ antiporter; sequesters cytotoxic sodium into the vacuole.", "note": "Orphan-crop literature handle.", "evidence_level": "sequence_similarity_only"},
        ],
    },
    "amaranth_c4_photosynthesis": {
        "description": "C4 carbon-fixation enzymes in grain amaranth (Amaranthus spp.), a highly nutritious pseudo-cereal with C4 photosynthesis and exceptional heat/drought efficiency.",
        "natural_farming_relevance": "Amaranth combines C4 water/N-use efficiency with high-lysine grain and edible leaves — a resilient smallholder crop across the Americas, Africa, and South Asia.",
        "genes": [
            {"symbol": "AhPEPC", "alias": "PEPC / PPC", "characterized_in": "amaranthus_hypochondriacus", "function": "Phosphoenolpyruvate carboxylase; the primary CO2-fixing enzyme of C4 photosynthesis in mesophyll cells.", "note": "Orphan-crop literature handle — Amaranthus genome assembled (Lightfoot 2017) but not in Ensembl Plants.", "evidence_level": "biochemical_activity"},
            {"symbol": "AhNADP-ME", "alias": "NADP-malic enzyme", "characterized_in": "amaranthus_hypochondriacus", "function": "NADP-malic enzyme; decarboxylates malate in bundle-sheath cells to release CO2 to Rubisco.", "note": "Orphan-crop literature handle.", "evidence_level": "sequence_similarity_only"},
        ],
    },
}


# Species quality grading — surfaces the unevenness of plant variation
# coverage directly inside tool responses. Lets the LLM moderate its claims
# without having to remember species-by-species the way it would from prose.
_SPECIES_QUALITY = {
    "arabidopsis_thaliana": {
        "tier": "richly_covered",
        "variation_source": "1001 Genomes Project (~1,135 accessions, ~12M SNPs)",
        "gene_annotation": "Araport11 (highest curation)",
    },
    "oryza_sativa": {
        "tier": "richly_covered",
        "variation_source": "3K Rice Genomes Project + other catalogs",
        "gene_annotation": "RAPdb / IRGSP-1.0 (high curation)",
    },
    "oryza_indica": {
        "tier": "richly_covered",
        "variation_source": "3K Rice Genomes Project (indica subset)",
        "gene_annotation": "Reference quality",
    },
    "vitis_vinifera": {
        "tier": "moderately_covered",
        "variation_source": "Partial — viticulture-focused catalogs",
        "gene_annotation": "Reference quality",
    },
    "zea_mays": {
        "tier": "moderately_covered",
        "variation_source": "HapMap / NAM panel (some variants exposed)",
        "gene_annotation": "B73 v5 NAM (high curation)",
    },
    "triticum_aestivum": {
        "tier": "moderately_covered",
        "variation_source": "Partial — IWGSC + breeding population resequencing",
        "gene_annotation": "IWGSC (high curation but HEXAPLOID — three subgenomes A/B/D)",
    },
    "solanum_lycopersicum": {
        "tier": "moderately_covered",
        "variation_source": "150 Tomato Genome Project + Varitome",
        "gene_annotation": "Reference quality",
    },
}

# Default for any species that isn't in the explicit table — most plant
# genomes in Ensembl have gene models but no variation database.
_SPECIES_QUALITY_DEFAULT = {
    "tier": "gene_models_only",
    "variation_source": "None or very limited — Ensembl Plants gene models exist but no population-variant catalog. Empty search_variants_in_region results are a data gap, not a tool error.",
    "gene_annotation": "Reference quality (per Ensembl Plants release)",
}


def _species_quality(species: str) -> dict:
    """Return a structured quality grade for the species.

    Surfaced inside tool responses so an LLM doesn't have to remember
    species-by-species which have rich variation data vs. only gene models.
    """
    if species in COMMUNITY_RESOURCES:
        return {"tier": "not_in_ensembl_plants", "see": "community fallback alternatives"}
    return _SPECIES_QUALITY.get(species, _SPECIES_QUALITY_DEFAULT) | {"species": species}


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

# Ensembl REST publishes a ~15 req/s soft limit and returns 429 with a
# Retry-After header when exceeded. The Ensembl best-practices guide also
# notes that 503s during scheduled maintenance / overloaded backend should
# be retried with backoff.
_RETRY_STATUS = {429, 503}
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 0.5


# Test seam: tests inject an httpx.MockTransport via _CLIENT_FACTORY override.
# In normal use this is None and a real client is constructed each call.
_CLIENT_FACTORY: "callable[[], httpx.Client] | None" = None


def _get_client() -> httpx.Client:
    if _CLIENT_FACTORY is not None:
        return _CLIENT_FACTORY()
    return httpx.Client(base_url=BASE_URL, headers=_JSON_HEADERS, timeout=30)


def _get_with_retry(client: httpx.Client, path: str, **kwargs) -> httpx.Response:
    """GET wrapper that honors Retry-After on 429/503, with jitter.

    Used for ALL external APIs (Ensembl, UniProt, EuropePMC, STRING-db,
    Kannapedia) — each can rate-limit and each benefits from the same
    backoff discipline.

    Backoff strategy:
      - If the server sends a Retry-After header, honor it (capped at 30s).
      - Otherwise, exponential backoff: _BASE_BACKOFF_SECONDS * 2^attempt.
      - Add up to 25% jitter to break up concurrent retries from
        ThreadPoolExecutor-spawned workers (the translate_trait_to_species
        path issues up to 6 parallel calls; without jitter they all retry
        at exactly the same instant = thundering herd against the upstream).
      - After _MAX_RETRIES, returns the last response without raising —
        callers continue with their normal status-code handling.
    """
    for attempt in range(_MAX_RETRIES + 1):
        resp = client.get(path, **kwargs)
        if resp.status_code not in _RETRY_STATUS or attempt == _MAX_RETRIES:
            return resp
        retry_after = resp.headers.get("Retry-After")
        try:
            base_wait = float(retry_after) if retry_after else _BASE_BACKOFF_SECONDS * (2 ** attempt)
        except ValueError:
            base_wait = _BASE_BACKOFF_SECONDS * (2 ** attempt)
        # Add up to 25% jitter to decorrelate concurrent retries.
        jitter = random.uniform(0, base_wait * 0.25)
        wait = min(base_wait + jitter, 30.0)
        time.sleep(wait)
    return resp  # unreachable, satisfies type-checker


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
        resp = _get_with_retry(client, "/info/species", params={"division": "EnsemblPlants"})
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
        resp = _get_with_retry(client, f"/lookup/id/{g}", params=params)
        if resp.status_code in (400, 404):
            # Fall back to symbol lookup, which requires species.
            resp = _get_with_retry(client, f"/lookup/symbol/{species}/{g}", params=params)
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


# Named subpopulation pairs used for a coarse Fst sketch when frequency data
# for both is present in an Ensembl variation record.
_FST_SUBPOP_HINTS = {
    "oryza_sativa": ("Indica", "Japonica"),
    "oryza_indica": ("Indica", "Japonica"),
}


def _wright_fst(p1: float, p2: float) -> float:
    """Wright's Fst for a biallelic locus between two equally-weighted subpops.

    p1, p2 = focal-allele frequency in each subpopulation. Fst = (Ht - Hs) / Ht,
    where Hs is the mean within-subpop heterozygosity and Ht the total.
    """
    p_bar = (p1 + p2) / 2
    h_t = 2 * p_bar * (1 - p_bar)
    if h_t == 0:
        return 0.0
    h_s = (p1 * (1 - p1) + p2 * (1 - p2)) / 2
    return round((h_t - h_s) / h_t, 4)


def _population_context(species: str, data: dict) -> dict:
    """Summarise population allele frequencies (and a coarse Fst) from an
    Ensembl variation record fetched with pops=1. Honest about gaps."""
    pops = data.get("populations") or []
    if not pops:
        return {"available": False, "note": "No population frequency data for this variant."}
    per_pop = [
        {
            "population": p.get("population"),
            "allele": p.get("allele"),
            "frequency": p.get("frequency"),
            "allele_count": p.get("allele_count"),
        }
        for p in pops
    ]
    result: dict = {"available": True, "global_maf": data.get("MAF"), "per_population": per_pop}

    sub = _FST_SUBPOP_HINTS.get(species)
    if sub:
        minor = data.get("minor_allele")
        freqs: dict[str, float] = {}
        for p in pops:
            if minor is not None and p.get("allele") != minor:
                continue
            name = p.get("population") or ""
            for label in sub:
                if label.lower() in name.lower() and isinstance(p.get("frequency"), (int, float)):
                    freqs[label] = float(p["frequency"])
        if len(freqs) == 2:
            fst = _wright_fst(freqs[sub[0]], freqs[sub[1]])
            result["fst"] = {"subpopulations": list(sub), "estimate": fst, "frequencies": freqs}
            if fst > 0.3:
                result["population_note"] = (
                    f"This allele shows strong population differentiation (Fst {fst} > 0.3) "
                    f"between {sub[0]} and {sub[1]} subpopulations — likely a target of "
                    "selection or a breeding bottleneck."
                )
            else:
                result["population_note"] = (
                    f"Modest differentiation (Fst {fst}) between {sub[0]} and {sub[1]} subpopulations."
                )
    return result


@mcp.tool()
def search_variants_in_region(
    region: str,
    species: str | None = None,
    limit: int = 25,
    population_context: bool = False,
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
        population_context: If True, adds guidance for retrieving per-population
               allele frequencies + Fst. Region overlap does not carry
               population frequencies, so this surfaces a pointer to call
               get_variant(variant_id, population_context=True) per variant of
               interest rather than fanning out N requests (rate-limit hygiene).
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
        resp = _get_with_retry(
            client,
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

    result = {
        "region": r,
        "species": species,
        "species_quality": _species_quality(species),
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

    if population_context:
        tier = _species_quality(species).get("tier")
        if tier == "richly_covered":
            result["population_context_hint"] = (
                "For per-population allele frequencies and Fst, call "
                "get_variant(variant_id, species, population_context=True) on a "
                "specific variant above. Fanning out frequency lookups for every "
                "variant in a region is avoided here to respect Ensembl rate limits."
            )
        else:
            result["population_context"] = {
                "available": False,
                "note": (
                    f"Population allele-frequency data is only available for "
                    f"richly-covered species; {species} is tier '{tier}'."
                ),
            }

    return result


@mcp.tool()
def get_variant(
    variant_id: str,
    species: str | None = None,
    population_context: bool = False,
) -> dict:
    """Get full information for a known plant variant by stable ID.

    Args:
        variant_id: Variant stable ID, e.g. 'ENSVATH00237387' (Arabidopsis)
                    or '1001genomes_snp:1:12345' style IDs depending on the
                    catalog.
        species: Ensembl species name (default 'arabidopsis_thaliana').
                 Must match the species whose variation database holds the
                 ID; Ensembl variant IDs are not unique across species.
        population_context: If True, fetch per-population allele frequencies
                 (1001 Genomes / 3K Rice Genomes etc.) and, where two named
                 subpopulations are present (e.g. Indica/Japonica for rice),
                 a coarse Wright's Fst. Only meaningful for richly-covered
                 species; otherwise returns a structured explanation.
    """
    species = _normalize_species(species)
    vid = (variant_id or "").strip()
    if not vid:
        return {"error": "variant_id is required"}

    fallback = _community_fallback(species, "get_variant")
    if fallback:
        return fallback

    want_pops = population_context and _species_quality(species).get("tier") == "richly_covered"
    params = {"pops": 1} if want_pops else None

    with _get_client() as client:
        resp = _get_with_retry(client, f"/variation/{species}/{vid}", params=params)
        if resp.status_code == 404:
            return {
                "error": "Variant not found",
                "variant_id": vid,
                "species": species,
            }
        resp.raise_for_status()
        data = resp.json()

    variant_result = {
        "variant_id": data.get("name") or vid,
        "ensembl_url": _ensembl_variant_url(species, data.get("name") or vid),
        "species": species,
        "species_quality": _species_quality(species),
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

    if population_context:
        if want_pops:
            variant_result["population_context"] = _population_context(species, data)
        else:
            variant_result["population_context"] = {
                "available": False,
                "note": (
                    f"Population allele-frequency data is only available for "
                    f"richly-covered species; {species} is tier "
                    f"'{_species_quality(species).get('tier')}'."
                ),
            }

    return variant_result


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

        resp = _get_with_retry(client, path)
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
            resp = _get_with_retry(client, f"/variation/{species}/{vid}")
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
        resp = _get_with_retry(client, f"/homology/id/{g}", params=params)
        used_route = "id"
        if resp.status_code in (400, 404):
            resp = _get_with_retry(client, f"/homology/symbol/{species}/{g}", params=params)
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
        resp = _get_with_retry(client, f"/sequence/id/{sid}", params={"type": seq_type})
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


# ---------------------------------------------------------------------------
# Kannapedia integration — live cannabis strain data
# ---------------------------------------------------------------------------


def _kannapedia_client() -> httpx.Client:
    """Separate client for Kannapedia — different base URL than Ensembl,
    standard browser-like User-Agent because Kannapedia returns HTML not JSON."""
    return httpx.Client(
        base_url=KANNAPEDIA_BASE_URL,
        headers={
            "User-Agent": "cultivars-mcp/0.2 (Copyleft Cultivars; cannabis genomics research)",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=30,
        follow_redirects=True,
    )


_KANNAPEDIA_S3_BASE = "https://mgcdata.s3.amazonaws.com"


def _uniprot_client() -> httpx.Client:
    return httpx.Client(base_url=UNIPROT_BASE_URL, headers={"Accept": "application/json"}, timeout=30)


def _europepmc_client() -> httpx.Client:
    return httpx.Client(base_url=EUROPEPMC_BASE_URL, headers={"Accept": "application/json"}, timeout=30)


def _string_client() -> httpx.Client:
    return httpx.Client(base_url=STRING_BASE_URL, headers={"Accept": "application/json"}, timeout=30)


def _parse_kannapedia_strain_html(html: str, rsp_id: str) -> dict:
    """Parse a Kannapedia strain page HTML into structured fields.

    Robust to layout changes — every field is wrapped in try-except style.
    Missing fields return None rather than failing.
    """
    def _first(pattern: str, flags: int = 0) -> str | None:
        m = re.search(pattern, html, flags)
        return m.group(1).strip() if m else None

    def _all(pattern: str, flags: int = 0) -> list[str]:
        return [m.group(1).strip() for m in re.finditer(pattern, html, flags)]

    # Identity
    strain_name = _first(r"<h1[^>]*>([^<]+)</h1>")
    page_title = _first(r"<title>([^<]+)</title>")

    # Dt/Dd-style attributes (Plant Type, Plant Sex, Report Type, Grower, etc.)
    # Pattern: <dt>LABEL</dt> <dd> <a ...> VALUE <svg
    attrs: dict[str, str] = {}
    for m in re.finditer(
        r"<dt>([^<]+)</dt>\s*<dd>\s*<a[^>]*>\s*([^<]+?)\s*<(?:svg|/a)",
        html,
        re.DOTALL,
    ):
        label = m.group(1).strip()
        value = m.group(2).strip()
        attrs[label] = value

    # Sometimes dd has the value directly without a wrapping anchor:
    for m in re.finditer(r"<dt>([^<]+)</dt>\s*<dd>\s*([^<]+?)\s*</dd>", html, re.DOTALL):
        label = m.group(1).strip()
        value = m.group(2).strip()
        if label not in attrs and value and not value.startswith("<"):
            attrs[label] = value

    # Numeric figcaption fields (Het + Y-Ratio + others)
    het = _first(r"Heterozygosity:\s*<strong>([^<]+)</strong>")
    yratio = _first(r"Y-Ratio Distribution:\s*<strong>([^<]+)</strong>")
    # Rarity is in a SearchLink anchor inside <strong>; pull the anchor text
    rarity_pct = _first(
        r"Rarity:\s*<strong>\s*<a[^>]*>\s*([^<]+?)\s*<(?:svg|/a)",
        re.DOTALL,
    )

    # Grower is in a StrainInfo--registrant block, not a dt/dd
    grower = _first(
        r'StrainInfo--registrant"[^>]*>\s*Grower:\s*<a[^>]*>\s*([^<]+?)\s*<(?:svg|/a)',
        re.DOTALL,
    )

    # S3-hosted data files
    s3_links = set(re.findall(r'href="(https://mgcdata\.s3\.amazonaws\.com/[^"]+)"', html))
    file_groups: dict[str, list[str]] = {
        "annotated_vcf": [u for u in s3_links if "vcf-snpeff-variants" in u and u.endswith(".vcf.gz")],
        "blockchain_vcf": [u for u in s3_links if "vcf_JL" in u and u.endswith(".vcf.gz")],
        "vcf_index": [u for u in s3_links if u.endswith(".vcf.gz.tbi")],
        "fastq_reads": sorted(u for u in s3_links if ".fastq.gz" in u),
        "bam_alignment": sorted(u for u in s3_links if u.endswith(".bam")),
        "bam_index": sorted(u for u in s3_links if u.endswith(".bam.bai")),
    }

    # Related strain pages
    related_ids = sorted({
        m.group(1)
        for m in re.finditer(r'/strains/(rsp\d+)"', html)
        if m.group(1).lower() != rsp_id.lower()
    })

    # Variant-of-interest mentions (look for known gene names in the HTML body)
    cannabis_genes_of_interest = [
        "THCAS", "CBDAS", "CBCAS", "OAC", "CsAAE1", "CsPT4", "OLS",
        "ELF3", "FAD2", "FAD2-2", "PHL-2", "PHL", "EMF1", "EMF1-2",
        "PKSG", "PKSG-4b", "MADC2",
    ]
    mentioned_genes = [g for g in cannabis_genes_of_interest if re.search(rf"\b{re.escape(g)}\b", html)]

    return {
        "rsp_id": rsp_id,
        "url": KANNAPEDIA_STRAIN_URL_PATTERN.format(rsp_id=rsp_id.lower().lstrip("rsp")),
        "strain_name": strain_name,
        "page_title": page_title,
        "attributes": attrs,
        "plant_type_chemotype": attrs.get("Plant Type"),  # Type I/II/III
        "plant_sex": attrs.get("Reported Plant Sex"),
        "report_type": attrs.get("Report Type"),
        "grower": grower or attrs.get("Grower"),
        "rarity_classification": rarity_pct or attrs.get("Rarity"),  # 'Common' / 'Uncommon' / 'Rare'
        "accession_date": attrs.get("Accession Date"),
        "sample_name": attrs.get("Sample Name"),
        "heterozygosity": het,
        "y_ratio_distribution": yratio,
        "rarity_pct": rarity_pct,
        "cannabis_genes_mentioned_on_page": mentioned_genes,
        "data_files": file_groups,
        "related_strains": related_ids[:20],
        "related_strain_count": len(related_ids),
    }


@mcp.tool()
def lookup_kannapedia_strain(rsp_id: str) -> dict:
    """Look up a Cannabis strain in Medicinal Genomics Kannapedia by its RSP ID.

    Kannapedia (https://www.kannapedia.net/) is the canonical public
    cannabis-strain database from Medicinal Genomics — built on
    StrainStat sequencing data with blockchain-stamped records. Each
    strain has an RSP ID (e.g. 'rsp13536', 'rsp13534') and a public
    page showing chemotype (Plant Type I / II / III), plant sex, Y-ratio
    (a Y-chromosome marker indicating sex-purity), heterozygosity,
    cannabinoid-synthase coverage (THCAS / CBDAS / CBCAS), variants on
    canonical cannabis genes (ELF3, FAD2, PHL, PKSG, etc.), file
    downloads (VCF, FASTQ, BAM on S3), and phylogenetic relatives.

    This tool fetches the strain page and parses out the structured
    fields. NOT all Kannapedia data is fetched — the strain page is the
    primary entry point; from there the agent can hand the user the
    direct URLs to S3-hosted data files for offline analysis.

    Args:
        rsp_id: Kannapedia RSP identifier — either 'rsp13536' (lower
                case) or '13536' (numeric only); both accepted.

    Returns: structured strain metadata. Returns an error response with
    the canonical URL if the strain page can't be reached.
    """
    rid = (rsp_id or "").strip().lower()
    rid = rid[3:] if rid.startswith("rsp") else rid
    if not rid.isdigit():
        return {
            "error": f"rsp_id must be numeric or rsp-prefixed numeric (got {rsp_id!r})",
            "expected_format": "rsp13536 or 13536",
        }

    url = f"/strains/rsp{rid}"
    with _kannapedia_client() as client:
        try:
            resp = _get_with_retry(client, url)
        except httpx.HTTPError as e:
            return {
                "error": f"Kannapedia fetch failed: {e}",
                "url": KANNAPEDIA_STRAIN_URL_PATTERN.format(rsp_id=rid),
            }
        if resp.status_code == 404:
            return {
                "error": "Strain not found",
                "rsp_id": f"rsp{rid}",
                "url": KANNAPEDIA_STRAIN_URL_PATTERN.format(rsp_id=rid),
                "hint": "Verify the RSP ID — Kannapedia uses numeric IDs ranging from ~rsp1 to current. Browse https://www.kannapedia.net/strains to discover IDs.",
            }
        if resp.status_code >= 400:
            return {
                "error": f"Kannapedia returned HTTP {resp.status_code}",
                "url": KANNAPEDIA_STRAIN_URL_PATTERN.format(rsp_id=rid),
            }

    parsed = _parse_kannapedia_strain_html(resp.text, f"rsp{rid}")
    parsed["source"] = "Medicinal Genomics Kannapedia (https://www.kannapedia.net/)"
    parsed["data_note"] = (
        "Kannapedia data is from StrainStat WGS / amplicon sequencing of "
        "registered cannabis cultivars. Blockchain-stamped records, "
        "manually-curated grower attribution. Respect Medicinal Genomics's "
        "terms of use; for bulk programmatic access contact them directly."
    )
    return parsed


@mcp.tool()
def compare_cannabis_strains(rsp_ids: list[str]) -> dict:
    """Compare 2-5 Cannabis strains from Kannapedia side-by-side.

    Composed tool: issues `lookup_kannapedia_strain` concurrently for each
    RSP ID and returns a unified table comparing chemotype, sex, het, Y-
    ratio, grower, rarity, and genes flagged on each page. Useful for
    breeders evaluating parents for a cross, or growers comparing
    chemotype claims across strains.

    Args:
        rsp_ids: List of Kannapedia RSP IDs (max 5 per call). Accepts
                 'rsp13536' or '13536' form.

    Returns: structured comparison + a flagged-genes overlap analysis
    (genes mentioned on multiple strain pages).
    """
    if not rsp_ids:
        return {"error": "rsp_ids is required (non-empty list)"}
    if len(rsp_ids) > 5:
        return {"error": "compare_cannabis_strains accepts at most 5 IDs per call to be polite to Kannapedia."}

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lookup_kannapedia_strain, rsp_ids))
    elapsed = time.monotonic() - started

    # Gene-mention overlap
    gene_mentions: dict[str, int] = {}
    for r in results:
        for g in r.get("cannabis_genes_mentioned_on_page", []):
            gene_mentions[g] = gene_mentions.get(g, 0) + 1
    shared_genes = sorted(g for g, n in gene_mentions.items() if n >= 2)

    # Chemotype distribution
    chemotypes = {}
    for r in results:
        ct = r.get("plant_type_chemotype")
        if ct:
            chemotypes[ct] = chemotypes.get(ct, 0) + 1

    # Rarity distribution
    rarities = {}
    for r in results:
        rar = r.get("rarity_classification")
        if rar:
            rarities[rar] = rarities.get(rar, 0) + 1

    return {
        "strain_count": len(results),
        "elapsed_seconds": round(elapsed, 2),
        "chemotype_distribution": chemotypes,
        "rarity_distribution": rarities,
        "genes_flagged_on_multiple_strains": shared_genes,
        "comparison": [
            {
                "rsp_id": r.get("rsp_id"),
                "strain_name": r.get("strain_name"),
                "url": r.get("url"),
                "chemotype": r.get("plant_type_chemotype"),
                "plant_sex": r.get("plant_sex"),
                "heterozygosity": r.get("heterozygosity"),
                "y_ratio": r.get("y_ratio_distribution"),
                "grower": r.get("grower"),
                "rarity": r.get("rarity_classification"),
                "accession_date": r.get("accession_date"),
                "genes_on_page": r.get("cannabis_genes_mentioned_on_page", []),
                "related_strain_count": r.get("related_strain_count"),
                "error": r.get("error"),
            }
            for r in results
        ],
    }


@mcp.tool()
def cannabis_strain_search_urls(query: str) -> dict:
    """Construct strain-lookup URLs for community cannabis databases.

    Kannapedia does not currently expose a public structured search API
    — this tool returns search URLs the agent can hand the user to
    drill in. Covers Kannapedia (Medicinal Genomics), Leafly (community
    strain profiles), SeedFinder (lineage / breeder records), and NCBI
    Taxonomy (for any Cannabis sativa-related accessions in NCBI).

    Args:
        query: Strain name or part of a name, e.g. 'Northern Lights',
               'OG Kush', 'ACDC'.

    Returns: a dict of database -> search URL. No HTTP requests are made.
    """
    q = (query or "").strip()
    if not q:
        return {"error": "query is required"}

    from urllib.parse import quote_plus

    qs = quote_plus(q)
    return {
        "query": q,
        "search_urls": {
            "kannapedia": f"https://www.kannapedia.net/strains?search={qs}",
            "kannapedia_phylotree": "https://www.kannapedia.net/cannabis-phylotree",
            "leafly": f"https://www.leafly.com/search?q={qs}",
            "seedfinder": f"https://en.seedfinder.eu/search/?q={qs}",
            "ncbi_taxonomy": f"https://www.ncbi.nlm.nih.gov/taxonomy/?term={qs}+cannabis",
            "europepmc": f"https://europepmc.org/search?query={qs}+cannabis",
        },
        "note": (
            "Kannapedia search is browser-side; the link above lands you on "
            "the search page. For programmatic strain lookup use "
            "lookup_kannapedia_strain(rsp_id=...) once you have an RSP ID. "
            "Leafly and SeedFinder are community resources — flavor / "
            "lineage / grow notes but NO sequencing data."
        ),
    }


# ---------------------------------------------------------------------------
# NAM founder lines for maize breeders
# ---------------------------------------------------------------------------

_MAIZE_NAM_FOUNDERS = [
    {"line": "B73", "subpopulation": "Stiff Stalk", "origin_notes": "The maize reference; B73 v5 is the Ensembl Plants assembly."},
    {"line": "B97", "subpopulation": "Non-Stiff Stalk", "origin_notes": ""},
    {"line": "CML103", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT tropical inbred."},
    {"line": "CML228", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT — tolerance to highland conditions."},
    {"line": "CML247", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT subtropical."},
    {"line": "CML277", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT."},
    {"line": "CML322", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT — drought tolerance source."},
    {"line": "CML333", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT."},
    {"line": "CML52", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT."},
    {"line": "CML69", "subpopulation": "Tropical / Subtropical", "origin_notes": "CIMMYT."},
    {"line": "Hp301", "subpopulation": "Popcorn", "origin_notes": "Popcorn-type founder."},
    {"line": "Il14H", "subpopulation": "Sweet Corn", "origin_notes": "Sweet-corn-type founder."},
    {"line": "Ki11", "subpopulation": "Tropical / Subtropical", "origin_notes": "Thai-origin tropical inbred."},
    {"line": "Ki3", "subpopulation": "Tropical / Subtropical", "origin_notes": "Thai-origin tropical inbred."},
    {"line": "Ky21", "subpopulation": "Non-Stiff Stalk", "origin_notes": "Kentucky-derived."},
    {"line": "M162W", "subpopulation": "Non-Stiff Stalk", "origin_notes": ""},
    {"line": "M37W", "subpopulation": "Non-Stiff Stalk", "origin_notes": ""},
    {"line": "Mo17", "subpopulation": "Non-Stiff Stalk", "origin_notes": "Classic Missouri-17 inbred; the B73 × Mo17 hybrid was a foundational dent-corn cross."},
    {"line": "Mo18W", "subpopulation": "Non-Stiff Stalk", "origin_notes": ""},
    {"line": "Ms71", "subpopulation": "Non-Stiff Stalk", "origin_notes": ""},
    {"line": "NC350", "subpopulation": "Tropical / Subtropical", "origin_notes": "NC State tropical inbred."},
    {"line": "NC358", "subpopulation": "Tropical / Subtropical", "origin_notes": "NC State tropical inbred."},
    {"line": "Oh43", "subpopulation": "Non-Stiff Stalk", "origin_notes": "Ohio-43; widely used breeding founder."},
    {"line": "Oh7B", "subpopulation": "Non-Stiff Stalk", "origin_notes": "Ohio-7B."},
    {"line": "P39", "subpopulation": "Sweet Corn", "origin_notes": "Sweet-corn-type founder."},
    {"line": "Tx303", "subpopulation": "Non-Stiff Stalk", "origin_notes": "Texas-303."},
    {"line": "Tzi8", "subpopulation": "Tropical / Subtropical", "origin_notes": "Tropical / IITA-derived."},
]


@mcp.tool()
def list_maize_nam_founders(subpopulation: str | None = None) -> dict:
    """List the 26 maize NAM (Nested Association Mapping) founder lines.

    The NAM panel (McMullen et al. 2009 Science 325:737, PMID 19661427)
    is a community resource of 26 diverse maize inbreds × B73 crosses
    used to capture the genetic diversity of cultivated maize for
    breeding and QTL mapping. Each line now has its own reference-quality
    genome assembly (Hufford et al. 2021 Science 373:655, PMID 34353948).
    Subpopulations: Stiff Stalk (B73 + B97 lineage), Non-Stiff Stalk
    (Mo17 lineage), Tropical/Subtropical (CIMMYT + IITA + Thai), Popcorn,
    Sweet Corn. Relevant for corn growers reasoning about heritage maize
    diversity beyond modern dent-corn elite lines.

    Args:
        subpopulation: Optional filter — 'Stiff Stalk', 'Non-Stiff Stalk',
                       'Tropical / Subtropical', 'Popcorn', 'Sweet Corn'.
    """
    founders = _MAIZE_NAM_FOUNDERS
    if subpopulation:
        s = subpopulation.strip()
        founders = [f for f in founders if f["subpopulation"].lower() == s.lower()]

    return {
        "panel": "Maize Nested Association Mapping (NAM)",
        "reference": "McMullen et al. 2009 Science 325:737 (PMID 19661427); Hufford et al. 2021 Science 373:655 (PMID 34353948) — reference-quality NAM founder genomes.",
        "subpopulations": sorted({f["subpopulation"] for f in _MAIZE_NAM_FOUNDERS}),
        "founder_count": len(founders),
        "founders": founders,
        "note": (
            "B73 is the Ensembl Plants reference assembly. The other 25 "
            "founder-line assemblies are at maizeGDB.org and on NCBI. For "
            "smallholder / regenerative breeders, the Tropical/Subtropical "
            "subpopulation (CIMMYT CML lines, IITA Tzi8, Thai Ki3/Ki11) "
            "carries diversity for heat / drought / pest pressures that "
            "elite US dent-corn lines lack."
        ),
    }


@mcp.tool()
def lookup_gene_evidence(stable_id: str, species: str | None = None) -> dict:
    """Pull the evidence trail for a plant gene from Ensembl Plants cross-references.

    This is the *veracity backbone* of the cultivars MCP. For any Ensembl
    Plants gene, returns the cross-references to authoritative external
    databases that an agent (or human) can follow to verify functional
    claims:

      - **UniProt/SWISSPROT** — manually curated function statement,
        GO annotations with evidence codes, PubMed citations. The
        single strongest veracity anchor.
      - **UniProt/SPTREMBL** — automatically annotated UniProt entries
        (lower curation tier).
      - **GO (Gene Ontology)** term count — total functional / process /
        component annotations.
      - **Plant Reactome** pathway memberships.
      - **PDB** — solved protein structures, if any.
      - **TAIR / RAP-DB / MaizeGDB** equivalents — species-specific
        curation sources Ensembl mirrors.
      - **BioGRID / STRING** — protein-protein interaction databases.

    Call this when you need to:
      - Verify that an atlas claim (e.g. 'DREB1A is the master cold-
        response TF') has primary-literature backing.
      - Get the UniProt ID for fetching curated function text externally.
      - Audit a gene's functional-annotation depth before reasoning from
        it.

    Args:
        stable_id: Ensembl Plants gene stable ID (e.g. 'AT2G18790',
                   'Os09g0286600', 'Zm00001eb287100').
        species: Optional Ensembl species name — informational only;
                 stable IDs are globally unique.
    """
    species = _normalize_species(species)
    sid = (stable_id or "").strip()
    if not sid:
        return {"error": "stable_id is required"}

    fallback = _community_fallback(species, "lookup_gene_evidence")
    if fallback:
        return fallback

    with _get_client() as client:
        resp = _get_with_retry(client, f"/xrefs/id/{sid}", params={"all_levels": "1"})
        if resp.status_code in (400, 404):
            return {
                "error": "Stable ID not found or has no cross-references",
                "stable_id": sid,
            }
        resp.raise_for_status()
        xrefs = resp.json()

    # Group cross-references by database, preserving the most informative
    # ones per category.
    by_db: dict[str, list[dict]] = {}
    for x in xrefs:
        by_db.setdefault(x["dbname"], []).append(x)

    def _entry(x: dict) -> dict:
        return {
            "id": x.get("primary_id"),
            "display": x.get("display_id"),
            "description": x.get("description"),
            "info_type": x.get("info_type"),
        }

    # Curated function source — UniProt/SWISSPROT is the gold standard.
    swissprot = [_entry(x) for x in by_db.get("Uniprot/SWISSPROT", [])]
    sptrembl = [_entry(x) for x in by_db.get("Uniprot/SPTREMBL", [])]
    uniprot_gn = [_entry(x) for x in by_db.get("Uniprot_gn", [])]

    # Pathway membership
    reactome_pathways = [_entry(x) for x in by_db.get("Plant_Reactome_Pathway", [])]
    reactome_reactions = [_entry(x) for x in by_db.get("Plant_Reactome_Reaction", [])]

    # Structural / interactions
    pdb = [_entry(x) for x in by_db.get("PDB", [])]
    biogrid = [_entry(x) for x in by_db.get("BioGRID", [])]
    string_xref = [_entry(x) for x in by_db.get("STRING", [])]

    # Species-specific authoritative annotations
    tair = [_entry(x) for x in by_db.get("TAIR_LOCUS", []) + by_db.get("TAIR_SYMBOL", [])]
    refseq = [_entry(x) for x in by_db.get("RefSeq_peptide", []) + by_db.get("RefSeq_mRNA", [])]
    entrez = [_entry(x) for x in by_db.get("EntrezGene", [])]

    # Term-style annotations
    go_count = len(by_db.get("GO", []))
    po_count = len(by_db.get("PO", []))

    # Construct a structured evidence-strength tier
    tier = "minimal"
    if swissprot:
        tier = "high_curated"
    elif sptrembl and go_count > 10:
        tier = "moderate_auto_annotated"
    elif sptrembl or go_count > 0:
        tier = "low_some_annotation"

    # Build external follow-up URLs the LLM can cite directly
    uniprot_url = None
    if swissprot:
        uniprot_url = f"https://www.uniprot.org/uniprotkb/{swissprot[0]['id']}"
    elif sptrembl:
        uniprot_url = f"https://www.uniprot.org/uniprotkb/{sptrembl[0]['id']}"

    pubmed_search_url = (
        f"https://europepmc.org/search?query={sid}" if sid else None
    )

    return {
        "stable_id": sid,
        "species": species,
        "evidence_tier": tier,
        "evidence_tier_description": {
            "high_curated": "UniProt/SWISSPROT entry present — manually curated function with PubMed citations.",
            "moderate_auto_annotated": "UniProt/SPTREMBL entry with substantial GO annotation; auto-annotated but supported.",
            "low_some_annotation": "Some functional annotation present but not in curated UniProt.",
            "minimal": "Cross-references exist but no functional annotation found.",
        }.get(tier),
        "uniprot_curated": swissprot,  # SWISSPROT is the manually curated tier
        "uniprot_auto": sptrembl,       # SPTREMBL is automatic
        "uniprot_gene_names": uniprot_gn,
        "uniprot_lookup_url": uniprot_url,
        "go_term_count": go_count,
        "plant_ontology_count": po_count,
        "plant_reactome_pathways": reactome_pathways,
        "plant_reactome_reactions_count": len(reactome_reactions),
        "pdb_structures": pdb,
        "biogrid_interactions": biogrid,
        "string_xref": string_xref,
        "tair_xref": tair,
        "refseq_xref": refseq,
        "entrez_xref": entrez,
        "all_database_counts": {k: len(v) for k, v in by_db.items()},
        "literature_search_url": pubmed_search_url,
        "note": (
            "The evidence tier is a heuristic over cross-reference presence "
            "— a 'high_curated' tier means UniProt has a hand-reviewed entry "
            "with cited evidence, NOT that any specific functional claim is "
            "verified. To verify a specific claim, follow the uniprot_lookup_url "
            "to the curated function statement and PubMed citations there."
        ),
    }


@mcp.tool()
def lookup_uniprot_entry(uniprot_id: str) -> dict:
    """Pull the manually-curated UniProt entry for a protein.

    Direct UniProt REST query — bypasses Ensembl and works for ANY
    protein UniProt has curated, including Cannabis genes that aren't
    in Ensembl Plants. UniProt is the canonical living document for
    protein function: curators read primary literature and write
    function statements with PubMed citations + GO terms with
    evidence codes (EXP / IDA / IPI / IMP / IGI etc. — the strongest
    levels of GO evidence).

    Critical for plant work because:
      - All canonical cannabis biosynthesis enzymes (THCAS Q8GTB6,
        CBDAS A6P6V9, OAC I6WU39, etc.) have UniProt entries even
        though Cannabis isn't in Ensembl Plants.
      - UniProt PubMed citations are the trail from a function
        statement back to the experimental paper that proved it.
      - GO evidence codes let an agent distinguish "experimentally
        validated" annotations from "inferred from sequence
        similarity".

    Args:
        uniprot_id: UniProt accession, e.g. 'Q8GTB6' (THCAS),
                    'P14713' (Arabidopsis PHYB), 'Q9LKW9' (SOS1).
                    Find these via lookup_gene_evidence or directly
                    from the atlas evidence field.

    Returns: function statement, protein name, organism, sequence
    length, GO term count (with evidence codes), PubMed citations,
    pathway / catalytic activity / cofactor / domain annotations
    where present, and the canonical UniProt URL.
    """
    uid = (uniprot_id or "").strip()
    if not uid:
        return {"error": "uniprot_id is required"}

    with _uniprot_client() as client:
        try:
            resp = _get_with_retry(client, f"/uniprotkb/{uid}")
        except httpx.HTTPError as e:
            return {"error": f"UniProt fetch failed: {e}", "uniprot_id": uid}
        if resp.status_code == 404:
            return {"error": "UniProt entry not found", "uniprot_id": uid}
        resp.raise_for_status()
        data = resp.json()

    # Extract function statement (CC FUNCTION)
    function_statements = []
    pathway_statements = []
    catalytic_activities = []
    cofactors = []
    for c in data.get("comments", []):
        ctype = c.get("commentType")
        if ctype == "FUNCTION":
            for t in c.get("texts", []):
                function_statements.append(t.get("value", "").strip())
        elif ctype == "PATHWAY":
            for t in c.get("texts", []):
                pathway_statements.append(t.get("value", "").strip())
        elif ctype == "CATALYTIC ACTIVITY":
            r = c.get("reaction", {})
            if r:
                catalytic_activities.append({
                    "reaction": r.get("name"),
                    "ecNumber": r.get("ecNumber"),
                })
        elif ctype == "COFACTOR":
            for cof in c.get("cofactors", []):
                cofactors.append(cof.get("name"))

    # Extract GO terms with evidence codes
    go_terms = []
    for x in data.get("uniProtKBCrossReferences", []):
        if x.get("database") == "GO":
            term_name = next((p["value"] for p in x.get("properties", []) if p.get("key") == "GoTerm"), None)
            evidence = next((p["value"] for p in x.get("properties", []) if p.get("key") == "GoEvidenceType"), None)
            go_terms.append({
                "id": x.get("id"),
                "term": term_name,
                "evidence": evidence,
            })

    # Extract PubMed citations
    pubmed_ids = []
    for ref in data.get("references", []):
        cit = ref.get("citation", {})
        for xref in cit.get("citationCrossReferences", []):
            if xref.get("database") == "PubMed":
                pubmed_ids.append(xref.get("id"))

    # Organism
    org = data.get("organism", {})
    organism_name = org.get("scientificName")
    common_name = org.get("commonName")

    # Names
    pn = data.get("proteinDescription", {})
    recommended_name = (pn.get("recommendedName") or {}).get("fullName", {}).get("value")
    gene_names = []
    for g in data.get("genes", []):
        if g.get("geneName"):
            gene_names.append(g["geneName"].get("value"))

    # Sequence
    seq_info = data.get("sequence", {})

    return {
        "uniprot_id": data.get("primaryAccession"),
        "secondary_accessions": data.get("secondaryAccessions") or [],
        "entry_name": data.get("uniProtkbId"),
        "review_status": "SwissProt (manually curated)" if data.get("entryType") == "UniProtKB reviewed (Swiss-Prot)" else "TrEMBL (auto-annotated)",
        "protein_name": recommended_name,
        "gene_names": gene_names,
        "organism": organism_name,
        "organism_common_name": common_name,
        "sequence_length": seq_info.get("length"),
        "sequence_md5": seq_info.get("md5"),
        "function": function_statements,
        "catalytic_activities": catalytic_activities,
        "cofactors": cofactors,
        "pathways": pathway_statements,
        "go_term_count": len(go_terms),
        "go_terms": go_terms[:40],  # cap for response size
        "pubmed_citation_count": len(pubmed_ids),
        "pubmed_ids": pubmed_ids[:30],
        "uniprot_url": f"https://www.uniprot.org/uniprotkb/{uid}",
        "literature_search_url": f"https://europepmc.org/search?query={uid}",
        "note": (
            "UniProt is the canonical curated protein function database. "
            "GO evidence codes carry the strength: EXP/IDA/IPI/IMP/IGI = "
            "experimentally validated; IEA/ISS = inferred. Function "
            "statements are written by curators from primary literature; "
            "follow the pubmed_ids to the source papers."
        ),
    }


@mcp.tool()
def search_pubmed_for_gene(query: str, page_size: int = 10) -> dict:
    """Search Europe PMC for recent literature on a plant gene / trait / species.

    Europe PMC (EBI's open-access PubMed mirror + preprint integration) is
    the living-document literature backbone — when you need to verify a
    claim with a paper newer than the trait atlas, or hunt down the
    seminal characterization paper for a gene the atlas doesn't cover,
    this is the search.

    Returns ranked hits with title + authors + journal + year + DOI +
    open-access status + abstract availability. Direct EuropePMC URLs.

    Args:
        query: Free-text query. Best practice: gene symbol + species,
               e.g. 'OsNRT1.1B rice', 'CsTPS9 cannabis', 'DREB1A
               Arabidopsis drought'. Multi-word queries are AND-ed.
        page_size: Number of hits to return (default 10, max 25).
    """
    q = (query or "").strip()
    if not q:
        return {"error": "query is required"}
    page_size = min(max(1, page_size), 25)

    with _europepmc_client() as client:
        try:
            resp = _get_with_retry(client, "/search", params={
                "query": q,
                "format": "json",
                "resultType": "lite",
                "pageSize": str(page_size),
            })
        except httpx.HTTPError as e:
            return {"error": f"EuropePMC fetch failed: {e}", "query": q}
        if resp.status_code >= 400:
            return {"error": f"EuropePMC returned {resp.status_code}", "query": q}
        data = resp.json()

    results = []
    for r in (data.get("resultList") or {}).get("result", []):
        pmid = r.get("pmid")
        results.append({
            "title": r.get("title"),
            "authors": r.get("authorString"),
            "journal": r.get("journalTitle"),
            "year": r.get("pubYear"),
            "pmid": pmid,
            "pmcid": r.get("pmcid"),
            "doi": r.get("doi"),
            "is_open_access": r.get("isOpenAccess") == "Y",
            "pub_type": r.get("pubType"),
            "cited_by_count": r.get("citedByCount", 0),
            "europepmc_url": f"https://europepmc.org/article/MED/{pmid}" if pmid else None,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            "doi_url": f"https://doi.org/{r.get('doi')}" if r.get("doi") else None,
        })

    return {
        "query": q,
        "total_hits": data.get("hitCount", 0),
        "returned_hits": len(results),
        "results": results,
        "europepmc_search_url": f"https://europepmc.org/search?query={q.replace(' ', '+')}",
        "note": (
            "Europe PMC indexes PubMed + Agricola + Patents + preprints. "
            "Open-access full text available in PMC for is_open_access=true "
            "entries. citedByCount is a rough impact signal but not a "
            "veracity guarantee — read the paper."
        ),
    }


# NCBI taxon IDs of common plant species — used for STRING-db queries which
# require a numeric NCBI Taxonomy ID rather than the Ensembl species name.
_NCBI_TAXON_IDS = {
    "arabidopsis_thaliana": 3702,
    "oryza_sativa": 4530,         # rice (japonica via 39947, generic 4530)
    "oryza_indica": 39946,
    "zea_mays": 4577,
    "sorghum_bicolor": 4558,
    "triticum_aestivum": 4565,
    "hordeum_vulgare": 4513,
    "glycine_max": 3847,
    "phaseolus_vulgaris": 3885,
    "solanum_lycopersicum": 4081,
    "solanum_tuberosum": 4113,
    "vitis_vinifera": 29760,
    "manihot_esculenta": 3983,
    "medicago_truncatula": 3880,
    "brassica_napus": 3708,
    "brassica_rapa": 3711,
    "helianthus_annuus": 4232,
    "cannabis_sativa": 3483,      # STRING covers Cannabis sativa even though Ensembl Plants doesn't
}


@mcp.tool()
def get_string_interactions(
    protein_id: str,
    species: str | None = None,
    score_threshold: int = 400,
    limit: int = 25,
) -> dict:
    """Pull the STRING-db protein-protein interaction network for a plant gene.

    STRING (https://string-db.org/) is the canonical living document of
    protein-protein associations across the tree of life. Evidence
    channels: neighborhood, gene fusion, phylogenetic co-occurrence,
    coexpression, experimental, database curation, text mining.

    Importantly STRING covers Cannabis sativa (taxon 3483) even though
    Ensembl Plants does not — so this tool also serves cannabis genes.

    Args:
        protein_id: Stable ID OR symbol — STRING resolves both. Examples:
                    'AT2G18790' (Arabidopsis PHYB), 'PHYB',
                    'Q8GTB6' (THCAS UniProt), 'THCAS'.
        species: Ensembl-style species name (auto-mapped to NCBI taxon
                 via the lookup table). Defaults to arabidopsis_thaliana.
        score_threshold: STRING combined-score cutoff [0-1000]. 400 =
                         medium confidence (default), 700 = high, 900
                         = highest.
        limit: Max interactions to return (default 25, max 100).
    """
    p = (protein_id or "").strip()
    if not p:
        return {"error": "protein_id is required"}
    sp = _normalize_species(species)
    taxon = _NCBI_TAXON_IDS.get(sp)
    if not taxon:
        return {
            "error": f"No NCBI taxon ID known for species {sp!r}",
            "supported_species": sorted(_NCBI_TAXON_IDS.keys()),
            "hint": "Add the species to _NCBI_TAXON_IDS in server.py or query NCBI Taxonomy for the ID and pass it manually.",
        }
    score_threshold = min(max(0, score_threshold), 1000)
    limit = min(max(1, limit), 100)

    with _string_client() as client:
        try:
            resp = _get_with_retry(client, "/json/network", params={
                "identifiers": p,
                "species": str(taxon),
                "required_score": str(score_threshold),
                "limit": str(limit),
            })
        except httpx.HTTPError as e:
            return {"error": f"STRING-db fetch failed: {e}", "protein_id": p}
        if resp.status_code >= 400:
            return {"error": f"STRING-db returned {resp.status_code}", "protein_id": p, "response": resp.text[:200]}
        edges = resp.json()

    interactions = []
    for e in edges:
        interactions.append({
            "partner_id": e.get("stringId_B"),
            "partner_symbol": e.get("preferredName_B"),
            "combined_score": e.get("score"),
            "evidence_channels": {
                "neighborhood": e.get("nscore"),
                "fusion": e.get("fscore"),
                "phylogenetic": e.get("pscore"),
                "coexpression": e.get("ascore"),
                "experimental": e.get("escore"),
                "database": e.get("dscore"),
                "textmining": e.get("tscore"),
            },
        })

    interactions.sort(key=lambda i: -(i["combined_score"] or 0))

    return {
        "query_protein": p,
        "species": sp,
        "ncbi_taxon_id": taxon,
        "score_threshold": score_threshold,
        "interaction_count": len(interactions),
        "interactions": interactions,
        "string_url": f"https://string-db.org/cgi/network?identifiers={p}&species={taxon}",
        "note": (
            "Combined score 0-1000. Highest-scoring channel is the "
            "dominant evidence type. Text-mining-only edges (tscore high, "
            "others ~0) are weaker than experimental + database curation. "
            "STRING covers Cannabis sativa (taxon 3483) even though "
            "Ensembl Plants does not — so this tool serves cannabis genes."
        ),
    }


@mcp.tool()
def list_trait_categories() -> dict:
    """List the curated natural-farming-relevant trait categories.

    Returns the keys you can pass to `find_trait_genes` plus a short
    description and the count of canonical genes recorded for each trait.

    The atlas is intentionally selective — a starting-point map for
    grower-scientists, not an exhaustive ontology. For each trait, the
    returned genes are characterized in a specific plant species
    (typically Arabidopsis, sometimes rice / wheat / sorghum / Medicago);
    use `get_orthologs` to translate to the species you actually grow.
    """
    return {
        "trait_count": len(TRAIT_ATLAS),
        "traits": {
            key: {
                "description": info["description"],
                "natural_farming_relevance": info["natural_farming_relevance"],
                "gene_count": len(info["genes"]),
            }
            for key, info in TRAIT_ATLAS.items()
        },
        "note": (
            "Curated literature handles, not a closed list. Use "
            "find_trait_genes(trait_key) to drill in, then get_orthologs "
            "to translate canonical species findings to your crop."
        ),
    }


@mcp.tool()
def find_trait_genes(trait: str, target_species: str | None = None) -> dict:
    """Look up canonical genes for a natural-farming-relevant plant trait.

    Returns the curated gene list (symbol, alias, species in which it was
    characterized, one-line function). For Copyleft Cultivars audiences,
    use this as the starting point when a grower-scientist asks about a
    trait without naming a specific gene: "what's known about drought
    tolerance in sorghum?", "which genes underlie symbiosis with
    mycorrhiza?", "what regulates flowering at my latitude?"

    Args:
        trait: One of the keys from list_trait_categories — e.g.
               'drought_tolerance', 'nitrogen_use_efficiency',
               'mycorrhizal_symbiosis', 'aluminum_tolerance',
               'flowering_photoperiod'. Loose matching is applied:
               'drought' will find 'drought_tolerance'.
        target_species: Optional. If provided, the response includes a
                        hint to follow up with get_orthologs for each gene
                        to translate from the characterized species to
                        the target. This tool does NOT issue the ortholog
                        calls itself — calling N HTTP endpoints implicitly
                        would be expensive and obscure failures. The LLM
                        should call get_orthologs explicitly for the
                        genes it wants to follow up on.

    Returns the trait description, the natural-farming relevance note,
    and the gene list. If the trait is unknown, returns the list of
    available trait keys.
    """
    t = (trait or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not t:
        return {
            "error": "trait argument is required",
            "available_traits": sorted(TRAIT_ATLAS.keys()),
        }

    # Exact match first
    entry = TRAIT_ATLAS.get(t)
    matched_key = t if entry else None

    # Loose match: any trait whose key contains the input
    if not entry:
        candidates = [k for k in TRAIT_ATLAS if t in k]
        # Tiebreak: if multiple keys contain the query but exactly one *starts*
        # with it, prefer that. Keeps 'drought' -> 'drought_tolerance' even
        # after orphan-crop keys like 'teff_drought_tolerance' were added.
        if len(candidates) > 1:
            prefix_matches = [k for k in candidates if k.startswith(t)]
            if len(prefix_matches) == 1:
                candidates = prefix_matches
        if len(candidates) == 1:
            matched_key = candidates[0]
            entry = TRAIT_ATLAS[matched_key]
        elif len(candidates) > 1:
            return {
                "error": f"trait {trait!r} is ambiguous",
                "candidates": candidates,
            }

    if not entry:
        return {
            "error": f"trait {trait!r} not in the curated atlas",
            "available_traits": sorted(TRAIT_ATLAS.keys()),
            "note": "The trait atlas is intentionally selective. If your trait isn't here, lookup_gene + get_orthologs on a literature-cited gene symbol is the next step.",
        }

    # Enrich each gene with the cached evidence tier from atlas_evidence.json
    # when available. This is the veracity backbone — populated from a live
    # Ensembl xref audit (see evals/atlas_audit.py). Absent entries return
    # None so LLMs see honest "evidence unknown" rather than fabricated tiers.
    enriched_genes = []
    high_curated_count = 0
    for g in entry["genes"]:
        ev = _evidence_for_gene(g)
        merged = dict(g)
        merged["evidence"] = ev  # None when neither ensembl_id nor symbol match
        if ev and ev.get("evidence_tier") == "high_curated":
            high_curated_count += 1
        enriched_genes.append(merged)

    result = {
        "trait": matched_key,
        "description": entry["description"],
        "natural_farming_relevance": entry["natural_farming_relevance"],
        "gene_count": len(entry["genes"]),
        "high_curated_gene_count": high_curated_count,
        "high_curated_fraction": round(high_curated_count / len(entry["genes"]), 2) if entry["genes"] else 0,
        "evidence_note": (
            "Each gene's 'evidence' field shows the UniProt/SWISSPROT "
            "curation tier from a live Ensembl Plants cross-reference "
            "audit. 'high_curated' means a manually-curated UniProt entry "
            "with PubMed-cited evidence exists. Call lookup_gene_evidence "
            "for the full xref chain on any specific gene. None = audit "
            "could not resolve cross-references; treat the function "
            "description as a literature handle, not a verified claim."
        ),
        "genes": enriched_genes,
    }
    if target_species:
        target = _normalize_species(target_species)
        result["target_species"] = target
        result["target_species_quality"] = _species_quality(target)
        result["followup_hint"] = (
            f"To find the equivalent gene(s) in {target}, call "
            f"translate_trait_to_species(trait='{matched_key}', "
            f"target_species='{target}') for a one-shot batched lookup, OR "
            "call get_orthologs per gene for fine-grained control. "
            "Pay attention to ortholog_one2many results — plants have "
            "undergone whole-genome duplications, so multiple paralogs are "
            "common, especially in maize, wheat (hexaploid), and sugarcane."
        )
    return result


@mcp.tool()
def translate_trait_to_species(trait: str, target_species: str, max_genes: int | None = None) -> dict:
    """Composed tool: trait → canonical genes → orthologs in target species.

    Replaces the common multi-call workflow (find_trait_genes + N×get_orthologs)
    with a single tool call. Issues the ortholog lookups concurrently to keep
    latency bounded — for a 6-gene trait, ~6× speedup vs. sequential.

    For each canonical gene in the trait atlas, this tool calls
    `get_orthologs` from the gene's characterized_in species to the
    target species, then returns a unified table: the canonical gene,
    its function, and the resolved ortholog(s) in the target species
    (with ortholog type and taxonomy level for confidence assessment).

    Args:
        trait: A trait key (loose match accepted, e.g. 'drought' →
               'drought_tolerance'). See list_trait_categories.
        target_species: The species you want answers in, e.g.
                        'sorghum_bicolor', 'oryza_sativa', 'glycine_max'.
        max_genes: Optional cap on how many genes to translate (default
                   all). Use to keep response sizes bounded for traits
                   with many canonical genes.
    """
    # Resolve trait first (reuses find_trait_genes logic — no HTTP)
    trait_result = find_trait_genes(trait=trait)
    if "error" in trait_result:
        return trait_result

    target = _normalize_species(target_species)
    target_fallback = _community_fallback(target, "translate_trait_to_species")
    if target_fallback:
        return target_fallback

    canonical_genes = trait_result["genes"]
    if max_genes:
        canonical_genes = canonical_genes[:max_genes]

    started = time.monotonic()

    def _resolve_one(gene: dict) -> dict:
        source_species = gene["characterized_in"]
        # If the source species isn't in Ensembl Plants, ortholog lookup
        # won't work either — mark unresolvable.
        if source_species in COMMUNITY_RESOURCES:
            return {
                "canonical_gene": gene,
                "ortholog_count": 0,
                "orthologs": [],
                "status": "source_species_not_in_ensembl_plants",
            }
        # Prefer ensembl_id when present (more durable than symbols).
        lookup_handle = gene.get("ensembl_id") or gene["symbol"]
        try:
            ortho = get_orthologs(gene=lookup_handle, species=source_species, target_species=target)
        except httpx.HTTPError as e:
            return {
                "canonical_gene": gene,
                "ortholog_count": 0,
                "orthologs": [],
                "status": f"http_error: {e}",
            }
        except Exception as e:
            # Broader catch: a worker raising any other exception would
            # propagate through pool.map() and crash the whole batch,
            # losing results from the other 5 workers. Per-gene failure
            # should stay per-gene.
            return {
                "canonical_gene": gene,
                "ortholog_count": 0,
                "orthologs": [],
                "status": f"unexpected_error: {type(e).__name__}: {e}",
            }
        if "error" in ortho:
            return {
                "canonical_gene": gene,
                "ortholog_count": 0,
                "orthologs": [],
                "status": ortho["error"],
            }
        return {
            "canonical_gene": gene,
            "ortholog_count": ortho["ortholog_count"],
            "orthologs": ortho["orthologs"],
            "status": "ok",
        }

    # Concurrent ortholog calls. Worker count capped at 6 to be polite to
    # Ensembl REST (their soft limit is ~15 req/sec).
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        translations = list(pool.map(_resolve_one, canonical_genes))

    elapsed = time.monotonic() - started

    successful = sum(1 for t in translations if t["status"] == "ok" and t["ortholog_count"] > 0)
    return {
        "trait": trait_result["trait"],
        "description": trait_result["description"],
        "natural_farming_relevance": trait_result["natural_farming_relevance"],
        "target_species": target,
        "target_species_quality": _species_quality(target),
        "canonical_gene_count": len(canonical_genes),
        "translations_with_orthologs": successful,
        "elapsed_seconds": round(elapsed, 2),
        "translations": translations,
        "note": (
            "Many-to-many ortholog calls are normal in plants due to "
            "whole-genome duplications — translations_with_orthologs counts "
            "canonical genes that resolved to at least one ortholog. A '0' "
            "could mean: gene not in Ensembl Plants source species (e.g. "
            "literature handles flagged in the atlas), or the homology call "
            "doesn't exist in Ensembl Compara for the target species."
        ),
    }


# ===========================================================================
# COMMUNITY SCIENCE LAYER
#
# Everything above this line is read-only: it queries open genomics databases
# and a curated trait atlas. The tools below add the *write* path and the
# scaffolding around it — the participatory-science instrument described in
# the Copyleft Cultivars upgrade brief:
#
#   - submit_phenotype_observation / query_community_phenotypes  (ledger)
#   - verify_observation_integrity                               (Ed25519 attribution)
#   - pin_observation_to_ipfs                                    (content addressing)
#   - estimate_gwas_power                                        (individual -> collective)
#   - resolve_accession                                          (folk name -> formal ID)
#   - query_organellar_variants                                  (Mt/Pt genomes)
#   - export_offline_snapshot                                    (online -> TinyLLamaFarmer)
#   - list_orphan_crop_requests                                  (contribution pipeline)
#
# Design discipline carried over from the read-only layer: honest framing
# (surface limits and provenance), structured responses instead of uncaught
# exceptions, no auth required at runtime, and the test seam pattern
# (`_*_client()` factories) for anything that touches the network.
# ===========================================================================

# Data the ledger is licensed under. The CODE is Apache-2.0 (see LICENSE);
# the community-contributed DATA is ODbL-1.0 (see DATA_LICENSE.md) so that
# derivative databases must stay open — preventing biotech enclosure of the
# commons the way a permissive code license on data would allow.
LEDGER_SCHEMA_VERSION = "1.0"
LEDGER_DATA_LICENSE = "ODbL-1.0"
_VALID_MEASUREMENT_TYPES = {"binary", "continuous", "categorical"}

# GRIN-Global (USDA ARS) REST service — bridges farmer seed names to formal
# accession IDs across 600,000+ holdings. Free, no-auth.
GRIN_BASE_URL = "https://npgsweb.ars-grin.gov/gringlobal/rest"

# kubo (go-ipfs) HTTP API. Localhost by default; overridable for a remote
# pinning gateway. The pinning tool degrades gracefully when this is down.
IPFS_API_URL = os.environ.get("CULTIVARS_IPFS_API", "http://127.0.0.1:5001")


def _ledger_dir() -> pathlib.Path:
    """Directory the phenotype ledger is written to / read from.

    Configurable via CULTIVARS_LEDGER_DIR so a deployment can point the ledger
    at a git working copy (for PR-based submission) or a shared volume.
    Defaults to ./phenotypes relative to the process CWD.
    """
    return pathlib.Path(
        os.environ.get("CULTIVARS_LEDGER_DIR") or (pathlib.Path.cwd() / "phenotypes")
    )


def _snapshots_dir() -> pathlib.Path:
    """Directory the offline-bridge snapshots are written to."""
    return pathlib.Path(
        os.environ.get("CULTIVARS_SNAPSHOTS_DIR") or (pathlib.Path.cwd() / "snapshots")
    )


def _data_dir() -> pathlib.Path:
    """Repo-local data directory (WANTED_TRAITS.yaml etc.)."""
    return pathlib.Path(__file__).parent


_PATH_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _path_safe(value: str) -> str:
    """Collapse anything that isn't a safe filename character to '_'.

    Defends the ledger directory against path traversal in the user-supplied
    accession_id / species / trait that become path components.
    """
    cleaned = _PATH_SAFE_RE.sub("_", (value or "").strip())
    return cleaned.strip("._") or "unknown"


def _known_species() -> set[str]:
    """Species we recognise for ledger submission.

    The quality table + the community-gap list + every species named in the
    trait atlases. The last group matters for the mission: orphan-crop species
    (teff, cowpea, pigeon pea, …) appear as atlas `characterized_in` values but
    are NOT in Ensembl Plants — a teff grower must still be able to submit a
    teff observation, so atlas-referenced species count as known.
    """
    known = set(_SPECIES_QUALITY) | set(COMMUNITY_RESOURCES)
    for entry in TRAIT_ATLAS.values():
        for gene in entry.get("genes", []):
            sp = gene.get("characterized_in")
            if sp:
                known.add(sp)
    for entry in ORGANELLAR_TRAITS.values():
        for gene in entry.get("genes", []):
            sp = gene.get("characterized_in")
            if sp:
                known.add(sp)
    return known


def _valid_trait_category(trait: str) -> bool:
    return trait in TRAIT_ATLAS or trait in ORGANELLAR_TRAITS


def _canonical_observation_bytes(obs: dict) -> bytes:
    """Deterministic bytes for signing/verifying an observation.

    Canonical form = JSON, sorted keys, compact separators, with the volatile
    `provenance.signature` field removed (you cannot sign a document that
    contains its own signature). Both the signer and the verifier MUST derive
    the bytes the same way; JSON-with-sorted-keys is used rather than YAML
    because YAML serialisation is not canonical across emitters.
    """
    clean = copy.deepcopy(obs)
    prov = clean.get("provenance")
    if isinstance(prov, dict):
        prov.pop("signature", None)
    return json.dumps(
        clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _content_hash(obs: dict) -> str:
    """SHA-256 over the canonical observation bytes (tamper-evidence handle)."""
    return "sha256:" + hashlib.sha256(_canonical_observation_bytes(obs)).hexdigest()


def _decode_key_material(value: str) -> bytes:
    """Decode hex or base64 key/signature material, tolerating a type prefix.

    Accepts 'ed25519:<hex>', a bare hex string, or base64. Raises ValueError
    on anything undecodable so callers can return a structured error.
    """
    import base64

    raw = (value or "").strip()
    if ":" in raw and raw.split(":", 1)[0].lower() in {"ed25519", "hex", "base64"}:
        raw = raw.split(":", 1)[1]
    raw = raw.strip()
    # Try hex first (Ed25519 keys/sigs are 32/64 bytes -> 64/128 hex chars).
    try:
        return bytes.fromhex(raw)
    except ValueError:
        pass
    try:
        return base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 - normalise to ValueError
        raise ValueError(f"could not decode key material: {exc}") from exc


# ---------------------------------------------------------------------------
# Organellar genome mini-atlas (mitochondrion / plastid)
#
# Mt and Pt are first-class chromosome identifiers in Ensembl Plants, not
# errors. These traits are politically significant for the seed-sovereignty
# audience: CMS is how hybrid seed is produced; plastid herbicide resistance
# is how Roundup-/atrazine-resistant traits spread maternally.
# ---------------------------------------------------------------------------
ORGANELLAR_TRAITS = {
    "cms": {
        "organelle": "mitochondrion",
        "chromosome": "Mt",
        "description": "Cytoplasmic male sterility — maternally inherited mitochondrial rearrangements that abort pollen. The genetic basis of most hybrid-seed production systems.",
        "natural_farming_relevance": "CMS is the mechanism by which commercial hybrids are made non-true-breeding, tying growers to seed repurchase. Understanding the loci helps heritage breeders identify and avoid (or deliberately use) CMS cytoplasms.",
        "genes": [
            {"symbol": "orf138", "function": "Ogura (radish) CMS-associated chimeric ORF; restored by the Rfo nuclear gene (PPR protein).", "characterized_in": "raphanus_sativus"},
            {"symbol": "orf256", "function": "Wheat/maize T-CMS-associated mitochondrial ORF.", "characterized_in": "zea_mays"},
            {"symbol": "T-urf13", "alias": "urf13", "function": "Maize CMS-T chimeric ORF; the cytoplasm behind the 1970 Southern corn leaf blight epidemic — a cautionary monoculture lesson.", "characterized_in": "zea_mays"},
            {"symbol": "atp6", "function": "Mitochondrial ATP synthase subunit 6; recurrent participant in CMS-associated rearrangements.", "characterized_in": "oryza_sativa"},
        ],
    },
    "plastid_herbicide_resistance": {
        "organelle": "plastid",
        "chromosome": "Pt",
        "description": "Plastid-encoded targets of herbicides; maternally inherited resistance alleles.",
        "natural_farming_relevance": "psbA point mutations confer atrazine/triazine and DCMU resistance and spread maternally through seed, not pollen — relevant to weed-management and to understanding GM-trait inheritance in seed-saving systems.",
        "genes": [
            {"symbol": "psbA", "function": "D1 protein of photosystem II; the Ser264 target site of triazine (atrazine) and urea (DCMU) herbicides. Point mutations confer resistance.", "characterized_in": "arabidopsis_thaliana"},
            {"symbol": "accD", "function": "Plastid acetyl-CoA carboxylase beta subunit; target context for graminicide (ACCase-inhibitor) resistance.", "characterized_in": "arabidopsis_thaliana"},
        ],
    },
    "plastid_photosynthesis": {
        "organelle": "plastid",
        "chromosome": "Pt",
        "description": "Core plastid-encoded photosynthetic machinery — Rubisco large subunit and photosystem reaction-centre proteins.",
        "natural_farming_relevance": "rbcL is the universal plant DNA-barcode locus and the large subunit of Rubisco; plastid photosynthesis genes anchor maternal-lineage identification of heritage seed.",
        "genes": [
            {"symbol": "rbcL", "function": "Rubisco large subunit — the carboxylase at the heart of carbon fixation; also the canonical plant barcoding marker.", "characterized_in": "arabidopsis_thaliana"},
            {"symbol": "psaA", "function": "Photosystem I P700 apoprotein A1 (plastid-encoded).", "characterized_in": "arabidopsis_thaliana"},
            {"symbol": "psaB", "function": "Photosystem I P700 apoprotein A2 (plastid-encoded).", "characterized_in": "arabidopsis_thaliana"},
            {"symbol": "atpB", "function": "Plastid ATP synthase beta subunit.", "characterized_in": "arabidopsis_thaliana"},
        ],
    },
}


# ---------------------------------------------------------------------------
# GWAS power estimation
# ---------------------------------------------------------------------------

# Approximate genome-wide common-SNP counts per species, used to set the
# Bonferroni multiple-testing burden. Conservative round numbers — the point
# is an order-of-magnitude honest estimate, not false precision. Species not
# listed fall back to a deliberately conservative low count (fewer SNPs ->
# lighter correction -> *optimistic* required-N, flagged in the response).
_SPECIES_SNP_COUNT = {
    "arabidopsis_thaliana": 12_000_000,
    "oryza_sativa": 20_000_000,
    "oryza_indica": 20_000_000,
    "zea_mays": 50_000_000,
    "triticum_aestivum": 40_000_000,
    "solanum_lycopersicum": 4_000_000,
    "vitis_vinifera": 2_000_000,
    "sorghum_bicolor": 6_000_000,
    "glycine_max": 10_000_000,
}
_DEFAULT_SNP_COUNT = 1_000_000


def _inv_norm_cdf(p: float) -> float:
    """Inverse standard-normal CDF (probit) via Acklam's rational approximation.

    Pure-Python so the server carries no scipy/numpy dependency. Accurate to
    ~1e-9 across (0,1) — far tighter than the GWAS estimate needs.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


# ---------------------------------------------------------------------------
# Network clients for the new external services (test-seam pattern)
# ---------------------------------------------------------------------------

def _grin_client() -> httpx.Client:
    """Client for the USDA GRIN-Global REST service (accession resolution)."""
    return httpx.Client(
        base_url=GRIN_BASE_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "cultivars-mcp/0.2 (Copyleft Cultivars; accession resolution)",
        },
        timeout=30,
        follow_redirects=True,
    )


def _ipfs_client() -> httpx.Client:
    """Client for the local kubo (go-ipfs) HTTP API."""
    return httpx.Client(base_url=IPFS_API_URL, timeout=30)


# ===========================================================================
# Phenotype ledger — the write path
# ===========================================================================

@mcp.tool()
def submit_phenotype_observation(
    accession_id: str,
    common_name: str,
    species: str,
    trait_category: str,
    measurement_type: str,
    measurement_value: bool | float | int | str | None = None,
    measurement_unit: str | None = None,
    measurement_protocol: str | None = None,
    trait_atlas_gene: str | None = None,
    agroecological_zone: str | None = None,
    environment: dict | None = None,
    season: str | None = None,
    submitter_pubkey: str | None = None,
    signature: str | None = None,
    license: str = LEDGER_DATA_LICENSE,
    submitted: str | None = None,
    write: bool = True,
) -> dict:
    """Submit a community phenotype observation to the open ledger.

    This is the write path that turns cultivars-mcp from a read-only query
    layer into a participatory community-science instrument. A grower who
    confirms that their Oaxacan landrace maize survived 14-day flooding is
    producing GWAS-relevant data; this tool captures it in a machine-readable,
    GWAS-aggregatable YAML record.

    The tool prepares (and, by default, writes) the observation artifact; it
    does NOT need GitHub credentials. The human submits the resulting file as
    a pull request, or it accumulates in a local/shared `ledger_dir`. Data in
    the ledger is licensed ODbL-1.0 (open-data copyleft), distinct from the
    Apache-2.0 code license — see DATA_LICENSE.md.

    Args:
        accession_id: Formal ID where known (GRIN/IRRI/USDA), else
            'community:{name}'. If informal, the response suggests running
            resolve_accession to find a formal match.
        common_name: Farmer-provided name (e.g. 'Gobol Sail', 'Hopi blue corn').
        species: Ensembl Plants species string (e.g. 'oryza_sativa').
        trait_category: Must match an atlas trait category (see
            list_trait_categories) or an organellar trait (see
            query_organellar_variants).
        measurement_type: 'binary' | 'continuous' | 'categorical'.
        measurement_value: The measured value. bool for binary, number for
            continuous, string for categorical.
        measurement_unit: Unit for continuous measurements (e.g. 'cm', 'days').
        measurement_protocol: Free-text protocol handle (e.g.
            '14_day_submergence_field').
        trait_atlas_gene: Optional canonical gene from the atlas (e.g. 'SUB1A').
        agroecological_zone: Koppen or FAO zone string.
        environment: Optional dict of structured environment fields (merged
            with agroecological_zone / season).
        season: Season tag (e.g. 'kharif_2026').
        submitter_pubkey: Optional Ed25519 public key ('ed25519:<hex>'). Sign
            the canonical_form returned here and resubmit with `signature` to
            create a verifiable, pseudonymous contribution record.
        signature: Optional detached Ed25519 signature over canonical_form.
        license: Data license (default ODbL-1.0).
        submitted: ISO date (default today, UTC).
        write: Whether to write the YAML file to the ledger (default True).

    Returns a structured response: validation result, the assembled
    observation, its content hash, the canonical form to sign, the written
    path (if any), and PR submission instructions.
    """
    errors: list[str] = []

    accession_id = (accession_id or "").strip()
    common_name = (common_name or "").strip()
    species = _normalize_species(species)
    trait_category = (trait_category or "").strip()
    measurement_type = (measurement_type or "").strip().lower()

    if not accession_id:
        errors.append("accession_id is required (use 'community:{name}' if informal)")
    if not common_name:
        errors.append("common_name is required")
    if not _valid_trait_category(trait_category):
        errors.append(
            f"trait_category {trait_category!r} is not a known atlas or organellar "
            "trait category — call list_trait_categories"
        )
    if species not in _known_species():
        errors.append(
            f"species {species!r} is not recognised — call list_plant_species"
        )
    if measurement_type not in _VALID_MEASUREMENT_TYPES:
        errors.append(
            f"measurement_type must be one of {sorted(_VALID_MEASUREMENT_TYPES)}"
        )
    else:
        if measurement_value is None:
            errors.append("measurement_value is required")
        elif measurement_type == "binary" and not isinstance(measurement_value, bool):
            errors.append("binary measurement_value must be a boolean")
        elif measurement_type == "continuous" and isinstance(measurement_value, bool):
            errors.append("continuous measurement_value must be numeric, not boolean")
        elif measurement_type == "continuous" and not isinstance(measurement_value, (int, float)):
            errors.append("continuous measurement_value must be numeric")

    if trait_atlas_gene and trait_category in TRAIT_ATLAS:
        symbols = {g.get("symbol") for g in TRAIT_ATLAS[trait_category]["genes"]}
        symbols |= {g.get("alias") for g in TRAIT_ATLAS[trait_category]["genes"]}
        if trait_atlas_gene not in symbols:
            errors.append(
                f"trait_atlas_gene {trait_atlas_gene!r} is not a canonical gene in "
                f"trait {trait_category!r} (genes: {sorted(s for s in symbols if s)})"
            )

    if errors:
        return {
            "ok": False,
            "validation": "failed",
            "errors": errors,
            "hint": "Fix the fields above and resubmit. Nothing was written.",
        }

    env: dict = dict(environment or {})
    if agroecological_zone:
        env.setdefault("agroecological_zone", agroecological_zone)
    if season:
        env.setdefault("season", season)

    submitted = (submitted or datetime.date.today().isoformat())

    observation = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "accession_id": accession_id,
        "common_name": common_name,
        "species": species,
        "trait_category": trait_category,
        "trait_atlas_gene": trait_atlas_gene,
        "measurement": {
            "type": measurement_type,
            "value": measurement_value,
            "unit": measurement_unit,
            "protocol": measurement_protocol,
        },
        "environment": env or None,
        "provenance": {
            "submitter_pubkey": submitter_pubkey,
            "signature": signature,
            "location_proof": None,
            "ipfs_cid": None,
        },
        "license": license,
        "submitted": submitted,
    }

    canonical = _canonical_observation_bytes(observation).decode("utf-8")
    content_hash = _content_hash(observation)

    informal = accession_id.lower().startswith("community:") or ":" not in accession_id
    accession_suggestion = None
    if informal:
        accession_suggestion = (
            f"'{accession_id}' looks informal. Run resolve_accession(query="
            f"'{common_name}') to find a formal GRIN/USDA accession ID and "
            "improve downstream GWAS aggregation."
        )

    response: dict = {
        "ok": True,
        "validation": "passed",
        "observation": observation,
        "content_hash": content_hash,
        "canonical_form": canonical,
        "accession_suggestion": accession_suggestion,
        "signing_instructions": (
            "To create a verifiable contribution record, sign `canonical_form` "
            "(UTF-8 bytes) with your Ed25519 secret key and resubmit with "
            "submitter_pubkey='ed25519:<hex>' and signature='<hex>'. Verify any "
            "record later with verify_observation_integrity. Signing is optional "
            "but encouraged — it builds a pseudonymous scientific CV tied to a "
            "keypair, not a financial instrument."
        ),
        "license_note": (
            f"Ledger data is licensed {license} (open-data copyleft). See "
            "DATA_LICENSE.md. This differs from the Apache-2.0 code license."
        ),
    }

    if not write:
        response["written"] = False
        response["note"] = "write=False — artifact prepared but not persisted."
        return response

    if _yaml is None:
        response["written"] = False
        response["warning"] = (
            "PyYAML is not installed, so the artifact could not be written. "
            "Install it (pip install pyyaml) or copy `observation` out manually."
        )
        return response

    ledger = _ledger_dir()
    target_dir = ledger / _path_safe(species) / _path_safe(accession_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_path_safe(trait_category)}_{_path_safe(submitted)}.yaml"
    path = target_dir / filename

    header = (
        f"# Cultivars community phenotype observation\n"
        f"# schema {LEDGER_SCHEMA_VERSION} — licensed {license} (see DATA_LICENSE.md)\n"
        f"# content_hash: {content_hash}\n"
    )
    path.write_text(header + _yaml.safe_dump(observation, sort_keys=False, allow_unicode=True))

    response["written"] = True
    response["path"] = str(path)
    response["pr_instructions"] = (
        f"Artifact written to {path}. To contribute it to the commons: commit "
        "the file under phenotypes/ and open a pull request against "
        "copyleftcultivars/cultivars-mcp. The maintainers aggregate merged "
        "observations for community GWAS (see estimate_gwas_power)."
    )
    return response


@mcp.tool()
def query_community_phenotypes(
    trait_category: str,
    species: str | None = None,
    min_observations: int = 1,
) -> dict:
    """Aggregate community phenotype observations from the ledger.

    Reads the YAML observation files written by submit_phenotype_observation
    (under `ledger_dir`, default ./phenotypes) and summarises them for a
    trait — observation count, measurement distribution, and the accessions
    carrying observations. Powers estimate_gwas_power.

    Args:
        trait_category: Atlas or organellar trait category to aggregate.
        species: Optional Ensembl species filter.
        min_observations: Minimum count to consider the result actionable
            (purely informational — the count is always returned).
    """
    trait_category = (trait_category or "").strip()
    species_filter = _normalize_species(species) if species else None

    if _yaml is None:
        return {
            "ok": False,
            "error": "PyYAML is not installed; cannot read the ledger.",
            "hint": "pip install pyyaml",
        }

    ledger = _ledger_dir()
    if not ledger.exists():
        return {
            "ok": True,
            "trait_category": trait_category,
            "species": species_filter,
            "observation_count": 0,
            "ledger_dir": str(ledger),
            "note": "No ledger directory yet — no observations submitted.",
        }

    observations: list[dict] = []
    parse_errors: list[str] = []
    for path in ledger.rglob("*.yaml"):
        try:
            doc = _yaml.safe_load(path.read_text())
        except Exception as exc:  # noqa: BLE001 - keep one bad file from killing the query
            parse_errors.append(f"{path.name}: {exc}")
            continue
        if not isinstance(doc, dict):
            continue
        if doc.get("trait_category") != trait_category:
            continue
        if species_filter and doc.get("species") != species_filter:
            continue
        observations.append(doc)

    # Build the measurement distribution.
    value_counts: dict[str, int] = {}
    continuous_values: list[float] = []
    accessions: dict[str, int] = {}
    signed = 0
    for obs in observations:
        m = obs.get("measurement") or {}
        mtype, val = m.get("type"), m.get("value")
        if mtype == "continuous" and isinstance(val, (int, float)) and not isinstance(val, bool):
            continuous_values.append(float(val))
        else:
            value_counts[str(val)] = value_counts.get(str(val), 0) + 1
        acc = obs.get("accession_id") or "unknown"
        accessions[acc] = accessions.get(acc, 0) + 1
        prov = obs.get("provenance") or {}
        if prov.get("signature") and prov.get("submitter_pubkey"):
            signed += 1

    distribution: dict = {"categorical_or_binary": value_counts}
    if continuous_values:
        distribution["continuous"] = {
            "n": len(continuous_values),
            "min": min(continuous_values),
            "max": max(continuous_values),
            "mean": round(sum(continuous_values) / len(continuous_values), 4),
        }

    return {
        "ok": True,
        "trait_category": trait_category,
        "species": species_filter,
        "observation_count": len(observations),
        "meets_min_observations": len(observations) >= min_observations,
        "distinct_accessions": len(accessions),
        "accessions": sorted(accessions),
        "signed_observations": signed,
        "measurement_distribution": distribution,
        "ledger_dir": str(ledger),
        "parse_errors": parse_errors or None,
        "next_step": (
            "Feed observation_count into estimate_gwas_power(trait_category, "
            "species) to see how close the community is to detecting a locus."
        ),
    }


@mcp.tool()
def verify_observation_integrity(
    yaml_path_or_content: str,
    pubkey: str | None = None,
) -> dict:
    """Verify the Ed25519 signature on a phenotype observation.

    Confirms that an observation was signed by the holder of a given keypair
    and has not been altered since signing — a verifiable, pseudonymous
    contribution record (a scientific CV tied to a keypair, not money).

    Args:
        yaml_path_or_content: Either a path to a ledger YAML file or the raw
            YAML content of an observation.
        pubkey: Ed25519 public key to verify against ('ed25519:<hex>' or bare
            hex/base64). If omitted, uses the key embedded in the observation's
            provenance.submitter_pubkey.

    Returns {verified, submitter_pubkey, signed_at, canonical_hash, ...}.
    """
    if _yaml is None:
        return {"verified": False, "error": "PyYAML is not installed; cannot parse YAML."}

    raw = yaml_path_or_content or ""
    p = pathlib.Path(raw)
    try:
        if len(raw) < 4096 and p.exists():
            raw = p.read_text()
    except OSError:
        pass  # treat as inline content

    try:
        obs = _yaml.safe_load(raw)
    except Exception as exc:  # noqa: BLE001
        return {"verified": False, "error": f"could not parse YAML: {exc}"}
    if not isinstance(obs, dict):
        return {"verified": False, "error": "parsed content is not a mapping/observation"}

    prov = obs.get("provenance") or {}
    sig = prov.get("signature")
    key = pubkey or prov.get("submitter_pubkey")
    if not sig:
        return {
            "verified": False,
            "error": "observation carries no signature",
            "canonical_hash": _content_hash(obs),
            "note": "Unsigned observations are still valid data — they just lack attribution proof.",
        }
    if not key:
        return {"verified": False, "error": "no public key supplied or embedded"}

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return {
            "verified": False,
            "error": "the 'cryptography' package is required for signature verification",
            "hint": "pip install cryptography",
        }

    try:
        pub_bytes = _decode_key_material(key)
        sig_bytes = _decode_key_material(sig)
    except ValueError as exc:
        return {"verified": False, "error": str(exc)}

    message = _canonical_observation_bytes(obs)
    try:
        Ed25519PublicKey.from_public_bytes(pub_bytes).verify(sig_bytes, message)
    except InvalidSignature:
        return {
            "verified": False,
            "submitter_pubkey": key,
            "canonical_hash": _content_hash(obs),
            "error": "signature does not match — observation altered or wrong key",
        }
    except Exception as exc:  # noqa: BLE001 - malformed key length etc.
        return {"verified": False, "error": f"verification failed: {exc}"}

    return {
        "verified": True,
        "submitter_pubkey": key,
        "signed_at": obs.get("submitted"),
        "canonical_hash": _content_hash(obs),
        "accession_id": obs.get("accession_id"),
        "trait_category": obs.get("trait_category"),
    }


@mcp.tool()
def pin_observation_to_ipfs(yaml_path: str, vcf_path: str | None = None) -> dict:
    """Pin an observation (and optionally a VCF) to IPFS via the kubo HTTP API.

    Content-addressed storage makes an observation tamper-evident and
    location-independent: the returned CID is a permanent, decentralised
    identifier (a replacement for the centralised S3 URL pattern used by
    Kannapedia VCFs). On success, the CID is written back into the YAML's
    provenance.ipfs_cid field.

    Requires a running kubo node (default http://127.0.0.1:5001, override with
    CULTIVARS_IPFS_API). If IPFS is unreachable, returns a structured fallback
    with setup instructions rather than raising.

    Args:
        yaml_path: Path to the observation YAML to pin.
        vcf_path: Optional path to an associated VCF to pin alongside it.
    """
    obs_path = pathlib.Path(yaml_path)
    if not obs_path.exists():
        return {"ok": False, "error": f"file not found: {yaml_path}"}

    files_to_pin = [obs_path]
    if vcf_path:
        vcf = pathlib.Path(vcf_path)
        if not vcf.exists():
            return {"ok": False, "error": f"vcf file not found: {vcf_path}"}
        files_to_pin.append(vcf)

    pinned: dict[str, str] = {}
    try:
        with _ipfs_client() as client:
            for fp in files_to_pin:
                resp = client.post(
                    "/api/v0/add",
                    params={"pin": "true", "cid-version": "1"},
                    files={"file": (fp.name, fp.read_bytes())},
                )
                resp.raise_for_status()
                # kubo may stream multiple JSON objects; take the last complete one.
                last = [line for line in resp.text.strip().splitlines() if line.strip()][-1]
                pinned[fp.name] = json.loads(last)["Hash"]
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TransportError):
        return {
            "ok": False,
            "ipfs_available": False,
            "fallback": True,
            "api_url": IPFS_API_URL,
            "instructions": (
                "No kubo node reachable. Install IPFS (https://docs.ipfs.tech/install/), "
                "run `ipfs daemon`, or set CULTIVARS_IPFS_API to a reachable gateway, "
                "then retry. The observation remains valid without a CID."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ipfs_available": True, "error": f"IPFS add failed: {exc}"}

    yaml_cid = pinned.get(obs_path.name)
    wrote_back = False
    if yaml_cid and _yaml is not None:
        try:
            doc = _yaml.safe_load(obs_path.read_text())
            if isinstance(doc, dict):
                doc.setdefault("provenance", {})
                doc["provenance"]["ipfs_cid"] = yaml_cid
                obs_path.write_text(_yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
                wrote_back = True
        except Exception:  # noqa: BLE001 - write-back is best-effort
            wrote_back = False

    return {
        "ok": True,
        "ipfs_available": True,
        "cids": pinned,
        "observation_cid": yaml_cid,
        "vcf_cid": pinned.get(pathlib.Path(vcf_path).name) if vcf_path else None,
        "wrote_cid_to_yaml": wrote_back,
        "note": "The observation_cid is now the canonical, tamper-evident identifier.",
    }


# ===========================================================================
# GWAS power estimator — individual observation -> collective significance
# ===========================================================================

@mcp.tool()
def estimate_gwas_power(
    trait_category: str,
    species: str,
    n_observations: int | None = None,
    target_gene: str | None = None,
    maf: float = 0.25,
) -> dict:
    """Estimate how many observations a community GWAS needs to detect a locus.

    Closes the loop between an individual grower's observation and collective
    scientific significance: "can my village's 12 rice varieties help detect
    the SUB1A locus?" gets a concrete answer — and a recruitment target.

    Uses a standard common-variant additive-model power calculation with a
    Bonferroni-corrected significance threshold over the species' approximate
    genome-wide SNP count. The required sample size for power (1 - beta) to
    detect a locus explaining proportion h2 of phenotypic variance is:

        required_n  ≈  (z_{alpha/2} + z_{beta})^2 / (2 * MAF * (1 - MAF) * effect^2)
                    =  (z_{alpha/2} + z_{beta})^2 / h2

    where, for the standardised additive model, h2 = 2 * MAF * (1 - MAF) * effect^2,
    alpha = 0.05 / (genome-wide SNP count), and beta = 0.20 (80% power).

    Args:
        trait_category: Atlas or organellar trait category.
        species: Ensembl species string (sets the SNP count / multiple-testing burden).
        n_observations: Current sample size. If omitted, pulled live from the
            community ledger via query_community_phenotypes.
        target_gene: Optional gene of interest (annotation only).
        maf: Assumed minor-allele frequency for the formula (default 0.25).
    """
    species = _normalize_species(species)

    if not _valid_trait_category(trait_category):
        return {
            "ok": False,
            "error": f"trait_category {trait_category!r} not recognised",
            "hint": "call list_trait_categories",
        }
    if not 0.0 < maf <= 0.5:
        return {"ok": False, "error": "maf must be in (0, 0.5]"}

    current_n = n_observations
    pulled_from_ledger = False
    if current_n is None:
        ledger_result = query_community_phenotypes(trait_category, species)
        current_n = int(ledger_result.get("observation_count", 0)) if ledger_result.get("ok") else 0
        pulled_from_ledger = True

    snp_count = _SPECIES_SNP_COUNT.get(species, _DEFAULT_SNP_COUNT)
    conservative_snp_estimate = species not in _SPECIES_SNP_COUNT
    alpha = 0.05 / snp_count
    z_alpha2 = _inv_norm_cdf(1 - alpha / 2)
    z_beta = _inv_norm_cdf(0.80)  # ~0.8416, for 80% power

    def required_n(h2: float) -> int:
        return math.ceil((z_alpha2 + z_beta) ** 2 / h2)

    large_h2, medium_h2 = 0.10, 0.05
    n_large = required_n(large_h2)
    n_medium = required_n(medium_h2)

    def gap_message(needed: int, label: str) -> str:
        remaining = max(0, needed - current_n)
        if remaining == 0:
            return f"The ledger already has enough observations ({current_n}) for 80% power to detect a {label} locus."
        return (
            f"For a {label} locus you need ~{needed} observations. The community "
            f"ledger currently has {current_n} — submit yours and recruit "
            f"{remaining} more."
        )

    return {
        "ok": True,
        "trait_category": trait_category,
        "species": species,
        "species_quality": _species_quality(species),
        "target_gene": target_gene,
        "current_observations": current_n,
        "current_observations_source": "community_ledger" if pulled_from_ledger else "caller-supplied",
        "assumptions": {
            "power": 0.80,
            "alpha_per_test": 0.05,
            "bonferroni_snp_count": snp_count,
            "bonferroni_alpha": alpha,
            "minor_allele_frequency": maf,
            "z_alpha_over_2": round(z_alpha2, 4),
            "z_beta": round(z_beta, 4),
            "model": "common-variant additive",
            "conservative_snp_estimate": conservative_snp_estimate,
        },
        "required_observations": {
            "large_effect_locus": {"variance_explained": large_h2, "n": n_large},
            "medium_effect_locus": {"variance_explained": medium_h2, "n": n_medium},
        },
        "formula": "required_n ≈ (z_{alpha/2} + z_{beta})^2 / h2,  h2 = 2·MAF·(1-MAF)·effect^2,  alpha = 0.05 / SNP_count",
        "interpretation": {
            "large_effect": gap_message(n_large, "large-effect (SUB1A-scale, ~10% variance)"),
            "medium_effect": gap_message(n_medium, "medium-effect (~5% variance)"),
        },
        "caveats": (
            "Order-of-magnitude guidance, not a substitute for formal power "
            "analysis. Assumes unrelated individuals, a single common causal "
            "variant, balanced binary phenotype, and no population structure. "
            "Real plant GWAS must correct for kinship and structure (mixed "
            "models), which raises the required N."
            + (" SNP count is a conservative default for this species — treat the required N as optimistic." if conservative_snp_estimate else "")
        ),
    }


# ===========================================================================
# GRIN accession resolver — folk taxonomy -> formal genomics
# ===========================================================================

# Map common GRIN genus/species names to Ensembl Plants species strings so a
# resolved accession can flow straight into the genomics tools.
_GRIN_TO_ENSEMBL = {
    "oryza sativa": "oryza_sativa",
    "zea mays": "zea_mays",
    "triticum aestivum": "triticum_aestivum",
    "hordeum vulgare": "hordeum_vulgare",
    "sorghum bicolor": "sorghum_bicolor",
    "glycine max": "glycine_max",
    "solanum lycopersicum": "solanum_lycopersicum",
    "vigna unguiculata": "vigna_unguiculata",
    "cajanus cajan": "cajanus_cajan",
    "eleusine coracana": "eleusine_coracana",
    "manihot esculenta": "manihot_esculenta",
}


def _grin_species_to_ensembl(taxon: str | None) -> str | None:
    if not taxon:
        return None
    key = taxon.strip().lower()
    if key in _GRIN_TO_ENSEMBL:
        return _GRIN_TO_ENSEMBL[key]
    # Try just the first two binomial tokens.
    parts = key.split()
    if len(parts) >= 2:
        return _GRIN_TO_ENSEMBL.get(f"{parts[0]} {parts[1]}")
    return None


@mcp.tool()
def resolve_accession(
    query: str,
    crop_type: str | None = None,
    region: str | None = None,
    limit: int = 10,
) -> dict:
    """Resolve a farmer's seed name to a formal GRIN-Global accession.

    Bridges folk taxonomy ("my grandmother's Hopi blue corn") to the formal
    accession systems that GWAS and genomics need. Queries the USDA
    GRIN-Global REST service (600,000+ accessions with common names, origins,
    and trait observations) and maps the result back to an Ensembl Plants
    species string so it can feed lookup_gene / find_trait_genes /
    submit_phenotype_observation.

    Args:
        query: Common or scientific seed name (e.g. 'Hopi blue corn', 'Gobol Sail').
        crop_type: Optional crop hint to narrow results (e.g. 'maize').
        region: Optional geographic origin hint.
        limit: Maximum matches to return (default 10, max 50).

    Returns candidate accessions with formal ID, species, origin, and the
    Ensembl species equivalent. GRIN's API shape varies; parsing is defensive
    and the response flags when no structured match was found.
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "query is required"}
    limit = min(max(1, limit), 50)

    params = {"q": q, "limit": limit}
    if crop_type:
        params["crop"] = crop_type
    if region:
        params["origin"] = region

    try:
        with _grin_client() as client:
            resp = _get_with_retry(client, "/search/accessions", params=params)
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "error": f"GRIN-Global request failed: {exc}",
            "fallback": "Search manually at https://npgsweb.ars-grin.gov/gringlobal/search",
            "query": q,
        }

    if resp.status_code == 404:
        return {"ok": True, "query": q, "match_count": 0, "matches": [],
                "note": "GRIN returned no matches for this query."}
    if resp.status_code >= 400:
        return {
            "ok": False,
            "error": f"GRIN-Global returned HTTP {resp.status_code}",
            "detail": resp.text[:300],
            "fallback": "Search manually at https://npgsweb.ars-grin.gov/gringlobal/search",
        }

    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "GRIN-Global response was not JSON",
                "detail": resp.text[:300]}

    # GRIN responses vary; accept a list, or a dict wrapping a list under
    # common keys. Parse defensively into a normalised shape.
    records: list = []
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("data", "results", "accessions", "items"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break

    def _field(rec: dict, *names):
        for n in names:
            if rec.get(n) not in (None, ""):
                return rec[n]
        return None

    matches = []
    for rec in records[:limit]:
        if not isinstance(rec, dict):
            continue
        taxon = _field(rec, "taxon", "taxonomy", "species", "scientificName")
        matches.append({
            "accession_id": _field(rec, "accessionId", "accession_id", "accenumb", "id"),
            "common_name": _field(rec, "commonName", "common_name", "name"),
            "taxon": taxon,
            "ensembl_species": _grin_species_to_ensembl(taxon),
            "origin": _field(rec, "origin", "originCountry", "country", "geography"),
            "grin_observations": _field(rec, "observations", "traits"),
        })

    return {
        "ok": True,
        "query": q,
        "match_count": len(matches),
        "matches": matches,
        "note": (
            "GRIN-Global is the USDA open accession system. Pass an "
            "ensembl_species into lookup_gene/find_trait_genes, or the "
            "accession_id into submit_phenotype_observation. The GRIN REST "
            "schema varies by deployment; if match_count is 0 but you expect "
            "hits, confirm at https://npgsweb.ars-grin.gov/gringlobal/search"
        ),
    }


# ===========================================================================
# Organellar genome tool (Mt / Pt)
# ===========================================================================

@mcp.tool()
def query_organellar_variants(
    species: str,
    organelle: str = "plastid",
    region: str | None = None,
    trait: str | None = None,
) -> dict:
    """Query organellar (mitochondrial / plastid) genome variants and traits.

    Mt (mitochondrion) and Pt (plastid) are first-class chromosomes in Ensembl
    Plants — querying them is valid, not an error. This tool wraps
    search_variants_in_region against the organellar chromosome and layers a
    curated organellar trait atlas (CMS, plastid herbicide resistance, plastid
    photosynthesis) on top — traits that matter for seed sovereignty (hybrid
    seed production, maternal inheritance of GM/herbicide-resistance traits).

    Args:
        species: Ensembl species string.
        organelle: 'plastid' (Pt) or 'mitochondrion' (Mt). Aliases accepted:
            'chloroplast'->plastid, 'mt'/'mito'->mitochondrion, 'pt'/'cp'->plastid.
        region: Optional 'start-end' coordinate range on the organellar
            chromosome. If omitted, only trait context is returned (no variant scan).
        trait: Optional organellar trait key (see ORGANELLAR_TRAITS:
            'cms', 'plastid_herbicide_resistance', 'plastid_photosynthesis').
    """
    species = _normalize_species(species)
    org = (organelle or "").strip().lower()
    alias = {
        "plastid": "plastid", "pt": "plastid", "cp": "plastid", "chloroplast": "plastid",
        "mitochondrion": "mitochondrion", "mt": "mitochondrion", "mito": "mitochondrion",
        "mitochondria": "mitochondrion",
    }
    if org not in alias:
        return {
            "ok": False,
            "error": f"organelle {organelle!r} not understood",
            "valid": ["plastid", "mitochondrion"],
        }
    org = alias[org]
    chromosome = "Pt" if org == "plastid" else "Mt"

    result: dict = {
        "ok": True,
        "species": species,
        "organelle": org,
        "chromosome": chromosome,
        "note": (
            f"'{chromosome}' is the Ensembl Plants chromosome identifier for the "
            f"{org} genome — a valid query target, not an error. Organellar "
            "genomes are maternally inherited."
        ),
    }

    if trait:
        trait_key = trait.strip().lower().replace(" ", "_").replace("-", "_")
        entry = ORGANELLAR_TRAITS.get(trait_key)
        if not entry:
            result["trait_error"] = (
                f"trait {trait!r} not in the organellar atlas"
            )
            result["available_organellar_traits"] = sorted(ORGANELLAR_TRAITS)
        else:
            if entry["organelle"] != org:
                result["trait_warning"] = (
                    f"trait {trait_key!r} is a {entry['organelle']} trait "
                    f"(chromosome {entry['chromosome']}), but you queried {org}."
                )
            result["trait_context"] = {
                "trait": trait_key,
                "description": entry["description"],
                "natural_farming_relevance": entry["natural_farming_relevance"],
                "genes": entry["genes"],
            }

    if region:
        r = region.strip()
        # Accept either 'start-end' or a full 'chrom:start-end'.
        full_region = r if ":" in r else f"{chromosome}:{r}"
        variants = search_variants_in_region(region=full_region, species=species)
        result["variant_scan"] = variants
    else:
        result["variant_scan_hint"] = (
            f"Pass region='start-end' to scan {chromosome} for known variants, "
            f"e.g. query_organellar_variants(species='{species}', "
            f"organelle='{org}', region='1-5000')."
        )

    return result


# ===========================================================================
# Offline bridge — online genomics -> TinyLLamaFarmer field handoff
# ===========================================================================

@mcp.tool()
def export_offline_snapshot(
    trait_category: str,
    species: str,
    include_orthologs: bool = True,
    max_genes: int | None = None,
) -> dict:
    """Package a trait's genomics into a self-contained offline snapshot.

    Bridges the online MCP to the offline-first TinyLLamaFarmer: a grower who
    can't stay connected in the field gets a portable JSON blob with the trait
    atlas entry, the species coverage grade, and (optionally) the resolved
    orthologs in their crop — everything needed to reason about the trait
    off-grid. This is the online->offline direction; the reverse (field
    observation -> ledger) is submit_phenotype_observation.

    Args:
        trait_category: Atlas trait category to package.
        species: Target Ensembl species string.
        include_orthologs: If True, resolve canonical genes -> target-species
            orthologs (one network round-trip via translate_trait_to_species).
            Set False for a fully offline, atlas-only snapshot.
        max_genes: Optional cap on genes translated (passed to translation).

    Returns the snapshot file path and a summary of what was included.
    """
    species = _normalize_species(species)
    trait_key = (trait_category or "").strip().lower().replace(" ", "_").replace("-", "_")
    if trait_key not in TRAIT_ATLAS:
        return {
            "ok": False,
            "error": f"trait_category {trait_category!r} not in the atlas",
            "available_traits": sorted(TRAIT_ATLAS),
        }

    atlas_entry = TRAIT_ATLAS[trait_key]
    snapshot: dict = {
        "snapshot_schema": "1.0",
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "cultivars-mcp",
        "trait_category": trait_key,
        "target_species": species,
        "species_quality": _species_quality(species),
        "atlas": {
            "description": atlas_entry["description"],
            "natural_farming_relevance": atlas_entry["natural_farming_relevance"],
            "genes": atlas_entry["genes"],
        },
        "orthologs_included": False,
        "consumer": "TinyLLamaFarmer context injection",
    }

    if include_orthologs:
        translation = translate_trait_to_species(
            trait=trait_key, target_species=species, max_genes=max_genes
        )
        # translate returns a fallback/error dict for unsupported species; keep
        # whatever it returned so the snapshot honestly records the gap.
        snapshot["orthologs"] = translation
        snapshot["orthologs_included"] = "error" not in translation and "available_in_ensembl_plants" not in translation

    snap_dir = _snapshots_dir()
    snap_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_path_safe(trait_key)}_{_path_safe(species)}.json"
    path = snap_dir / filename
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    return {
        "ok": True,
        "path": str(path),
        "trait_category": trait_key,
        "target_species": species,
        "gene_count": len(atlas_entry["genes"]),
        "orthologs_included": snapshot["orthologs_included"],
        "snapshots_dir": str(snap_dir),
        "note": (
            "Self-contained JSON for offline use. Transfer to a field device "
            "running TinyLLamaFarmer. Online->offline is one-directional; bring "
            "field observations back with submit_phenotype_observation."
        ),
    }


# ===========================================================================
# Orphan crops contribution pipeline
# ===========================================================================

@mcp.tool()
def list_orphan_crop_requests() -> dict:
    """List requested orphan-crop trait entries (the contribution 'bounty' list).

    Orphan crops — teff, fonio, cowpea, pigeon pea, finger millet, amaranth —
    feed resource-limited farmers but are systematically underrepresented in
    model-system-funded genomics. This returns the WANTED_TRAITS.yaml bounty
    list and invites contributors to claim an entry via a PR.
    """
    path = _data_dir() / "WANTED_TRAITS.yaml"
    if not path.exists():
        return {
            "ok": True,
            "requests": [],
            "note": "No WANTED_TRAITS.yaml found — no open orphan-crop requests.",
        }
    if _yaml is None:
        return {
            "ok": False,
            "error": "PyYAML is not installed; cannot read WANTED_TRAITS.yaml.",
            "hint": "pip install pyyaml",
        }
    try:
        doc = _yaml.safe_load(path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"could not parse WANTED_TRAITS.yaml: {exc}"}

    requests = doc.get("wanted_traits", []) if isinstance(doc, dict) else []
    return {
        "ok": True,
        "request_count": len(requests),
        "requests": requests,
        "how_to_contribute": (
            "Claim a trait by opening a PR that adds it to TRAIT_ATLAS in "
            "server.py with at least GWAS-mapped evidence and a primary_ref. "
            "See CONTRIBUTING.md '# ORPHAN CROPS BOUNTY'."
        ),
        "source": str(path),
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()
