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
        "crop?' — one call replaces ~7 sequential calls.\n\n"
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
            {"symbol": "DREB1A", "alias": "CBF3", "characterized_in": "arabidopsis_thaliana", "function": "Master TF activating the cold/drought response regulon; the canonical entry point for drought engineering."},
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
            {"symbol": "SOS1", "characterized_in": "arabidopsis_thaliana", "function": "Plasma-membrane Na+/H+ antiporter; root-tip sodium extrusion."},
            {"symbol": "SOS2", "alias": "CIPK24", "characterized_in": "arabidopsis_thaliana", "function": "Kinase activating SOS1 under salt; signal-relay step."},
            {"symbol": "SOS3", "alias": "CBL4", "characterized_in": "arabidopsis_thaliana", "function": "Ca2+ sensor that perceives salt-induced cytosolic Ca2+ spike."},
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
            {"symbol": "SUB1A", "ensembl_id": "Os09g0286600", "characterized_in": "oryza_sativa", "function": "ERF TF on chromosome 9; suppresses elongation under submergence (quiescence strategy) — basis of Swarna-Sub1 and similar flood-tolerant landrace introgressions."},
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
            {"symbol": "NRT1.1B", "alias": "OsNPF6.5", "ensembl_id": "Os10g0554200", "characterized_in": "oryza_sativa", "function": "Indica-allele variant underlies superior N-use efficiency in indica vs. japonica rice — landrace breeding target."},
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
            {"symbol": "PSTOL1", "ensembl_id": "Os12g0552900", "characterized_in": "oryza_sativa", "function": "Phosphorus-Starvation Tolerance 1 — protein kinase; the Kasalath landrace allele dramatically improves rice P uptake on low-P soils. A canonical public-sector breeding success (Gamuyao et al. 2012)."},
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
            {"symbol": "SD1", "alias": "C20ox2 / OsGA20ox2", "ensembl_id": "Os01g0883800", "characterized_in": "oryza_sativa", "function": "GA20 oxidase — IR8 'miracle rice' semi-dwarf allele underlying the rice Green Revolution. Ensembl display name is C20ox2."},
            {"symbol": "Rht-B1", "characterized_in": "triticum_aestivum", "function": "Wheat DELLA — gain-of-function alleles cause Norin-10 semi-dwarfing."},
            {"symbol": "D8", "ensembl_id": "Zm00001eb019200", "characterized_in": "zea_mays", "function": "Maize DELLA; dwarfing allele used in some hybrid backgrounds."},
        ],
    },
    "tiller_branching": {
        "description": "Strigolactone signaling and TB1-family TFs governing shoot branching / tillering architecture.",
        "natural_farming_relevance": "Tiller number is a primary yield-architecture lever in cereals; landrace selection often shifts this trait toward the local growing system.",
        "genes": [
            {"symbol": "TB1", "alias": "tb1 / teosinte branched 1", "ensembl_id": "Zm00001eb287100", "characterized_in": "zea_mays", "function": "TCP-domain TF — single locus underlying the most dramatic morphological difference between maize and teosinte (suppressed tillering). Stable ID is from B73 v5 NAM assembly."},
            {"symbol": "MAX2", "characterized_in": "arabidopsis_thaliana", "function": "F-box strigolactone-signaling component; loss-of-function = bushy shoots."},
            {"symbol": "D14", "characterized_in": "oryza_sativa", "function": "Strigolactone receptor in rice."},
            {"symbol": "MOC1", "characterized_in": "oryza_sativa", "function": "GRAS TF promoting tiller bud outgrowth."},
        ],
    },
    "aluminum_tolerance": {
        "description": "Root organic-acid efflux (malate / citrate) chelating Al3+ in acidic soils, and the STOP1 transcriptional regulator above it.",
        "natural_farming_relevance": "Al toxicity is THE major constraint on crop yield on acidic tropical soils — the soils where many smallholder farmers work and where heritage landraces have been selected for tolerance over generations.",
        "genes": [
            {"symbol": "ALMT1", "characterized_in": "triticum_aestivum", "function": "Root-tip malate efflux transporter — first cloned Al-tolerance gene; classical wheat tolerance allele."},
            {"symbol": "MATE1", "alias": "AltSB / SbMATE", "characterized_in": "sorghum_bicolor", "function": "Root citrate efflux; the major sorghum Al-tolerance gene (Magalhães et al. 2007).", "note": "Literature handle — sorghum SbMATE is at locus Sb03g043890 / SORBI_3003G432200 depending on assembly; not directly resolvable by symbol."},
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
            {"symbol": "BADH2", "alias": "fgr / Fragrant / Os2AP", "ensembl_id": "Os08g0424500", "characterized_in": "oryza_sativa", "function": "Betaine aldehyde dehydrogenase 2; loss-of-function in basmati and jasmine landraces causes 2-acetyl-1-pyrroline accumulation (the popcorn-like fragrance)."},
            {"symbol": "GBSSII", "characterized_in": "oryza_sativa", "function": "Soluble starch synthase; controls intermediate amylose levels.", "note": "Literature handle — GBSSII is the soluble paralog of Wx/GBSSI; not directly resolvable by symbol."},
            {"symbol": "GLU-A1", "characterized_in": "triticum_aestivum", "function": "Glutenin subunit — major bread-making quality determinant in wheat.", "note": "Literature handle — high-molecular-weight glutenin loci on wheat 1A; not directly resolvable by symbol."},
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
    """GET wrapper that honors Ensembl's Retry-After on 429/503.

    On retryable status: read Retry-After (seconds or HTTP-date — Ensembl
    sends seconds), cap at 30s, sleep, retry. After _MAX_RETRIES, returns
    the last response without raising — callers continue with their normal
    status-code handling.
    """
    for attempt in range(_MAX_RETRIES + 1):
        resp = client.get(path, **kwargs)
        if resp.status_code not in _RETRY_STATUS or attempt == _MAX_RETRIES:
            return resp
        retry_after = resp.headers.get("Retry-After")
        try:
            wait = float(retry_after) if retry_after else _BASE_BACKOFF_SECONDS * (2 ** attempt)
        except ValueError:
            wait = _BASE_BACKOFF_SECONDS * (2 ** attempt)
        wait = min(wait, 30.0)
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

    return {
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
        resp = _get_with_retry(client, f"/variation/{species}/{vid}")
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

    result = {
        "trait": matched_key,
        "description": entry["description"],
        "natural_farming_relevance": entry["natural_farming_relevance"],
        "gene_count": len(entry["genes"]),
        "genes": entry["genes"],
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


def main():
    mcp.run()


if __name__ == "__main__":
    main()
