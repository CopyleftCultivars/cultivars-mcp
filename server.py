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
        "species each was characterized in. Pair with get_orthologs to "
        "translate to the user's actual crop.\n\n"
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
            {"symbol": "SnRK2.6", "alias": "OST1", "characterized_in": "arabidopsis_thaliana", "function": "ABA-activated kinase, central to stomatal closure under water deficit."},
            {"symbol": "RD29A", "alias": "COR78", "characterized_in": "arabidopsis_thaliana", "function": "Dehydration-responsive marker gene; classical DREB1A target."},
            {"symbol": "HVA1", "characterized_in": "hordeum_vulgare", "function": "Group 3 LEA protein; barley drought-tolerance marker, transgene-validated in rice and wheat."},
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
            {"symbol": "OsHKT1;5", "characterized_in": "oryza_sativa", "function": "Rice ortholog of HKT1; Saltol QTL on chromosome 1 in salt-tolerant Pokkali landrace."},
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
            {"symbol": "SUB1A", "characterized_in": "oryza_sativa", "function": "ERF TF on chromosome 9; suppresses elongation under submergence (quiescence strategy) — basis of Swarna-Sub1 and similar flood-tolerant landrace introgressions."},
            {"symbol": "SK1", "characterized_in": "oryza_sativa", "function": "ERF TF in deepwater rice; promotes internode elongation (escape strategy)."},
            {"symbol": "SK2", "characterized_in": "oryza_sativa", "function": "Paralog of SK1; same elongation-promoting role under submergence."},
        ],
    },
    "nitrogen_use_efficiency": {
        "description": "Nitrate / ammonium transport and assimilation — uptake, root-to-shoot translocation, and reduction to glutamine.",
        "natural_farming_relevance": "Central to KNF / natural-farming nutrient cycling without synthetic fertilizer; high-NUE varieties extract more from the same biologically-managed soil.",
        "genes": [
            {"symbol": "NRT1.1", "alias": "NPF6.3, CHL1", "characterized_in": "arabidopsis_thaliana", "function": "Dual-affinity nitrate transceptor; also signals nitrate status."},
            {"symbol": "NRT2.1", "characterized_in": "arabidopsis_thaliana", "function": "High-affinity nitrate transporter; dominant under low-N conditions."},
            {"symbol": "NRT1.1B", "alias": "OsNPF6.5", "characterized_in": "oryza_sativa", "function": "Indica-allele variant underlies superior N-use efficiency in indica vs. japonica rice — landrace breeding target."},
            {"symbol": "AMT1.1", "characterized_in": "arabidopsis_thaliana", "function": "High-affinity ammonium transporter; dominant N source under acidic-soil / paddy conditions."},
            {"symbol": "GS1", "characterized_in": "arabidopsis_thaliana", "function": "Cytosolic glutamine synthetase; assimilates NH4+ into glutamine."},
        ],
    },
    "phosphorus_uptake": {
        "description": "Inorganic phosphate (Pi) uptake transporters and the systemic Pi-starvation response.",
        "natural_farming_relevance": "Phosphorus is the limiting nutrient on weathered tropical soils common to smallholder agriculture; high-P-efficiency varieties + mycorrhizal symbiosis are the natural-farming answer to fertilizer P.",
        "genes": [
            {"symbol": "PHT1.1", "characterized_in": "arabidopsis_thaliana", "function": "Root high-affinity Pi transporter."},
            {"symbol": "PHO2", "alias": "UBC24", "characterized_in": "arabidopsis_thaliana", "function": "E2 ubiquitin ligase that down-regulates Pi uptake under P-replete conditions; miR399 target."},
            {"symbol": "PHR1", "characterized_in": "arabidopsis_thaliana", "function": "Master TF of the Pi-starvation response."},
            {"symbol": "PSTOL1", "characterized_in": "oryza_sativa", "function": "Phosphorus-Starvation Tolerance 1 — protein kinase; the Kasalath landrace allele dramatically improves rice P uptake on low-P soils. A canonical public-sector breeding success."},
        ],
    },
    "iron_uptake": {
        "description": "Strategy I (reductive) and Strategy II (chelative) iron acquisition under Fe-limited soils.",
        "natural_farming_relevance": "Iron biofortification + uptake-on-calcareous-soils are smallholder-nutrition priorities (HarvestPlus etc.).",
        "genes": [
            {"symbol": "IRT1", "characterized_in": "arabidopsis_thaliana", "function": "Root Fe2+ transporter (Strategy I); also takes up Zn, Mn, Cd — bottleneck for biofortification AND cadmium-accumulation."},
            {"symbol": "FRO2", "characterized_in": "arabidopsis_thaliana", "function": "Root-surface Fe3+ reductase; Strategy I."},
            {"symbol": "FIT", "alias": "FER", "characterized_in": "arabidopsis_thaliana", "function": "bHLH TF; master regulator of Strategy I Fe response."},
            {"symbol": "IDS3", "characterized_in": "hordeum_vulgare", "function": "Mugineic-acid biosynthesis; grass Strategy II Fe chelator."},
        ],
    },
    "mycorrhizal_symbiosis": {
        "description": "Common symbiosis (SYM) pathway enabling arbuscular mycorrhizal (AM) fungal colonization of root cells.",
        "natural_farming_relevance": "Central to Korean Natural Farming and JADAM nutrient strategies — AM fungi extend root reach and bridge plants to P, Zn, water. Most flowering plants are AM-competent.",
        "genes": [
            {"symbol": "SYMRK", "alias": "DMI2", "characterized_in": "medicago_truncatula", "function": "LRR receptor-like kinase essential for both AM and rhizobial symbiosis."},
            {"symbol": "CCaMK", "alias": "DMI3", "characterized_in": "medicago_truncatula", "function": "Ca2+/calmodulin-dependent kinase decoding the symbiosis-specific calcium spike."},
            {"symbol": "DMI1", "characterized_in": "medicago_truncatula", "function": "Cation channel required for symbiosis Ca2+ signaling."},
            {"symbol": "PT4", "alias": "PHT1;4", "characterized_in": "medicago_truncatula", "function": "Arbuscule-specific Pi transporter — receives P from the fungal symbiont."},
            {"symbol": "RAM1", "characterized_in": "medicago_truncatula", "function": "GRAS-domain TF required for arbuscule branching and maintenance."},
            {"symbol": "DELLA", "characterized_in": "arabidopsis_thaliana", "function": "GA-signaling repressor — required for AM colonization; ties symbiosis to gibberellin signaling."},
        ],
    },
    "rhizobial_nodulation": {
        "description": "Legume-specific nitrogen-fixing root-nodule symbiosis with rhizobia; shares the SYM pathway upstream with mycorrhizal signaling.",
        "natural_farming_relevance": "The atmospheric-N-fixation engine of legume-based natural farming and cover cropping (cowpea, common bean, hairy vetch, faba bean).",
        "genes": [
            {"symbol": "NFR1", "characterized_in": "lotus_japonicus", "function": "LysM receptor kinase perceiving rhizobial Nod factor."},
            {"symbol": "NFR5", "characterized_in": "lotus_japonicus", "function": "Co-receptor of NFR1 for Nod-factor perception."},
            {"symbol": "NIN", "characterized_in": "lotus_japonicus", "function": "Nodulation-specific TF — master regulator of nodule organogenesis."},
            {"symbol": "ERN1", "characterized_in": "medicago_truncatula", "function": "ERF TF required for infection-thread formation."},
            {"symbol": "NSP1", "characterized_in": "medicago_truncatula", "function": "GRAS-domain TF activating early Nod-factor responses."},
        ],
    },
    "root_architecture": {
        "description": "Lateral-root development, root depth, and root-hair density — the plant's interface with soil.",
        "natural_farming_relevance": "Root architecture is the *physical* interface to KNF-managed soil biology; deeper / denser / hairier roots = more rhizosphere recruitment, more drought escape, more nutrient capture.",
        "genes": [
            {"symbol": "PIN2", "characterized_in": "arabidopsis_thaliana", "function": "Auxin efflux carrier directing root-tip gravitropism."},
            {"symbol": "ARF7", "characterized_in": "arabidopsis_thaliana", "function": "Auxin response factor; master regulator of lateral-root initiation."},
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
            {"symbol": "OsKSL4", "characterized_in": "oryza_sativa", "function": "Kaurene synthase-like — momilactone biosynthesis cluster on chromosome 4."},
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
            {"symbol": "VRN1", "characterized_in": "triticum_aestivum", "function": "Wheat VRN1 — vernalization response; spring vs. winter wheat allelic basis."},
            {"symbol": "Hd1", "characterized_in": "oryza_sativa", "function": "Rice CO ortholog; heading-date QTL underlying photoperiod adaptation across rice latitudes."},
        ],
    },
    "plant_height_dwarfing": {
        "description": "Gibberellin-signaling alleles underlying the Green Revolution semi-dwarf phenotype.",
        "natural_farming_relevance": "Dwarfing alleles trade off against root depth and lodging resistance vs. yield-under-irrigation. Heritage tall varieties carry recessive *wild-type* alleles at these loci — relevant to context-specific landrace selection.",
        "genes": [
            {"symbol": "SD1", "characterized_in": "oryza_sativa", "function": "GA20 oxidase — IR8 'miracle rice' semi-dwarf allele underlying the rice Green Revolution."},
            {"symbol": "Rht-B1", "characterized_in": "triticum_aestivum", "function": "Wheat DELLA — gain-of-function alleles cause Norin-10 semi-dwarfing."},
            {"symbol": "D8", "characterized_in": "zea_mays", "function": "Maize DELLA; dwarfing allele used in some hybrid backgrounds."},
        ],
    },
    "tiller_branching": {
        "description": "Strigolactone signaling and TB1-family TFs governing shoot branching / tillering architecture.",
        "natural_farming_relevance": "Tiller number is a primary yield-architecture lever in cereals; landrace selection often shifts this trait toward the local growing system.",
        "genes": [
            {"symbol": "TB1", "alias": "tb1", "characterized_in": "zea_mays", "function": "TCP-domain TF — single locus underlying the most dramatic morphological difference between maize and teosinte (suppressed tillering)."},
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
            {"symbol": "MATE1", "alias": "AltSB", "characterized_in": "sorghum_bicolor", "function": "Root citrate efflux; the major sorghum Al-tolerance gene (Magalhães et al.)."},
            {"symbol": "STOP1", "characterized_in": "arabidopsis_thaliana", "function": "Zn-finger TF activating ALMT1 and other Al-tolerance genes under acidic conditions."},
        ],
    },
}


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
        result["target_species"] = _normalize_species(target_species)
        result["followup_hint"] = (
            f"To find the equivalent gene(s) in {result['target_species']}, "
            "call get_orthologs(gene=<symbol>, species=<characterized_in>, "
            f"target_species='{result['target_species']}') for each gene of "
            "interest. Pay attention to ortholog_one2many results — plants "
            "have undergone whole-genome duplications, so multiple paralogs "
            "are common, especially in maize, wheat (hexaploid), and "
            "sugarcane / sorghum."
        )
    return result


def main():
    mcp.run()


if __name__ == "__main__":
    main()
