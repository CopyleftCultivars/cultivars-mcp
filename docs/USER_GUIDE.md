# Cultivars MCP — User Guide

Complete reference for grower-scientists, breeders, and natural-farming
researchers using Cultivars to query the open plant-genomics commons.

**Quick links:** [Quick Start](#quick-start) · [Tool reference](#tool-reference) · [Workflow recipes (by persona)](#workflow-recipes) · [Species coverage](#species-coverage) · [Trait atlas](#trait-atlas) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) · [Glossary](#glossary)

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

### Community science tools (the write path)

Everything above is read-only. These tools let grower-scientists **contribute**
observations and reason about collective statistical power. Ledger data is
licensed **ODbL-1.0** (open-data copyleft — see `DATA_LICENSE.md`), distinct
from the Apache-2.0 code license.

#### `submit_phenotype_observation(...)`

Records a field observation as a schema-v1.0 YAML under `ledger_dir` (default
`./phenotypes/`, override with `CULTIVARS_LEDGER_DIR`). Validates the trait
category and species, sanitizes the file path, and returns a `canonical_form`
to sign plus PR instructions. **No GitHub credentials are used** — the tool
prepares the artifact; you open the PR.

```python
submit_phenotype_observation(
    accession_id="community:hopi_blue",      # or a formal GRIN/IRRI/USDA ID
    common_name="Hopi blue corn",
    species="zea_mays",
    trait_category="drought_tolerance",
    measurement_type="binary", measurement_value=True,
    measurement_protocol="rainfed_no_irrigation_2026",
    agroecological_zone="us_southwest_arid", season="2026",
)
# → {ok: True, written: True, path: ".../phenotypes/zea_mays/community_hopi_blue/drought_tolerance_2026-05-29.yaml",
#    content_hash: "sha256:…", canonical_form: "…", accession_suggestion: "run resolve_accession …"}
```

#### `query_community_phenotypes(trait_category, species=None, min_observations=1)`

Aggregates the ledger: observation count, measurement distribution, distinct
accessions, signed-observation count.

#### `estimate_gwas_power(trait_category, species, n_observations=None, ...)`

"Can my village's 12 rice varieties detect SUB1A?" Pulls the current count from
the ledger when `n_observations` is omitted, then reports the sample size needed
for 80% power to detect large- (~10% variance) and medium- (~5%) effect loci,
the formula, the assumptions, and the recruit-N-more gap. Order-of-magnitude
guidance — not a substitute for a mixed-model power analysis.

#### `verify_observation_integrity(yaml_path_or_content, pubkey=None)`

Verifies a detached **Ed25519** signature over the canonical observation form.
Sign `canonical_form` with your keypair and resubmit with `submitter_pubkey` +
`signature` to attach verifiable, pseudonymous attribution. Not a token.

#### `pin_observation_to_ipfs(yaml_path, vcf_path=None)`

Content-addresses an observation (and optional VCF) via a local kubo node
(`CULTIVARS_IPFS_API`, default `http://127.0.0.1:5001`); writes the CID into the
YAML. Returns a structured fallback with setup steps if no node is reachable.

#### `resolve_accession(query, crop_type=None, region=None)`

Bridges a folk seed name ("my grandmother's Hopi blue corn") to a USDA
**GRIN-Global** accession and an Ensembl species string. Run this *before*
`submit_phenotype_observation` / `lookup_gene` when the name is informal.

#### `query_organellar_variants(species, organelle="plastid", region=None, trait=None)`

First-class **Mt/Pt** queries plus a curated organellar mini-atlas: `cms`
(cytoplasmic male sterility — hybrid seed), `plastid_herbicide_resistance`
(psbA/atrazine), `plastid_photosynthesis` (rbcL). `Mt`/`Pt` are valid Ensembl
chromosomes, not errors.

#### `export_offline_snapshot(trait_category, species, include_orthologs=True)`

Packages a trait's atlas entry, species coverage, and optional orthologs into a
portable JSON under `snapshots/` for offline use with TinyLLamaFarmer.

#### `list_orphan_crop_requests()`

Returns the `WANTED_TRAITS.yaml` orphan-crop contribution bounty list.

#### Population context on existing variant tools

`get_variant(..., population_context=True)` and
`search_variants_in_region(..., population_context=True)` add per-population
allele frequencies and a coarse Indica/Japonica Wright's Fst — for
`richly_covered` species only; a structured "not available" notice otherwise.

---

## Workflow recipes

Recipes are organized by **user persona**. Find your role below; each section has the recipes most relevant to that kind of work. Recipes show the tool calls; an LLM agent uses them to assemble a natural-language answer.

### 🌿 For cannabis & hemp growers / breeders

#### Recipe 1: "Is my hemp cultivar safely Type III?"

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

#### Recipe 2: "Compare three cannabis strains I'm thinking of breeding from"

```
compare_cannabis_strains(rsp_ids=["13536", "13534", "10837"])
# Returns chemotype distribution, rarity, and genes flagged on multiple strain pages
# — surfaces the variant patterns they share, in one call.
```

#### Recipe 2b: "What does the cannabinoid biosynthesis pathway look like at the molecular level?"

```
1. find_trait_genes(trait="cannabinoid_biosynthesis")
   → CsAAE1 → OLS → OAC → CsPT4 → THCAS / CBDAS / CBCAS (7-enzyme pathway)
2. lookup_uniprot_entry(uniprot_id="Q8GTB6")  # THCAS
   → "Tetrahydrocannabinolic acid synthase", EC 1.21.3.7, FAD cofactor, reaction
     CBGA + O2 → THCA + H2O2, with 7 PubMed citations including Sirikantaramas 2004
3. lookup_uniprot_entry(uniprot_id="A6P6V9")  # CBDAS
   → Curated function statement + Taura 2007 citation
```

### 🌽 For heritage corn / maize growers + breeders

#### Recipe 3: "Translate Arabidopsis drought genes into my crop"

```
translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")
# Single call. Returns 6 canonical genes + 4 sorghum orthologs in ~2 seconds.
# Each gene tagged with evidence_tier, characterized_in species, and primary_ref.
```

#### Recipe 4: "What heritage maize lines should I cross with?"

```
1. list_maize_nam_founders(subpopulation="Tropical / Subtropical")
   → 13 CIMMYT/IITA/Thai tropical lines selected for diversity
2. find_trait_genes(trait="maize_disease_resistance")
   → Ht1 (NLB), Htn1 (Hurni 2015 PMID 26124137), Rcg1 (anthracnose)
3. find_trait_genes(trait="maize_pest_resistance")
   → Mir1-CP (Pechan 2000 PMID 10899972) — non-Bt fall armyworm resistance
```

### 🌾 For natural-farming / regenerative researchers

#### Recipe 5: "Genetic basis of mycorrhizal symbiosis"

```
1. find_trait_genes(trait="mycorrhizal_symbiosis")
   → 6 canonical SYM-pathway genes
2. lookup_gene(gene="CCaMK", species="medicago_truncatula")
   → gene46630 (the central calcium-decoding kinase)
3. get_string_interactions(protein_id="CCaMK", species="medicago_truncatula")
   → STRING returns NSP1 (canonical SYM TF) + Vpy + 13 more interactors
4. lookup_uniprot_entry on each curated partner for full function statements
```

#### Recipe 6: "What's the latest on PSTOL1 (rice P-uptake) for low-P soils?"

```
1. find_trait_genes(trait="phosphorus_uptake")
   → PSTOL1: Os12g0552900, primary_ref Gamuyao 2012 PMID 22914168
2. lookup_gene_evidence(stable_id="Os12g0552900")
   → UniProt cross-refs + 4 GO terms
3. search_pubmed_for_gene(query="PSTOL1 rice Kasalath phosphorus")
   → newest papers, citation counts, open-access flags
```

#### Recipe 7: "What stress-tolerance loci could I look at in a sorghum landrace from a dry region?"

```
1. find_trait_genes(trait="drought_tolerance", target_species="sorghum_bicolor")
2. find_trait_genes(trait="aluminum_tolerance", target_species="sorghum_bicolor")
   → If you're growing on acidic tropical soils, this matters as much as drought
3. find_trait_genes(trait="heat_tolerance", target_species="sorghum_bicolor")
4. For each canonical gene of interest, get_orthologs to translate to sorghum,
   then search_pubmed_for_gene to find the newest sorghum-specific literature
```

#### Recipe 8: "I want to understand how my legume cover crop fixes nitrogen — what genes are involved?"

```
1. find_trait_genes(trait="rhizobial_nodulation")
   → 5 SYM-pathway genes from Medicago truncatula (the model legume): NFP, LYK3, NIN, ERN1, NSP1
2. find_trait_genes(trait="mycorrhizal_symbiosis")
   → The SYM pathway is SHARED upstream between rhizobial nodulation and AM symbiosis
3. lookup_uniprot_entry(uniprot_id="<UniProt ID from atlas>")  # for each
4. lookup_gene_evidence + get_string_interactions for the central kinase (CCaMK/DMI3)
```

### 🌱 For community-science contributors / seed-keeper networks

The write path. These recipes grow the commons — a grower's field observation
becomes GWAS-relevant, attributable, open data.

#### Recipe 9: "Record that my landrace survived the flood, and tell me if it helps map the locus"

```
1. resolve_accession(query="Gobol Sail")
   → bridges the folk name to a USDA GRIN accession + ensembl_species="oryza_sativa"
2. submit_phenotype_observation(
       accession_id="IRGC_12345", common_name="Gobol Sail", species="oryza_sativa",
       trait_category="submergence_tolerance", trait_atlas_gene="SUB1A",
       measurement_type="binary", measurement_value=True,
       measurement_protocol="14_day_submergence_field", season="kharif_2026")
   → writes phenotypes/oryza_sativa/IRGC_12345/submergence_tolerance_<date>.yaml (ODbL-1.0)
   → returns content_hash, a canonical_form to sign, and PR instructions
3. estimate_gwas_power(trait_category="submergence_tolerance", species="oryza_sativa")
   → pulls the live ledger count: "you have N observations, need ~M for 80% power —
     submit yours and recruit M-N more"
4. (in your shell) commit the YAML and open a PR — the tool never needs your GitHub creds
```

#### Recipe 10: "Sign my observation so my contribution is verifiable"

Attribution is a pseudonymous scientific CV tied to an Ed25519 keypair — **not** a
token or wallet. The tool returns the exact bytes to sign (`canonical_form`).

```bash
# One-time: generate an Ed25519 keypair (any Ed25519 tool works; example uses Python)
python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; \
from cryptography.hazmat.primitives import serialization as s; \
k=Ed25519PrivateKey.generate(); \
open('key.sk','wb').write(k.private_bytes(s.Encoding.Raw,s.PrivateFormat.Raw,s.NoEncryption())); \
print('pubkey: ed25519:'+k.public_key().public_bytes(s.Encoding.Raw,s.PublicFormat.Raw).hex())"
```

```
1. submit_phenotype_observation(..., write=False)        # get canonical_form back
2. (sign canonical_form's UTF-8 bytes with key.sk → signature hex)
3. submit_phenotype_observation(..., submitter_pubkey="ed25519:<hex>", signature="<hex>")
4. verify_observation_integrity(yaml_path_or_content="phenotypes/.../...yaml")
   → {verified: true, submitter_pubkey, canonical_hash}
```

#### Recipe 11: "Take a trait offline to the field, and make an observation permanent"

```
1. export_offline_snapshot(trait_category="drought_tolerance", species="sorghum_bicolor")
   → portable JSON in snapshots/ for TinyLLamaFarmer (atlas + coverage + orthologs)
2. pin_observation_to_ipfs(yaml_path="phenotypes/.../...yaml")
   → content-addressed CID, written back into the YAML (needs a local kubo node;
     returns setup instructions if none is running)
```

#### Recipe 12: "Contribute an orphan crop my community grows"

```
1. list_orphan_crop_requests()
   → the WANTED_TRAITS.yaml bounty list (fonio, bambara groundnut, enset, grass pea, quinoa)
2. (open a PR adding the trait to TRAIT_ATLAS per CONTRIBUTING.md '# ORPHAN CROPS BOUNTY')
```

#### Configuration (environment variables)

| Variable | Default | Controls |
|---|---|---|
| `CULTIVARS_LEDGER_DIR` | `./phenotypes` | Where `submit_phenotype_observation` writes and `query_community_phenotypes` reads. Point it at a git working copy for PR-based submission, or a shared volume for a local network. |
| `CULTIVARS_SNAPSHOTS_DIR` | `./snapshots` | Where `export_offline_snapshot` writes. |
| `CULTIVARS_IPFS_API` | `http://127.0.0.1:5001` | The kubo HTTP API endpoint `pin_observation_to_ipfs` talks to. |

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

## Troubleshooting

### "Claude Code says no MCP server is loaded"

Usually one of:
- You're not in the project directory. `cd` to the cloned repo and re-launch `claude`.
- You ran `git clone` but haven't run `uv sync` yet. The MCP can't start without dependencies installed.
- Permission prompt: the first time Claude Code sees `.mcp.json`, it asks before enabling the server. Approve the prompt.
- Check `claude` is actually picking up `.mcp.json` — `claude /mcp` from inside Claude Code lists registered MCP servers; `cultivars` should appear.

### "Claude Desktop doesn't see the MCP after I edit config"

Restart Claude Desktop completely (`Cmd-Q` / `Alt-F4` then relaunch — `Cmd-R` reload isn't enough). The MCP config is read at process start.

### "Ensembl returned 503 / timed out"

Ensembl has scheduled-maintenance windows (Tuesdays for some indices) and occasional REST backend load spikes. The tool's built-in retry helper handles 429 + 503 transients with `Retry-After` backoff. If it's persistent:
- Check https://rest.ensembl.org/info/ping for service status
- Wait a few minutes and retry
- The retry budget is 3 attempts per request — after that the tool surfaces the error

### "EuropePMC returned 503"

Same pattern as Ensembl — transient infrastructure load. The tool now has Retry-After backoff (added in the same docs round). Wait and retry. We observed this in real-time during the integration testing; the second attempt succeeded.

### "STRING-db returned 400"

STRING returns 400 when it can't map your identifier to a protein in the requested species. Common cases:
- The gene symbol uses an alias STRING doesn't have. Try a stable ID instead.
- The species (NCBI taxon ID) doesn't have that protein in STRING's database. STRING covers ~16,000 species but coverage varies — Cannabis is supported (taxon 3483), but not every cannabis protein is mapped.
- Try a different identifier form: STRING accepts symbol, UniProt ID, or its own `species.proteinId` form (e.g., `3702.AT2G18790` for Arabidopsis PHYB).

### "Cannabis lookup returns empty"

Cannabis sativa **is not in Ensembl Plants**. This is documented and intentional — every tool with a `species` argument checks for `cannabis_sativa` and returns a structured fallback pointing at:
- `lookup_kannapedia_strain` for strain-level live data
- `lookup_uniprot_entry` for cannabis protein curation
- `find_trait_genes(trait="cannabinoid_biosynthesis"...)` for the literature-handle atlas

If you want a specific cannabis gene by symbol (e.g., "THCAS"), use `lookup_uniprot_entry(uniprot_id="Q8GTB6")` directly — UniProt has it curated.

### "Kannapedia strain lookup says 'Strain not found'"

Verify the RSP ID. Kannapedia IDs are numeric and range from ~rsp1 to current. Browse https://www.kannapedia.net/strains to discover IDs. The tool accepts both forms: `rsp13536` or `13536`.

### "find_trait_genes returns 'trait not in atlas'"

The atlas is a curated map, not exhaustive. If your trait isn't there:
- Call `list_trait_categories` to see what's available
- The tool does loose matching — `"drought"` → `drought_tolerance`, `"hemp"` → matches multiple — so try a shorter or longer form
- If the trait is truly absent, find the seminal gene from primary literature and use `lookup_gene` directly. The atlas adds categories in response to community contributions (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

### "An atlas gene's `evidence` field is `null`"

Two reasons:
- The gene is a **literature handle** — known from primary literature but not symbol-indexed in Ensembl (barley HVA1, sorghum SbMATE, rice SK1/SK2). The atlas marks these with a `note` field. Use the cited paper as the evidence trail.
- The atlas evidence file (`atlas_evidence.json`) is stale relative to a newly-added atlas gene. The `test_atlas_evidence_drift_warning` pytest catches this. Regenerate via `python evals/atlas_audit.py`.

### "Hexaploid wheat (Triticum aestivum) returns multiple orthologs for one gene"

Bread wheat is hexaploid (AABBDD subgenomes). A gene like VRN-A1 has homoeologs at VRN-A1, VRN-B1, and VRN-D1. Ensembl Compara returns all three when you query "TaVRN1" or similar. **This is correct, not a bug.** Look at the `taxonomy_level` field — homoeolog matches come at deep nodes (Triticeae) while one2one orthologs come at shallow nodes.

### "Variant search returns empty for my species"

Variation coverage is wildly uneven across plant species:
- **Arabidopsis** (1001 Genomes) → ~12M variants
- **Rice** (3K Rice Genomes) → millions
- **Tomato, grape, wheat, maize** → partial
- **Most other crops** → no variation database; you get `[]`

The tool surfaces this in the `species_quality` field of the response — `"tier": "gene_models_only"` means there's no curated variation database. This is a data gap, not a tool failure.

### "PubMed search returns ancient-only results"

EuropePMC results are ranked by relevance by default, which can surface older highly-cited papers. To filter to recent literature:
- Add the year explicitly to the query: `"DREB1A drought 2024 OR 2025 OR 2026"`
- Use the `cited_by_count` field in results to prioritize impact (with the caveat that recent papers haven't had time to accumulate citations)
- For specific date filtering, see Europe PMC's [advanced search syntax](https://europepmc.org/Help#search-tips) — pass query directly

### "Concurrent calls are hitting rate limits"

The internal `_get_with_retry` helper handles 429s automatically. If you're orchestrating many parallel calls externally (more than the tool already does internally):
- `translate_trait_to_species` already caps internal concurrency at 6 workers
- `compare_cannabis_strains` caps at 5
- If you're seeing rate limits, reduce concurrency at the agent level

### "My test passes locally but fails in CI"

Check Python version compatibility — the CI matrix runs 3.10 / 3.11 / 3.12. Some `httpx.MockTransport` behaviors differ slightly between Python minor versions.

### "submit_phenotype_observation didn't open a pull request"

By design. The tool prepares the artifact (writes the YAML, returns a content
hash and PR instructions) but **never uses GitHub credentials at runtime** — you
commit the file under `phenotypes/` and open the PR yourself. This keeps review
and attribution in human hands. Set `CULTIVARS_LEDGER_DIR` to a git working copy
to make that step a one-liner.

### "submit_phenotype_observation rejected my trait_category / species"

`trait_category` must match an atlas category (`list_trait_categories`) or an
organellar trait (`cms`, `plastid_herbicide_resistance`, `plastid_photosynthesis`).
`species` must be a recognized Ensembl species **or** an orphan-crop species named
in the atlas (e.g. `eragrostis_tef`). A genuine typo is rejected with the list of
errors and nothing is written — fix and resubmit.

### "verify_observation_integrity says verified: false"

Three honest causes, each reported distinctly: (1) the observation carries no
signature (unsigned data is still valid — it just lacks attribution proof);
(2) the key/signature couldn't be decoded (use `ed25519:<hex>` or base64);
(3) the signature doesn't match — the observation was altered after signing, or
the wrong public key was supplied. Re-derive the `canonical_form` from
`submit_phenotype_observation` and sign exactly those UTF-8 bytes.

### "pin_observation_to_ipfs returns a fallback, not a CID"

No kubo node was reachable. Install IPFS (https://docs.ipfs.tech/install/), run
`ipfs daemon`, or point `CULTIVARS_IPFS_API` at a reachable gateway, then retry.
The observation remains valid without a CID — pinning is an enhancement.

### "resolve_accession returns match_count: 0"

GRIN-Global's public REST schema varies by deployment, and not every folk name
maps cleanly. A zero-match result with the manual-search fallback link is a
legitimate honest answer, not a bug. Try a scientific name or a broader query, or
search directly at https://npgsweb.ars-grin.gov/gringlobal/search.

### "estimate_gwas_power gave a huge required-N"

That's usually correct: the Bonferroni correction over millions of SNPs makes the
genome-wide threshold very strict. The number is order-of-magnitude guidance for
an idealized additive common-variant model. Real plant GWAS uses mixed models that
correct for kinship/population structure, which **raises** required N further — so
treat the figure as a floor, and recruit collaborators.

### "query_organellar_variants — is `Mt`/`Pt` an error?"

No. `Mt` (mitochondrion) and `Pt` (plastid) are first-class Ensembl Plants
chromosome identifiers. Empty variant scans on them are a data gap (organellar
variation catalogs are sparse), not a tool error. The curated organellar atlas
(`trait="cms"` etc.) gives context even when the variant scan is empty.

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
A: Yes. Edit `TRAIT_ATLAS` in `server.py`, then regenerate `atlas_evidence.json` via `evals/atlas_audit.py`. PRs welcome — we add trait categories in response to grower-scientist requests. For underrepresented crops, see the `# ORPHAN CROPS BOUNTY` section of [CONTRIBUTING.md](../CONTRIBUTING.md) and `list_orphan_crop_requests`.

**Q: What's the license?**
A: Two licenses, deliberately. The **code** is Apache-2.0 ([LICENSE](../LICENSE)). The **community-contributed data** in `phenotypes/` — and any derivative database — is ODbL-1.0 ([DATA_LICENSE.md](../DATA_LICENSE.md)), an open-data *copyleft* license (the same model OpenStreetMap uses). A permissive license on data would let anyone enclose the commons in a proprietary database; ODbL's share-alike requirement keeps it open.

**Q: Is there a token, coin, or wallet involved in contributing?**
A: No — and there deliberately never will be. Attribution uses Ed25519 signatures, which build a verifiable, pseudonymous *scientific* CV tied to a keypair. There is no cryptocurrency, utility token, or on-chain storage; financializing contributions distorts incentives and adds regulatory overhead incompatible with nonprofit operations.

**Q: Where do my observations go? Do they leave my machine?**
A: `submit_phenotype_observation` writes a YAML to a local directory (`CULTIVARS_LEDGER_DIR`, default `./phenotypes/`) — nothing leaves your machine until *you* open a pull request. You can run a fully private local ledger and decide later what to share. IPFS pinning (opt-in, via `pin_observation_to_ipfs`) is the only step that publishes content, and only if you run it.

**Q: How accurate is `estimate_gwas_power`?**
A: It's transparent order-of-magnitude guidance, not a formal power analysis. It assumes unrelated individuals, a single common causal variant, a balanced binary phenotype, and no population structure, with a Bonferroni threshold over an approximate genome-wide SNP count. The response surfaces the formula and every assumption. Real plant GWAS needs mixed-model kinship/structure correction, which raises the required sample size.

---

## Glossary

| Term | Meaning |
|---|---|
| **BT/BD allele** | The cannabis chromosome-6 locus where BT (functional THCAS) and BD (functional CBDAS) alleles determine chemotype Type I/II/III |
| **Chemotype I/II/III** | Cannabis classification: Type I = THC-dominant, Type II = balanced, Type III = CBD-dominant (hemp-compliant) |
| **CMS** | Cytoplasmic Male Sterility — maternally-inherited mitochondrial trait used to produce hybrid seed; queried via `query_organellar_variants` |
| **Compara** | Ensembl's protein-tree-based comparative genomics resource — powers `get_orthologs` |
| **CS10** | Cannabis sativa reference genome v10 (Grassa et al. 2021), NCBI GCF_900626175.2 |
| **Ed25519** | The elliptic-curve signature scheme used for observation attribution — a verifiable, pseudonymous scientific credential, not a financial instrument |
| **Fst** | Wright's fixation index — a 0–1 measure of allele-frequency differentiation between subpopulations (e.g. Indica vs Japonica rice); surfaced by `population_context=True` |
| **GRIN-Global** | USDA ARS open germplasm/accession system (600,000+ holdings); `resolve_accession` bridges folk seed names to its formal IDs |
| **GWAS power** | The probability a study detects a true trait–locus association at a given sample size; `estimate_gwas_power` reports the sample size needed |
| **GO** | Gene Ontology — controlled vocabulary for gene function (process / function / component) |
| **GO evidence code** | Tag on a GO annotation indicating how it was derived (EXP/IDA = experimentally validated; IEA/ISS = inferred) |
| **HGVS** | Human Genome Variation Society nomenclature for variants (also used in plants) |
| **High_curated** | Atlas evidence tier — gene has a UniProt/SWISSPROT manually-curated entry |
| **IPFS** | InterPlanetary File System — content-addressed, decentralized storage; `pin_observation_to_ipfs` returns a permanent CID for an observation |
| **KNF** | Korean Natural Farming — natural-farming methodology emphasizing indigenous microorganisms (IMO) |
| **Kannapedia** | Medicinal Genomics's public cannabis-strain database |
| **Ledger** | The community phenotype store under `phenotypes/` (ODbL-1.0); written by `submit_phenotype_observation`, read by `query_community_phenotypes` |
| **NAM** | Nested Association Mapping — 26-line maize founder panel (McMullen 2009) |
| **ODbL** | Open Database License — the open-data *copyleft* license (share-alike) covering ledger data; same model as OpenStreetMap |
| **Organellar (Mt/Pt)** | The mitochondrial (`Mt`) and plastid/chloroplast (`Pt`) genomes — valid Ensembl chromosomes, maternally inherited |
| **Orphan crop** | A regionally-vital crop underrepresented in funded genomics (teff, fonio, cowpea, finger millet, amaranth…); see `list_orphan_crop_requests` |
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
