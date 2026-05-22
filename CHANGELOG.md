# Changelog

All notable changes to the Cultivars MCP server. Format adapted from [Keep a Changelog](https://keepachangelog.com/) — augmented with the metrics + reasoning Copyleft Cultivars work tends to surface.

The unreleased section reflects work on the `refactor/plant-genomics-cultivars` branch (this PR).

## [Unreleased] — fork from EVEE MCP for plant genomics

### Tool count: 6 (upstream) → **19**
### Atlas: 0 → **30 categories, 123 genes, 73% UniProt-curated**
### Tests: 0 (upstream had none) → **89 unit + 225+ live integration checks**
### External APIs integrated: 1 (Goodfire EVEE) → **5** (Ensembl + UniProt + EuropePMC + STRING + Kannapedia)

---

### Added — Docs round (commit `58f1447`+)

- `LICENSE` (Apache 2.0, copyright Copyleft Cultivars Nonprofit + Caleb DeLeeuw)
- `NOTICE` documenting the upstream EVEE fork lineage + data-source attributions
- `CHANGELOG.md` (this file)
- `CONTRIBUTING.md` — how to add trait categories, regenerate atlas evidence, add species to NCBI taxon table
- `docs/USER_GUIDE.md` — comprehensive ~900-line reference with tool-by-tool walkthrough, 6 workflow recipes, FAQ, glossary
- `docs/PATREON_INTRO.md` — accessible intro post for Copyleft Cultivars Patreon members in CC voice
- Table of contents added to README
- Troubleshooting section + persona-organized workflow recipes added to USER_GUIDE
- SKILL.md gains tool-routing decision table + Cannabis-specific + Maize-specific routing sections
- `test_atlas_evidence_drift_warning` regression test — flags when atlas grows new `ensembl_id` entries without re-running the audit
- `_get_with_retry` (429/503 + Retry-After backoff) now applies to **all 5 external APIs**, not just Ensembl

### Added — Living-document databases round (commit `c1207fe`)

- **`lookup_uniprot_entry`** — direct UniProt REST query. Returns manually-curated function statement, catalytic activity + EC number, cofactors, GO terms with evidence codes (EXP / IDA / IPI / IMP / IGI vs IEA / ISS), PubMed citations. **Works for Cannabis genes** (THCAS Q8GTB6, CBDAS A6P6V9) which are not in Ensembl Plants. Live-verified: Q8GTB6 returns "Tetrahydrocannabinolic acid synthase", EC 1.21.3.7, FAD cofactor, 7 PubMed citations.
- **`search_pubmed_for_gene`** — Europe PMC REST literature search. Returns title, authors, year, DOI, PMID, open-access flag, citation count. The "living document" — returned 2025 + 2026 papers in DREB1A test (newer than training data).
- **`get_string_interactions`** — STRING-db protein-protein interaction network. Per-channel evidence scores (textmining / experimental / database / coexpression / neighborhood / fusion / phylogenetic). **Covers Cannabis sativa** (taxon 3483). Live-verified: SOS1 returns CIPK24 (canonical SOS2 partner) at score 0.999.
- **`compare_cannabis_strains`** — composed tool batching 2–5 Kannapedia strain lookups concurrently. Returns chemotype distribution, rarity distribution, and "genes flagged on multiple strain pages" overlap analysis.
- New per-API client-factory helpers (`_uniprot_client`, `_europepmc_client`, `_string_client`) for test injection.

### Added — Cannabis/Hemp/Corn round (commit `69ff5eb`)

- **`lookup_kannapedia_strain`** — LIVE fetch from Medicinal Genomics Kannapedia by RSP ID. Parses strain name, chemotype (Plant Type I/II/III), plant sex, Y-ratio, heterozygosity, rarity, grower, 12+ cannabis genes flagged on the page, S3-hosted VCF/FASTQ/BAM URLs, and up to 20 phylogenetically-related strain IDs. Live-verified against rsp13536 (Type I) + rsp13534 (Type III hemp).
- **`cannabis_strain_search_urls`** — search-URL constructors for Kannapedia, Leafly, SeedFinder, NCBI Taxonomy, EuropePMC (no HTTP, pure construction).
- **`list_maize_nam_founders(subpopulation)`** — the 26-line maize NAM founder panel from McMullen 2009 (PMID 19661427) + Hufford 2021 (PMID 34353948). Stiff Stalk, Non-Stiff Stalk, Tropical/Subtropical (CIMMYT CML + Thai Ki + IITA Tzi), Popcorn, Sweet Corn.
- 9 new trait atlas categories: `cannabinoid_biosynthesis` (7-enzyme pathway), `cannabis_terpene_profile` (CsTPS family), `hemp_compliance` (BT/BD allele system), `cannabis_sex_and_photoperiod` (MADC2, CsAuto, CsELF3), `cannabis_disease_resistance` (PMR loci, MLO orthologs), `general_lepidopteran_pest_resistance`, `maize_quality_protein` (Opaque-2), `maize_disease_resistance` (Ht1, Htn1, Rcg1), `maize_pest_resistance` (Mir1-CP).
- Cannabis fallback (`COMMUNITY_RESOURCES['cannabis_sativa']`) enriched to point at the new tools.

### Added — Atlas veracity backbone (commit `b63cacc`)

- **`lookup_gene_evidence`** — pulls Ensembl `/xrefs/id?all_levels=1`. Groups cross-references by database: UniProt/SWISSPROT (gold-standard manual curation) vs SPTREMBL (auto-annotated), GO term count, Plant Reactome pathways, PDB structures, TAIR/RAP-DB/MaizeGDB authoritative refs, BioGRID/STRING. Computes evidence_tier: `high_curated` / `moderate_auto_annotated` / `low_some_annotation` / `minimal`.
- `atlas_evidence.json` — cached evidence audit results, committed to the repo. Populated by `evals/atlas_audit.py`. Loaded at module init; `find_trait_genes` enriches each gene with the cached tier.
- 10 canonical atlas entries gained `primary_ref` (PubMed-cited seminal characterization paper) + `evidence_level` (knockout_phenotype / transgenic_complementation / qtl_mapped) fields: DREB1A, SOS1/2/3, SUB1A, NRT1.1B, PSTOL1, SD1, TB1, ALMT1, SbMATE, BADH2.
- Symbol-resolved evidence fallback: even atlas genes without explicit `ensembl_id` (e.g. SOS1) get evidence enrichment via the symbol→ID secondary index.

### Veracity audit results (real measured numbers, 93 atlas genes)

- 73.1% UniProt/SWISSPROT manually curated
- 24.7% in Plant Reactome pathways
- 23.7% with PDB-solved 3D structures
- Mean 11.0 / median 8 GO terms per gene
- 10.8% unresolvable — all are pre-flagged literature handles with citations

### Added — Trait atlas fixes + composed tool + species quality (commit `75f4773`)

- **M1: Trait atlas discoverability** rose from 66.2% → 84.9% (+18.7 pp) after adding `ensembl_id` fields to 24 entries, switching rhizobial_nodulation genes from Lotus japonicus (not in Ensembl Plants) to Medicago truncatula (in Ensembl Plants), and fixing symbol-vs-display-name mismatches.
- **`translate_trait_to_species`** — composed tool with `ThreadPoolExecutor(max_workers=6)` concurrency. M2: workflow latency dropped 11.66s → 3.13s (3.7× speedup). M3: tool calls dropped 7 → 1.
- **`_SPECIES_QUALITY` table** — 4 tiers (`richly_covered` / `moderately_covered` / `gene_models_only` / `not_in_ensembl_plants`) surfaced inside response shapes for `search_variants_in_region`, `get_variant`, `find_trait_genes`, `translate_trait_to_species`.
- 3 new atlas categories: `cell_wall_biosynthesis`, `grain_quality` (Wx/Waxy, BADH2/fgr basmati fragrance), `photosynthesis_c4` (PEPC, NADP-ME, PPDK, RBCS1A).

### Added — Test infrastructure + retry helper + CI + FORK_NOTES (commit `3e0583f`)

- `tests/test_server.py` — pytest suite using `httpx.MockTransport` (no live network). 36 → expanded across rounds → 89 tests. Runs in ~1.2s.
- `_get_with_retry` helper — Retry-After-aware backoff on 429/503 status codes. Initially on Ensembl only; expanded to all 5 APIs in docs round.
- `.github/workflows/ci.yml` — GitHub Actions matrix on Python 3.10 / 3.11 / 3.12.
- `_CLIENT_FACTORY` test seam in `server.py` enables `httpx.MockTransport` injection for unit tests.
- **`FORK_NOTES.md`** — memo to the upstream EVEE Claude Opus author documenting what carried over, what changed, live-API data points (PHYB → AT2G18790 → 88 GO terms → 4 PDB structures), the `/lookup/id` 400-vs-404 gotcha, hexaploid wheat homoeologs, `Mt`/`Pt` chromosomes, ortholog one2one vs many2many at deep taxonomy levels, Cannabis sativa data-gap rationale. 3 postscripts add improvement deltas, veracity audit, and integration testing.
- `pyproject.toml` — declared `[project.optional-dependencies] dev = ["pytest>=8.0"]`, `[tool.pytest.ini_options]` config.

### Refactor round (commit `0e74ece`) — initial fork rebuild

- MCP server name `evee` → `cultivars`
- Backend: Goodfire EVEE API (human ClinVar) → Ensembl Plants REST API (~80 plant species)
- Coordinate convention: 0-based half-open → 1-based fully-closed (matches VCF/GFF, what plant biologists actually use)
- 8 initial tools: `list_plant_species`, `lookup_gene`, `search_variants_in_region`, `get_variant`, `predict_variant_effect`, `compare_variants`, `get_orthologs`, `get_sequence`
- 18 initial trait atlas categories
- `COMMUNITY_RESOURCES` table for Cannabis (not in Ensembl Plants) with structured fallback pointing at NCBI CS10 + Cannabis Genome DB

### Removed (vs upstream EVEE)

- `wait_for_variant_analysis` — Ensembl REST is synchronous; no equivalent of EVEE's on-demand `/analysis` endpoint
- `get_variant_disruptions` — folded into `predict_variant_effect`
- `get_variant_annotations` — no annotation-probe array in Ensembl
- The `pathogenicity_score`, `interpretation`, `evee_url` fields — clinical-only concepts that don't transfer to plant genomics

---

## Process metrics (added in docs round)

- Total commits on fork branch: 8
- Total live verification checks documented: ~225 across unit / integration / consistency / robustness layers
- Total docs added: README (rewrite), USER_GUIDE.md (new ~900 lines), PATREON_INTRO.md (new), FORK_NOTES.md (new with 3 postscripts), CONTRIBUTING.md (new), SKILL.md (significant additions), CHANGELOG.md (new)
