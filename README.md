# Cultivars MCP — Plant Genomics for the Commons

> **Tooling for grower-scientists, heritage breeders, and natural-farming researchers** working with the open plant-genomics commons. Live integration with **5 public databases**: Ensembl Plants, UniProt, Europe PMC, STRING-db, and Medicinal Genomics Kannapedia.

Part of the [Copyleft Cultivars](https://github.com/CopyleftCultivars) ecosystem alongside [TinyLLamaFarmer](https://github.com/CopyleftCultivars/TinyLLamaFarmer) (offline natural-farming AI) and [gemma4-natural-farming](https://huggingface.co/CopyleftCultivars/gemma4-natural-farming-gguf) (open-weight KNF/JADAM model).

| | |
|---|---|
| 👥 **Audience guide** (Patreon members, non-technical) | [docs/PATREON_INTRO.md](docs/PATREON_INTRO.md) |
| 📖 **User guide** (full reference + recipes) | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| 🔧 **Contributing** (add traits, regenerate audits) | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 📜 **License** (Apache 2.0) | [LICENSE](LICENSE) |
| 🪞 **Lineage from upstream fork** | [FORK_NOTES.md](FORK_NOTES.md) |
| 🧾 **Changelog** | [CHANGELOG.md](CHANGELOG.md) |

## Table of contents

- [What it does](#what-it-does)
- [The trait atlas (30 categories, 123 genes, 73% UniProt-curated)](#the-trait-atlas-30-categories-123-genes-73-uniprot-curated)
- [Honest framings](#honest-framings-per-copyleft-cultivars-mission)
- [Veracity verification](#veracity-verification)
- [Testing & CI](#testing--ci)
- [Installation](#usage)
- [Example workflows](#example-workflows-see-user_guidemd-for-full-recipes)
- [Skill (for Claude Code agents)](#skill)
- [Data sources](#data-sources)
- [License & lineage](#license--lineage)

---

## What it does

28 MCP tools across 5 live databases plus a 35-category curated trait atlas — **73% of the core atlas is verified against manually-curated UniProt entries with PubMed citations**. Beyond read-only genomics, a **community-science layer** adds a phenotype-observation write path, Ed25519 attribution, a GWAS power estimator, GRIN accession resolution, organellar-genome queries, and an offline-bridge export (see the [Community Science Layer](#community-science-layer)).

### Plant gene + variant tools (Ensembl Plants, ~80 species)

| Tool | Use |
|---|---|
| `list_plant_species` | Discover the Ensembl `name` for any plant species (rice, maize, cassava, etc.) |
| `lookup_gene` | Resolve a gene by symbol (`PHYB`, `DREB1A`) or stable ID (`AT2G18790`) |
| `search_variants_in_region` | Known variants in a 1-based genomic region (1001 Genomes / 3K Rice Genomes coverage) |
| `get_variant` | Fetch a single known variant by Ensembl stable ID |
| `predict_variant_effect` | Run VEP on a novel variant or a known ID |
| `compare_variants` | Side-by-side summary of 2–10 known variants |
| `get_orthologs` | Cross-species translation via Ensembl Compara |
| `get_sequence` | Fetch genomic / cDNA / CDS / protein sequence |

### Trait atlas + composed-workflow tools

| Tool | Use |
|---|---|
| `list_trait_categories` | Discover the 30 curated trait categories |
| `find_trait_genes` | Canonical genes for a trait (drought, salt, mycorrhiza, etc.) with evidence tier + UniProt cross-ref + primary literature |
| `translate_trait_to_species` | **Composed shortcut** — trait + target species → concurrent ortholog calls; one call replaces ~7 |

### Veracity / living-document tools

| Tool | Source | Use |
|---|---|---|
| `lookup_gene_evidence` | Ensembl `/xrefs/id` | Full cross-reference chain: UniProt curation tier, GO term count, Plant Reactome, PDB, BioGRID, STRING, TAIR/RAP-DB/MaizeGDB |
| `lookup_uniprot_entry` | UniProt REST | Manually-curated function statement, catalytic activity + EC number, cofactors, GO terms with evidence codes, PubMed citations. **Works for Cannabis genes** (THCAS Q8GTB6, CBDAS A6P6V9) which aren't in Ensembl Plants. |
| `search_pubmed_for_gene` | Europe PMC REST | Plant-gene literature search — returns 2025/2026 papers; the "living document" |
| `get_string_interactions` | STRING-db REST | Protein-protein interaction network with per-channel evidence (textmining vs experimental vs database). **Covers Cannabis sativa** (taxon 3483). |

### Cannabis-specific tools (Kannapedia + helpers)

| Tool | Use |
|---|---|
| `lookup_kannapedia_strain` | **LIVE fetch** from Medicinal Genomics Kannapedia by RSP ID. Returns chemotype (Type I/II/III), plant sex, Y-ratio, heterozygosity, rarity, grower, genes flagged on page, S3-hosted VCF/FASTQ/BAM URLs, related strain IDs. |
| `compare_cannabis_strains` | Concurrent batch comparison of 2–5 strains; surfaces chemotype distribution + genes flagged on multiple strain pages |
| `cannabis_strain_search_urls` | URL constructors for Kannapedia, Leafly, SeedFinder, NCBI Taxonomy, EuropePMC (no HTTP) |

### Maize tools

| Tool | Use |
|---|---|
| `list_maize_nam_founders` | The 27-line maize NAM founder panel (McMullen 2009 + Hufford 2021) — Stiff Stalk, Non-Stiff Stalk, Tropical/Subtropical (CIMMYT + Thai + IITA), Popcorn, Sweet Corn |

### Community Science Layer

The write path and participatory-science tools. **Ledger data is licensed
[ODbL-1.0](DATA_LICENSE.md)** (open-data copyleft), distinct from the Apache-2.0
code license — so the commons stays open. Attribution is via Ed25519 signatures,
**not** any token or cryptocurrency.

| Tool | Use |
|---|---|
| `submit_phenotype_observation` | Record a field observation as a schema-v1.0 YAML in the ledger; returns a canonical form to sign + PR instructions (no GitHub creds needed) |
| `query_community_phenotypes` | Aggregate the ledger: count, measurement distribution, accessions, signed-observation count |
| `estimate_gwas_power` | "Can my village's 12 varieties detect this locus?" — Bonferroni power calc, pulls live count from the ledger |
| `verify_observation_integrity` | Verify a detached Ed25519 signature over the canonical observation — pseudonymous scientific attribution |
| `pin_observation_to_ipfs` | Content-address an observation (+ optional VCF) via a local kubo node; graceful fallback if none |
| `resolve_accession` | Folk seed name → USDA GRIN-Global accession → Ensembl species string |
| `query_organellar_variants` | First-class Mt/Pt genome queries + curated organellar atlas (CMS, plastid herbicide resistance, photosynthesis) |
| `export_offline_snapshot` | Package a trait's genomics into a portable JSON for offline TinyLLamaFarmer use |
| `list_orphan_crop_requests` | The `WANTED_TRAITS.yaml` orphan-crop contribution bounty list |

`get_variant` and `search_variants_in_region` also gain an optional
`population_context=True` for per-population allele frequencies + Indica/Japonica
Fst on richly-covered species.

## The trait atlas (30 categories, 123 genes, 73% UniProt-curated)

| Category | Representative genes |
|---|---|
| **Abiotic stress** | drought_tolerance (DREB1A/DREB2A/OST1), salt_tolerance (SOS1/2/3, OsHKT1;5), cold_tolerance (CBF1/2, ICE1), heat_tolerance (HsfA1a/A2), submergence_tolerance (SUB1A, SK1/2), aluminum_tolerance (ALMT1, SbMATE) |
| **Nutrients** | nitrogen_use_efficiency (NRT1.1/2.1, NRT1.1B-indica, AMT1;1), phosphorus_uptake (PHT1;1, PHO2, PHR1, PSTOL1-Kasalath), iron_uptake (IRT1, FRO2, FIT) |
| **Symbiosis** | mycorrhizal_symbiosis (SYMRK, CCaMK, DMI1, PT4, RAM1), rhizobial_nodulation (NFP, LYK3, NIN, ERN1) |
| **Architecture / development** | root_architecture (PIN2, ARF7, LBD16, RHD6, DRO1), flowering_photoperiod (FT, CO, FLC, Vrn-A1, Hd1), plant_height_dwarfing (SD1 IR8, Rht-B1, D8), tiller_branching (TB1, MAX2, D14, MOC1) |
| **Defense** | defense_jasmonate (COI1, MYC2, LOX2, JAR1), terpene_biosynthesis (TPS21, TPS10, STO1, OsKS4), glucosinolate_biosynthesis (MYB28/29/51, CYP79B2), general_lepidopteran_pest_resistance (Mir1, PI-II, Mi-1.2) |
| **Quality** | grain_quality (Wx/Waxy, BADH2/fgr, GBSSII, GLU-A1), cell_wall_biosynthesis (CESA1/4, PAL1, CCR1, CAD5), photosynthesis_c4 (PEPC, NADP-ME, PPDK, RBCS1A) |
| **Cannabis-specific** *(literature handles)* | cannabinoid_biosynthesis (full 7-enzyme pathway), cannabis_terpene_profile (CsTPS family), hemp_compliance (BT/BD), cannabis_sex_and_photoperiod (MADC2, CsAuto, CsELF3), cannabis_disease_resistance (PMR loci, MLO orthologs) |
| **Maize-specific** | maize_quality_protein (Opaque-2), maize_disease_resistance (Ht1, Htn1, Rcg1), maize_pest_resistance (Mir1-CP) |
| **Orphan crops** *(literature handles)* | teff_drought_tolerance (EtDREB/EtNAC), cowpea_heat_tolerance (VuHSP70, VuHSFA2), finger_millet_calcium_accumulation (EcCAX1), pigeon_pea_salinity_tolerance (CcSOS1, CcNHX1), amaranth_c4_photosynthesis (AhPEPC, AhNADP-ME) |

The **30-category / 123-gene core** above is the UniProt-verified set (73%
high-curated). The 5 **orphan-crop** categories are a newer extension — most of
those species aren't in Ensembl Plants, so they're literature handles flagged
with `note` + `evidence_level`, not symbol-resolvable. See
[`WANTED_TRAITS.yaml`](WANTED_TRAITS.yaml) and the `# ORPHAN CROPS BOUNTY`
section of [CONTRIBUTING.md](CONTRIBUTING.md) to extend them.

10 canonical entries carry `primary_ref` fields with PubMed citations (DREB1A → Liu 1998 PMID 9707537; SOS1 → Shi 2000 PMID 10823923; SUB1A → Xu 2006 PMID 16900200; PSTOL1 → Gamuyao 2012 PMID 22914168; SD1 → Sasaki 2002 PMID 11961545; TB1 → Doebley 1997 PMID 9087409; ALMT1 → Sasaki 2004 PMID 14871304; SbMATE → Magalhães 2007 PMID 17721535; BADH2 → Bradbury 2005 PMID 17173626; SUB1A → Xu 2006 PMID 16900200) plus `evidence_level` taxonomy (knockout_phenotype / transgenic_complementation / qtl_mapped / etc.).

## Honest framings (per Copyleft Cultivars mission)

- **This MCP needs internet.** It calls live REST APIs. That contradicts the org's offline-first ethos — the offline tools are TinyLLamaFarmer and gemma4-natural-farming. Cultivars is the desk-side companion.
- **"Genomics is one lens.** Indigenous knowledge, farmer observation, on-farm trials, and natural-farming holism remain the other lenses. This tool does not replace them." — stated in code (`server.py` docstring + FastMCP `instructions=`) and in the skill.
- **Cannabis sativa is not in Ensembl Plants** (federal-research-funding gap). Every Cannabis query returns a structured fallback pointing to Kannapedia + NCBI CS10 + Cannabis Genome DB + the 5 cannabis-specific trait atlas categories — instead of a confusing 404.
- **Variation coverage is wildly uneven by species.** Arabidopsis (1001 Genomes) and rice (3K Rice Genomes) are richly covered. Most crops have gene models but no curated variation database. The tool surfaces this as a `species_quality` field inside response shapes (`richly_covered` / `moderately_covered` / `gene_models_only` / `not_in_ensembl_plants`).
- **VEP ≠ foundation model.** Ensembl VEP is classical, rule-based, consequence-term-driven — not embedding-based pathogenicity prediction. Treat consequence terms as descriptive.

## Veracity verification

Beyond unit tests, the atlas was audited against live Ensembl `/xrefs/id` for every gene:

| Veracity signal | Count | % |
|---|---|---|
| **UniProt/SWISSPROT manually-curated** | 68/93 | **73.1%** |
| Plant Reactome pathway membership | 23/93 | 24.7% |
| PDB-solved 3D structure | 22/93 | 23.7% |
| Mean GO terms per gene | 11.0 | — |

Cross-source consistency check: for each high-curated atlas entry, fetched UniProt directly and verified organism + function + entry existence. **Result: 68/68 consistent. 100.0% rate** across `JAR1` (32 PubMed cites), `RD29A` (30), `OST1` (28), `MYC2` (28), `GAI` (27), `COR15A` (26), `CESA1` (24), `NRT1.1` (23), and the rest.

Live workflow integration tests: 5/6 multi-tool grower-scientist workflows complete end-to-end against real APIs in ~15s total wall-clock for 13 tool calls.

Robustness probing: **35/35 adversarial input probes** (empty strings, 10K-char inputs, CJK, emoji, SQL-injection, malformed IDs, out-of-range numerics, both-arg-conflict cases) return structured responses with **zero uncaught exceptions**.

Full details in [FORK_NOTES.md](FORK_NOTES.md). Eval scripts in `evals/` (gitignored — regeneratable).

## Testing & CI

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

**88 unit tests** using `httpx.MockTransport` (no live network), run in ~1.5s. GitHub Actions runs on Python 3.10 / 3.11 / 3.12 on every PR.

## Usage

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/CopyleftCultivars/evee-mcp-fork-for-plants.git
cd evee-mcp-fork-for-plants
uv sync
```

### Claude Code

The repo ships a `.mcp.json`; opening the directory triggers the permission prompt:

```bash
claude
```

### Claude Desktop

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

## Example workflows (see [USER_GUIDE.md](docs/USER_GUIDE.md) for full recipes)

**"What drought-tolerance genes from Arabidopsis literature have orthologs in my sorghum landrace?"**
```
translate_trait_to_species(trait="drought_tolerance", target_species="sorghum_bicolor")
# 1 call. Returns 6 canonical Arabidopsis genes → 4 sorghum orthologs in ~2 seconds.
# DREB1A → SORBI_3002G269100 + 6 paralogs; DREB2A → SORBI_3009G101400; etc.
```

**"Is my hemp cultivar (rsp13534) safely Type III?"**
```
lookup_kannapedia_strain(rsp_id="13534")
# Live fetch confirms Type III (CBD-dominant); links to S3-hosted VCF for variant verification
find_trait_genes(trait="hemp_compliance")
# Returns the BT/BD allele system + Weiblen 2015 PMID 26242869
```

**"Compare these 3 cannabis strains I'm thinking of breeding from"**
```
compare_cannabis_strains(rsp_ids=["13536", "13534", "10837"])
# 1 call. Returns chemotype distribution + 12 genes flagged on multiple strain pages
# (THCAS, CBDAS, CBCAS, ELF3, FAD2, PHL, PKSG variants — the breeding-relevant overlap)
```

**"What's the latest 2026 literature on PSTOL1 and rice phosphorus uptake?"**
```
search_pubmed_for_gene(query="PSTOL1 rice Kasalath phosphorus", page_size=5)
# Returns the freshest papers from Europe PMC — newer than my training data.
```

**"What does STRING-db say about SOS1 interactors?"**
```
get_string_interactions(protein_id="SOS1", species="arabidopsis_thaliana")
# 10 interactions. Top partner: CIPK24 (= SOS2 — the textbook salt-pathway interactor) at score 0.999.
```

## Skill

A Claude Code skill lives at `.claude/skills/cultivars/SKILL.md`. Agents that load it get triggering criteria tuned to grower-scientist questions, routing guidance for all 28 tools, and explicit caveats about which plant genomes are open vs. paywalled.

## Data sources

- **[Ensembl Plants](https://plants.ensembl.org/)** (Sanger / EMBL-EBI) — ~80 plant species, quarterly releases
- **[UniProt](https://www.uniprot.org/)** (SIB / EMBL-EBI / PIR) — manually-curated protein function
- **[Europe PMC](https://europepmc.org/)** — open-access literature + preprints + Agricola
- **[STRING-db](https://string-db.org/)** (SIB / EMBL) — protein-protein interaction networks
- **[Medicinal Genomics Kannapedia](https://www.kannapedia.net/)** — public cannabis strain database
- **[1001 Genomes Project](https://1001genomes.org/)** — Arabidopsis population variation
- **[3K Rice Genomes Project](https://www.nature.com/articles/sdata201418)** — rice population variation
- **[Plant Reactome](https://plantreactome.gramene.org/)** — plant pathway annotations
- **[MaizeGDB](https://www.maizegdb.org/)** — maize genome + NAM panel reference

All free. All public. All maintained by people doing real public-sector science.

## License & lineage

This is a fork of [Goodfire's EVEE MCP](https://github.com/goodfire-ai/evee-mcp) (human ClinVar variants via Evo 2 foundation model embeddings). The structural design — FastMCP, `.claude/skills/`, the `@mcp.tool()` decorator pattern, the SKILL.md "Gotchas" convention — carries through. The data, semantics, and 28 tools are entirely new.

License terms follow the upstream EVEE MCP project. Copyleft Cultivars's own contributions are open-source under permissive terms consistent with the org's free-software ethos. The org name signals the commitment: **copyleft** (free software / open data that stays open) for **cultivars** (the heritage and improvement of plant varieties). Plant genetics, like seeds, should circulate freely.

🌱 — Caleb DeLeeuw and the Copyleft Cultivars team
