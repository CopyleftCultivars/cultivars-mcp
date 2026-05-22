# Cultivars MCP — User Guide

Complete reference for grower-scientists, breeders, and natural-farming
researchers using Cultivars to query the open plant-genomics commons.

**Quick links:** [Quick Start](#quick-start) · [Tool reference](#tool-reference) · [Workflow recipes](#workflow-recipes) · [Species coverage](#species-coverage) · [Trait atlas](#trait-atlas) · [FAQ](#faq) · [Glossary](#glossary)

---

## Quick Start

### Install

You need Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/CopyleftCultivars/evee-mcp-fork-for-plants.git
cd evee-mcp-fork-for-plants
uv sync
```

### Run with Claude Code

The repo ships a `.mcp.json` so Claude Code auto-loads the tools:

```bash
claude
```

The first time you open the directory, Claude Code will ask permission to enable the `cultivars` MCP server. Approve it.

### Run with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cultivars": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/evee-mcp-fork-for-plants", "python3", "server.py"]
    }
  }
}
```

### Your first query

Ask Claude:

> "What are the canonical drought-tolerance genes in Arabidopsis, and what are their orthologs in sorghum?"

It'll call `translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")` and respond with 6 canonical genes plus their sorghum orthologs, each tagged with evidence tier. ~2 seconds.

---

## Tool reference

19 tools across 5 external databases plus the curated trait atlas.

### Ensembl Plants gene-and-variant tools

#### `list_plant_species(query=None)`

Discover species in Ensembl Plants. Returns the Ensembl `name` you'll pass to other tools.

```python
list_plant_species(query="rice")
# → 25 hits: oryza_sativa, oryza_glaberrima, oryza_indica, oryza_nivara, oryza_sativa_gobolsailbalam (Indica Gobol Sail landrace), ...
```

#### `lookup_gene(gene, species=None, expand=False)`

Resolve a gene by symbol or stable ID.

```python
lookup_gene(gene="PHYB", species="arabidopsis_thaliana")
# → {"gene_id": "AT2G18790", "symbol": "PHYB", "description": "phytochrome B", ...}

lookup_gene(gene="AT2G18790")  # stable ID — species inferred
```

Tries stable-ID lookup first, then symbol. Returns Ensembl `display_name` (which sometimes differs from the literature name — e.g., PIN2 → "EIR1" — the atlas notes this where it matters).

#### `search_variants_in_region(region, species=None, limit=25)`

List known variants in a genomic region (1-based, inclusive).

```python
search_variants_in_region(region="2:8140000-8140100", species="arabidopsis_thaliana", limit=5)
# → 5 variants from "The 1001 Genomes Project"
```

**Variation coverage varies wildly by species.** Arabidopsis (1001 Genomes) and rice (3K Rice Genomes) are rich. Most crops return `[]` — that's a data gap, not a tool error. The response includes a `species_quality` field with the tier (richly_covered / moderately_covered / gene_models_only / not_in_ensembl_plants).

#### `get_variant(variant_id, species=None)`

Fetch a known variant by Ensembl stable ID.

```python
get_variant(variant_id="ENSVATH00237387", species="arabidopsis_thaliana")
# → {"variant_class": "SNP", "most_severe_consequence": "5_prime_UTR_variant", ...}
```

#### `predict_variant_effect(region=None, allele=None, variant_id=None, species=None)`

Run Ensembl VEP (Variant Effect Predictor) on a novel variant or a known one.

```python
# Novel variant — pass region + allele:
predict_variant_effect(region="2:8140000-8140000", allele="T", species="arabidopsis_thaliana")
# → 6 transcript-level consequences, each with impact (HIGH/MODERATE/LOW/MODIFIER)

# Known variant — pass variant_id:
predict_variant_effect(variant_id="ENSVATH00237387", species="arabidopsis_thaliana")
```

VEP is rule-based (classical), not a deep-learning effect predictor. Treat consequence terms as **descriptive** (e.g., "missense_variant"), not as effect-magnitude scores.

#### `compare_variants(variant_ids, species=None)`

Side-by-side summary of 2–10 known variants in one call.

```python
compare_variants(variant_ids=["ENSVATH00237387", "ENSVATH07882512"], species="arabidopsis_thaliana")
```

#### `get_orthologs(gene, species=None, target_species=None, target_taxon=None)`

Cross-species gene translation via Ensembl Compara.

```python
get_orthologs(gene="PHYB", species="arabidopsis_thaliana", target_species="oryza_sativa")
# → 1 ortholog: Os03g0309200, type=ortholog_one2many, taxonomy_level=Mesangiospermae
```

Note ortholog `type`:
- `ortholog_one2one` — strongest evidence
- `ortholog_one2many` — gene duplicated in target species (common in plants — paleopolyploidy)
- `ortholog_many2many` — both sides duplicated (very common in wheat, maize)

And `taxonomy_level` — `Brassicaceae` (Brassicas) is stronger evidence than `Viridiplantae` (all green plants).

#### `get_sequence(stable_id, seq_type="genomic", species=None)`

Fetch genomic / cDNA / CDS / protein sequence.

```python
get_sequence(stable_id="AT2G18790.1", seq_type="protein")
# → 1172-aa PHYB protein sequence
```

For protein / cDNA / CDS, **pass a transcript ID** (`AT2G18790.1`), not a gene ID.

---

### Trait atlas tools

#### `list_trait_categories()`

Discover the 30 curated trait categories.

```python
list_trait_categories()
# → 30 traits: drought_tolerance, salt_tolerance, ..., cannabinoid_biosynthesis, maize_pest_resistance, ...
```

#### `find_trait_genes(trait, target_species=None)`

Look up canonical genes for a trait. Each gene comes with **evidence tier**, **primary literature reference** (for ~10 canonical entries), and **UniProt cross-reference** where curated.

```python
find_trait_genes(trait="salt_tolerance", target_species="oryza_sativa")
# → 6 genes; high_curated_gene_count: 6 (100%)
#   SOS1 → UniProt Q9LKW9, evidence_tier: high_curated, primary_ref: Shi 2000 PMID 10823923
#   SOS2 → Q9LDI3, knockout_phenotype evidence, Liu 2000 PMID 10725357
#   SOS3 → O81223, knockout_phenotype, Liu & Zhu 1998 PMID 9632394
#   NHX1 → Q68KI4, NHX7 sodium/hydrogen exchanger
#   HKT1 → Q84TI7, sodium transporter
#   OsHKT1;5 → Q0JNB6 (Saltol QTL — the Pokkali landrace tolerance allele)
```

Loose matching: `"drought"` → `drought_tolerance`. `"Drought-Tolerance"` → same.

#### `translate_trait_to_species(trait, target_species, max_genes=None)`

Composed tool — finds canonical genes for a trait AND issues concurrent ortholog calls to translate each to a target species. One call replaces ~7 sequential calls.

```python
translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")
# → 6 canonical Arabidopsis genes → 4 sorghum orthologs in ~2 seconds:
#   DREB1A  → SORBI_3002G269100 (+6 paralogs)
#   DREB2A  → SORBI_3009G101400
#   HVA1    → SORBI_3009G215700
#   DRO1    → SORBI_3002G215300
```

3.7× faster than sequential, 7× fewer agent tool calls.

---

### Veracity / living-document tools

#### `lookup_gene_evidence(stable_id, species=None)`

Pull the Ensembl cross-reference chain for a gene — the **veracity backbone**.

```python
lookup_gene_evidence(stable_id="AT2G18790", species="arabidopsis_thaliana")
# → {
#     "evidence_tier": "high_curated",
#     "uniprot_curated": [{"id": "P14713", ...}],   # SwissProt manually-curated
#     "go_term_count": 88,
#     "plant_reactome_pathways": ["Circadian rhythm", "Long day regulated expression of florigens"],
#     "pdb_structures": [{"id": "4OUR"}, {"id": "7RZW"}, {"id": "8YB4"}, {"id": "9IUZ"}],
#     "uniprot_lookup_url": "https://www.uniprot.org/uniprotkb/P14713",
#   }
```

Use whenever you need to **verify an atlas claim**.

#### `lookup_uniprot_entry(uniprot_id)`

Direct UniProt REST query. **Works for Cannabis genes** even though Cannabis isn't in Ensembl Plants.

```python
lookup_uniprot_entry(uniprot_id="Q8GTB6")  # THCAS, Cannabis
# → {
#     "protein_name": "Tetrahydrocannabinolic acid synthase",
#     "organism": "Cannabis sativa",
#     "function": ["Oxidoreductase in cannabinoid biosynthesis..."],
#     "catalytic_activities": [{"reaction": "cannabigerolate + O2 = THCA + H2O2", "ecNumber": "1.21.3.7"}],
#     "cofactors": ["FAD"],
#     "pubmed_citation_count": 7,
#     "go_terms": [...with evidence codes EXP/IDA/IEA...],
#   }
```

GO **evidence codes** distinguish experimental validation (`EXP`, `IDA`, `IPI`, `IMP`, `IGI`) from inferred annotation (`IEA`, `ISS`).

#### `search_pubmed_for_gene(query, page_size=10)`

EuropePMC literature search — the **living document** for primary literature.

```python
search_pubmed_for_gene(query="OsNRT1.1B rice nitrogen", page_size=5)
# → 190 hits including 2025 + 2026 papers; each with PMID, DOI, open-access flag, citation count.
```

Use to find papers newer than the trait atlas's `primary_ref` citations.

#### `get_string_interactions(protein_id, species=None, score_threshold=400, limit=25)`

STRING-db protein-protein interaction network. **Covers Cannabis sativa** (NCBI taxon 3483).

```python
get_string_interactions(protein_id="SOS1", species="arabidopsis_thaliana", limit=10)
# → 10 interactions, top partner CIPK24 (= SOS2 — the canonical interactor), combined_score 0.999
```

Per-channel evidence scores: `experimental`, `database`, `textmining`, `coexpression`, `neighborhood`, `fusion`, `phylogenetic`. Text-mining-only edges are weaker than experimental + database curation.

---

### Cannabis tools (Kannapedia + helpers)

#### `lookup_kannapedia_strain(rsp_id)`

**Live fetch** from Medicinal Genomics Kannapedia.

```python
lookup_kannapedia_strain(rsp_id="13536")
# → {
#     "strain_name": "Crème de la Crème x Pearadise #4",
#     "plant_type_chemotype": "Type I",       # I = THC-dominant, II = balanced, III = CBD-dominant
#     "plant_sex": "Female",
#     "heterozygosity": "1.11%",
#     "y_ratio_distribution": "0.0198",
#     "grower": "Team Elite Genetics",
#     "rarity_classification": "Uncommon",
#     "cannabis_genes_mentioned_on_page": ["THCAS", "CBDAS", "CBCAS", "ELF3", "FAD2", "PHL", "PKSG", ...],
#     "data_files": {
#       "annotated_vcf": ["https://mgcdata.s3.amazonaws.com/.../RSP13536.vcf.gz"],
#       "fastq_reads": [..._R1.fastq.gz, ..._R2.fastq.gz],
#       "bam_alignment": [...]
#     },
#     "related_strains": ["rsp10837", "rsp11072", ...]  # 40 phylogenetic relatives
#   }
```

#### `compare_cannabis_strains(rsp_ids)`

Concurrent batch comparison of 2–5 strains.

```python
compare_cannabis_strains(rsp_ids=["13536", "13534", "10837"])
# → {
#     "chemotype_distribution": {"Type I": 2, "Type III": 1},
#     "rarity_distribution": {"Uncommon": 1, "Rare": 1, "Common": 1},
#     "genes_flagged_on_multiple_strains": ["CBCAS", "CBDAS", "ELF3", "EMF1", "FAD2", "PHL", "PKSG", "THCAS", ...],
#     "comparison": [<one row per strain>],
#     "elapsed_seconds": 2.72
#   }
```

#### `cannabis_strain_search_urls(query)`

URL constructors for Kannapedia, Leafly, SeedFinder, NCBI Taxonomy, EuropePMC.

```python
cannabis_strain_search_urls(query="Northern Lights")
# → {
#     "search_urls": {
#       "kannapedia": "https://www.kannapedia.net/strains?search=Northern+Lights",
#       "leafly": "https://www.leafly.com/search?q=Northern+Lights",
#       ...
#     }
#   }
```

---

### Maize tools

#### `list_maize_nam_founders(subpopulation=None)`

The 26-line maize NAM founder panel (McMullen 2009 + Hufford 2021 reference-quality genomes).

```python
list_maize_nam_founders(subpopulation="Tropical / Subtropical")
# → 13 lines including 8 CIMMYT CML lines + Thai Ki3/Ki11 + IITA Tzi8
```

Subpopulations: `"Stiff Stalk"`, `"Non-Stiff Stalk"`, `"Tropical / Subtropical"`, `"Popcorn"`, `"Sweet Corn"`. The Tropical/Subtropical subset is highlighted for smallholder breeders.

---

## Workflow recipes

### Recipe 1: "Is my hemp cultivar safely Type III?"

```
1. lookup_kannapedia_strain(rsp_id="13534")
   → confirms Type III (CBD-dominant)
2. find_trait_genes(trait="hemp_compliance")
   → BT/BD allele system, de Meijer 2003 + Weiblen 2015 PMID 26242869
3. lookup_uniprot_entry(uniprot_id="Q8GTB6")  # THCAS
   → curated function statement + 7 PubMed cites
4. search_pubmed_for_gene(query="hemp Type III THCAS pseudogene")
   → newest published evidence on the chemotype-determining locus
```

### Recipe 2: "Translate Arabidopsis drought genes into my crop"

```
translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")
# Single call. Returns 6 canonical genes + 4 sorghum orthologs in ~2 seconds.
# Each gene tagged with evidence_tier, characterized_in species, and primary_ref.
```

### Recipe 3: "What heritage maize lines should I cross with?"

```
1. list_maize_nam_founders(subpopulation="Tropical / Subtropical")
   → 13 CIMMYT/IITA/Thai tropical lines selected for diversity
2. find_trait_genes(trait="maize_disease_resistance")
   → Ht1 (NLB), Htn1 (Hurni 2015 PMID 26124137), Rcg1 (anthracnose)
3. find_trait_genes(trait="maize_pest_resistance")
   → Mir1-CP (Pechan 2000 PMID 10899972) — non-Bt fall armyworm resistance
```

### Recipe 4: "Genetic basis of mycorrhizal symbiosis"

```
1. find_trait_genes(trait="mycorrhizal_symbiosis")
   → 6 canonical SYM-pathway genes
2. lookup_gene(gene="CCaMK", species="medicago_truncatula")
   → gene46630 (the central calcium-decoding kinase)
3. get_string_interactions(protein_id="CCaMK", species="medicago_truncatula")
   → STRING returns NSP1 (canonical SYM TF) + Vpy + 13 more interactors
4. lookup_uniprot_entry on each curated partner for full function statements
```

### Recipe 5: "Compare three cannabis strains I'm thinking of breeding from"

```
compare_cannabis_strains(rsp_ids=["13536", "13534", "10837"])
# Returns chemotype distribution, rarity, and genes flagged on multiple strain pages
# — surfaces the variant patterns they share, in one call.
```

### Recipe 6: "What's the latest on PSTOL1 (rice P-uptake)?"

```
1. find_trait_genes(trait="phosphorus_uptake")
   → PSTOL1: Os12g0552900, primary_ref Gamuyao 2012 PMID 22914168
2. lookup_gene_evidence(stable_id="Os12g0552900")
   → UniProt cross-refs + 4 GO terms
3. search_pubmed_for_gene(query="PSTOL1 rice Kasalath phosphorus")
   → newest papers, citation counts, open-access flags
```

---

## Species coverage

### Richly covered (rich variation data + reference assembly)
| Species | Common name | Variation source |
|---|---|---|
| `arabidopsis_thaliana` | Thale cress | 1001 Genomes (~12M SNPs across 1,135 accessions) |
| `oryza_sativa` | Asian rice (japonica) | 3K Rice Genomes Project |
| `oryza_indica` | Indica rice | 3K Rice Genomes (indica subset) |

### Moderately covered (partial variation data)
| Species | Common name | Notes |
|---|---|---|
| `zea_mays` | Maize | HapMap / NAM panel partially exposed |
| `triticum_aestivum` | Bread wheat | IWGSC + breeding population resequencing; HEXAPLOID (A/B/D subgenomes) |
| `solanum_lycopersicum` | Tomato | 150 Tomato Genome Project + Varitome |
| `vitis_vinifera` | Grape | Viticulture-focused catalogs |

### Gene models only (no variation database)
Most other Ensembl Plants species. `search_variants_in_region` returns `[]` for these — that's a data gap, not a tool error.

### Not in Ensembl Plants (special handling)
| Species | Why | What the tool does |
|---|---|---|
| `cannabis_sativa` | Federal-research-funding history excluded Cannabis from public infrastructure | Returns a structured fallback with `lookup_kannapedia_strain` + UniProt search URLs + CS10 accession + Cannabis Genome DB pointer |
| `psilocybe_cubensis` | Fungus, not plant | Points to Ensembl Fungi |

---

## Trait atlas

30 categories spanning 123 canonical genes. Use `list_trait_categories()` for the live list.

### Abiotic stress
- `drought_tolerance` — DREB1A, DREB2A, OST1, RD29A, HVA1, DRO1
- `salt_tolerance` — SOS1/2/3, NHX1, HKT1, OsHKT1;5
- `cold_tolerance` — CBF1/2, ICE1, COR15A
- `heat_tolerance` — HsfA1a, HsfA2, HSP70, HSP101
- `submergence_tolerance` — SUB1A (Swarna-Sub1 lineage), SK1, SK2
- `aluminum_tolerance` — ALMT1, MATE1/SbMATE, STOP1

### Nutrient acquisition
- `nitrogen_use_efficiency` — NRT1.1, NRT2.1, NRT1.1B (indica rice), AMT1;1, GS1
- `phosphorus_uptake` — PHT1;1, PHO2, PHR1, PSTOL1 (Kasalath landrace)
- `iron_uptake` — IRT1, FRO2, FIT, IDS3

### Symbiosis
- `mycorrhizal_symbiosis` — SYMRK, CCaMK, DMI1, PT4, RAM1, GAI/DELLA
- `rhizobial_nodulation` — NFP, LYK3, NIN, ERN1, NSP1

### Plant architecture & development
- `root_architecture` — EIR1/PIN2, NPH4/ARF7, LBD16, RHD6, DRO1
- `flowering_photoperiod` — FT, CO, FLC, Vrn-A1 (wheat), Hd1 (rice)
- `plant_height_dwarfing` — SD1 (IR8 miracle rice), Rht-B1 (Norin-10 wheat), D8
- `tiller_branching` — TB1 (teosinte→maize), MAX2, D14, MOC1

### Defense
- `defense_jasmonate` — COI1, MYC2, LOX2, JAR1, JAZ1
- `terpene_biosynthesis` — TPS21, TPS10, STO1, OsKS4/KSL4
- `glucosinolate_biosynthesis` — MYB28/29/51, CYP79B2
- `general_lepidopteran_pest_resistance` — Mir1-CP, PI-II, Mi-1.2, Bt-receptor cadherins

### Quality
- `grain_quality` — Wx/Waxy, BADH2/fgr (basmati fragrance), GBSSII, GLU-A1
- `cell_wall_biosynthesis` — CESA1, CESA4/IRX5, PAL1, CCR1, CAD5
- `photosynthesis_c4` — PEPC, NADP-ME, PPDK, RBCS1A

### Cannabis-specific (literature handles — not in Ensembl Plants)
- `cannabinoid_biosynthesis` — CsAAE1 → OLS → OAC → CsPT4 → THCAS/CBDAS/CBCAS
- `cannabis_terpene_profile` — CsTPS1 (myrcene), CsTPS9 (β-caryophyllene), CsTPS18 (terpinolene), CsTPS3 (linalool), CsTPS19 (α-pinene)
- `hemp_compliance` — BT/BD allele system
- `cannabis_sex_and_photoperiod` — MADC2 sex marker, CsAuto, CsELF3
- `cannabis_disease_resistance` — PMR loci, MLO orthologs, PR1

### Maize-specific
- `maize_quality_protein` — Opaque-2, Floury-2
- `maize_disease_resistance` — Ht1, Htn1, Rcg1
- `maize_pest_resistance` — Mir1-CP

---

## FAQ

**Q: Do I need API keys for any of the underlying databases?**
A: No. Ensembl, UniProt, EuropePMC, STRING, and Kannapedia all serve public data without authentication. That's the whole point.

**Q: What's the deal with `evidence_tier`?**
A: Each gene in the atlas is graded against Ensembl xrefs into:
- `high_curated` — Has UniProt/SWISSPROT entry (manually curated by a trained biocurator)
- `moderate_auto_annotated` — UniProt/SPTREMBL entry + substantial GO annotation
- `low_some_annotation` — Some functional annotation but not curated
- `minimal` — Cross-references exist but no functional annotation

73% of atlas entries reach `high_curated`. The remaining 27% are split between auto-annotated entries and literature handles (genes that don't symbol-resolve in Ensembl).

**Q: What's a "literature handle"?**
A: A gene we know about from the published literature but that doesn't resolve via `lookup_gene` in Ensembl Plants — usually because (a) the species isn't in Ensembl (Cannabis), or (b) the gene is at a locus that Ensembl hasn't symbol-indexed (barley HVA1, sorghum SbMATE). Each literature handle includes a `note` field with citation pointers + the recommended way to look up the gene (typically by ortholog from a resolvable source species).

**Q: Why is Cannabis sativa not in Ensembl Plants?**
A: Historical federal-research-funding gap. Public-sector plant-genomics infrastructure was built before cannabis legalization made the species fundable in many jurisdictions. The tool handles this honestly — every Cannabis lookup returns a structured fallback pointing at NCBI CS10 (the canonical 2021 Grassa reference assembly), Cannabis Genome DB, Kannapedia (live strain data), and the cannabis-specific trait atlas categories.

**Q: How current is the trait atlas?**
A: The atlas is hand-curated and version-controlled in this repo. The audit results (`atlas_evidence.json`) reflect Ensembl Plants release 115 (quarterly refresh). To regenerate the audit against a newer Ensembl release, run `evals/atlas_audit.py`. Primary literature citations (`primary_ref` fields) are the seminal characterization papers and are stable.

**Q: How does it handle Ensembl rate limits?**
A: Ensembl REST has a documented ~15 req/s soft limit. The `_get_with_retry` helper honors `Retry-After` headers on 429 / 503 responses with exponential backoff. The `translate_trait_to_species` concurrent tool caps internal worker count at 6.

**Q: What about offline use?**
A: Cultivars is the *desk-side* companion. For offline use, see [TinyLLamaFarmer](https://github.com/CopyleftCultivars/TinyLLamaFarmer) (offline natural-farming AI) and the [gemma4-natural-farming](https://huggingface.co/CopyleftCultivars/gemma4-natural-farming-gguf) open-weight model. They run on a phone without connectivity.

**Q: Can I extend the trait atlas?**
A: Yes. Edit `TRAIT_ATLAS` in `server.py`, then regenerate `atlas_evidence.json` via `evals/atlas_audit.py`. PRs welcome — we add trait categories in response to grower-scientist requests.

**Q: What's the license?**
A: This is a fork; the upstream EVEE MCP project's license applies. Copyleft Cultivars's own work is open-source under permissive licenses (Apache 2.0 / MIT depending on project), consistent with the org's free-software ethos.

---

## Glossary

| Term | Meaning |
|---|---|
| **BT/BD allele** | The cannabis chromosome-6 locus where BT (functional THCAS) and BD (functional CBDAS) alleles determine chemotype Type I/II/III |
| **Chemotype I/II/III** | Cannabis classification: Type I = THC-dominant, Type II = balanced, Type III = CBD-dominant (hemp-compliant) |
| **Compara** | Ensembl's protein-tree-based comparative genomics resource — powers `get_orthologs` |
| **CS10** | Cannabis sativa reference genome v10 (Grassa et al. 2021), NCBI GCF_900626175.2 |
| **GO** | Gene Ontology — controlled vocabulary for gene function (process / function / component) |
| **GO evidence code** | Tag on a GO annotation indicating how it was derived (EXP/IDA = experimentally validated; IEA/ISS = inferred) |
| **HGVS** | Human Genome Variation Society nomenclature for variants (also used in plants) |
| **High_curated** | Atlas evidence tier — gene has a UniProt/SWISSPROT manually-curated entry |
| **KNF** | Korean Natural Farming — natural-farming methodology emphasizing indigenous microorganisms (IMO) |
| **Kannapedia** | Medicinal Genomics's public cannabis-strain database |
| **NAM** | Nested Association Mapping — 26-line maize founder panel (McMullen 2009) |
| **PMID** | PubMed ID — unique identifier for a biomedical paper |
| **PMR** | Powdery Mildew Resistance |
| **QPM** | Quality Protein Maize — CIMMYT lysine/tryptophan-enriched maize varieties (Vasal/Villegas, World Food Prize 2000) |
| **RSP ID** | Kannapedia strain identifier (e.g., `rsp13536`) |
| **SwissProt** | The manually-curated tier of UniProt — gold standard for protein function |
| **SYM pathway** | Common symbiosis signaling pathway shared between mycorrhizal and rhizobial symbiosis |
| **SUB1** | Rice submergence-tolerance locus (Xu 2006); SUB1A introgression underlies Swarna-Sub1 and similar flood-tolerant rice varieties |
| **TrEMBL / SPTREMBL** | Auto-annotated tier of UniProt (less curated than SwissProt) |
| **VEP** | Variant Effect Predictor — Ensembl's rule-based variant-consequence annotator |
| **Y-Ratio** | Kannapedia's measure of Y-chromosome marker abundance in a cannabis sample (sex-purity check) |
