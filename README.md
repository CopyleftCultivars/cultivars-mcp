# Cultivars MCP — Plant Genomics for the Commons

> Tooling for grower-scientists, heritage breeders, and natural-farming
> researchers working with the open plant-genomics commons.

An MCP server that wraps the [Ensembl Plants REST API](https://rest.ensembl.org/)
to expose gene lookup, variant effect prediction, cross-species orthology, and
sequence retrieval across ~80 plant species — Arabidopsis, rice, maize, wheat,
sorghum, common bean, cassava, tomato, sunflower, grape, and more.

This is part of the [Copyleft Cultivars](https://github.com/CopyleftCultivars)
ecosystem, alongside [TinyLLamaFarmer](https://github.com/CopyleftCultivars/TinyLLamaFarmer)
(offline natural-farming AI assistant) and the
[gemma4-natural-farming](https://huggingface.co/CopyleftCultivars/gemma4-natural-farming-gguf)
open-weight model fine-tuned on Korean Natural Farming, JADAM, and regenerative
agriculture literature.

It is a fork of [Goodfire's EVEE MCP server](https://github.com/goodfire-ai/evee-mcp)
(human clinical variants from a genomic foundation model). The clinical
machinery doesn't transfer — plant genomics has no equivalent pre-computed
deep-learning effect resource — so the underlying API was swapped for
Ensembl Plants, and the tools were reshaped around what grower-scientists
actually need to ask: *what does this gene do, does the trait carry across to
my crop, what variants exist in the breeding pool, what does this mutation
predict for the protein?*

## Why this exists

Public-sector plant genomics is small, fragmented, and easy to overlook
compared to the funding around human medical genomics. Ensembl Plants is the
most complete free, no-auth, public-sector-funded REST source for plant
variation, gene models, and comparative genomics. Phytozome (JGI) hosts
additional assemblies including draft Cannabis sativa, but requires a login —
**this server deliberately uses Ensembl Plants** so anyone can run it, no
account required, no API key, no quota.

Copyleft Cultivars's mission is *democratizing access to agricultural
knowledge where it's needed most.* The flagship tools target offline,
on-device, off-grid deployment for smallholder farmers. This MCP server is
the desk-side counterpart — for grower-scientists, citizen-scientist
breeders, and seed-keepers who do have connectivity and want to interrogate
the molecular literature without buying into proprietary breeder platforms.

## Honest framings

- **This tool needs internet.** It calls a remote REST API. That contradicts
  Copyleft Cultivars's offline-first ethos — the offline tools are
  TinyLLamaFarmer and gemma4-natural-farming. Cultivars is the desk-side
  research companion, not the field tool. Cache results locally where
  possible (Ensembl REST responses are JSON and trivially cacheable).
- **Cannabis sativa is not in Ensembl Plants.** Federal-research-funding
  constraints have historically kept Cannabis out of public plant-genomics
  infrastructure. When you query `species='cannabis_sativa'`, every tool
  returns a structured pointer to community resources (NCBI CS10 reference,
  Cannabis Genome DB) instead of a confusing 404. This gap is itself a
  Copyleft Cultivars topic.
- **Genomics is one lens.** Farmer observation, indigenous land knowledge,
  on-farm trials, soil biology, and natural-farming holism are the other
  lenses. This tool does not replace them — it complements them when you
  want a molecular explanation for something you already see in the field.
- **Variation coverage is wildly uneven.** Arabidopsis (1001 Genomes) and
  rice (3K Rice Genomes Project) are richly covered. Many heritage crops
  have gene models but no variation database — `search_variants_in_region`
  returns `[]` for those. That's a data-gap, not a tool error.
- **VEP ≠ foundation model.** Ensembl VEP is classical, rule-based,
  consequence-term-driven. It does not produce embedding-based pathogenicity
  scores. Treat consequence terms as descriptive (`missense_variant`,
  `splice_region_variant`), not as effect magnitudes.

## Tools

| Tool | Description |
|---|---|
| `list_plant_species` | Discover available species. Returns the Ensembl `name` to pass as `species` elsewhere. Optional substring filter. |
| `lookup_gene` | Resolve a gene by symbol (`PHYB`, `DREB1A`, `OsNRT1.1B`) or stable ID (`AT2G18790`). Returns coordinates, biotype, canonical transcript, description. |
| `search_variants_in_region` | List known variants overlapping a 1-based genomic region. Backed by 1001 Genomes (Arabidopsis), 3K Rice Genomes (rice), etc. |
| `get_variant` | Fetch a single known variant by stable ID. |
| `predict_variant_effect` | Run Ensembl VEP on a novel variant (region+allele) or a known variant ID. Returns per-transcript consequences, impact (HIGH/MODERATE/LOW/MODIFIER), HGVS, SIFT/PolyPhen where available. |
| `compare_variants` | Side-by-side summary of 2–10 known variants in one call. |
| `get_orthologs` | Translate findings between species via Ensembl Compara — *the* tool for grower-scientists working with heritage crops where direct molecular literature is sparse. Find the rice / maize / cassava counterpart of a well-characterized Arabidopsis gene, etc. |
| `get_sequence` | Fetch genomic / cDNA / CDS / protein sequence for a stable ID. |
| `list_trait_categories` | Discover the curated trait atlas — 18 natural-farming-relevant trait categories from drought / salt / cold tolerance through mycorrhizal symbiosis, N-use efficiency, defense secondary metabolites, photoperiodic flowering, Green Revolution dwarfing, and aluminum tolerance on acidic tropical soils. |
| `find_trait_genes` | Look up canonical genes for a trait — e.g. `drought_tolerance` → DREB1A, DREB2A, SnRK2.6/OST1, RD29A, HVA1, DRO1, each with the species in which it was characterized. The starting point for "what's known about *X*?" questions. Pair with `get_orthologs` to translate to your crop. |

## Use cases for grower-scientists

These map natural-farming and heritage-breeding questions to concrete tool
sequences. The genomics doesn't answer the farming question on its own —
but it grounds the molecular conversation.

### "Why is this landrace drought-tolerant?"
1. `find_trait_genes(trait="drought_tolerance", target_species="sorghum_bicolor")` — surfaces DREB1A, DREB2A, SnRK2.6, RD29A, HVA1, DRO1 and which species each was characterized in.
2. `get_orthologs("DREB1A", species="arabidopsis_thaliana", target_species="sorghum_bicolor")` — find the sorghum ortholog.
3. `search_variants_in_region(...)` over the ortholog's locus to see what allelic diversity is documented in the breeding pool (variation coverage varies by species — sorghum is currently sparse).

### "Does this rice gene have a maize equivalent?"
1. `lookup_gene("OsNRT1.1B", species="oryza_sativa")` — nitrate transporter
   associated with japonica/indica nitrogen-use-efficiency divergence.
2. `get_orthologs("OsNRT1.1B", species="oryza_sativa", target_species="zea_mays")`.

### "What does this SNP I found in 1001 Genomes do to the protein?"
1. `search_variants_in_region(region="2:8139756-8144461", species="arabidopsis_thaliana", limit=50)`.
2. `predict_variant_effect(variant_id="ENSVATH00237387", species="arabidopsis_thaliana")` — VEP per-transcript consequences.

### "I'm researching Cannabis sativa cultivars."
1. `lookup_gene("...", species="cannabis_sativa")` — returns a structured
   note that Ensembl Plants does not carry Cannabis, with pointers to NCBI
   CS10 and Cannabis Genome DB. We surface this gap deliberately rather
   than fail silently.

## Coordinate conventions (read before constructing IDs)

- **1-based, fully closed** — same as VCF / GFF, opposite of the upstream
  EVEE fork's 0-based convention. To query a variant at VCF position `P`,
  pass `P` directly.
- **No `chr` prefix.** Arabidopsis TAIR10 uses chromosome names `1`..`5`,
  `Mt`, `Pt`. Other plants follow their own assemblies.
- **Lowercase, underscored species names.** Always `arabidopsis_thaliana`,
  never `Arabidopsis thaliana` or `A. thaliana`. Call `list_plant_species`
  if unsure.
- **Insertions encoded as start = end + 1.** Deletions use `-` as alt allele.

## Skill

A Claude Code skill lives at `.claude/skills/cultivars/SKILL.md`. Agents that
load it get triggering criteria tuned to grower-scientist questions, species
selection guidance, ortholog workflows, and explicit caveats about which
plant genomes are open vs. paywalled.

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

## The trait atlas (`find_trait_genes`)

The fork's biggest in-code alignment with Copyleft Cultivars's mission is a curated map from natural-farming-relevant traits to canonical gene families:

| Category | Genes (representative) | Why it matters in natural farming |
|---|---|---|
| `drought_tolerance` | DREB1A, DREB2A, SnRK2.6/OST1, RD29A, HVA1, DRO1 | Marginal land + rain-fed smallholder farming |
| `salt_tolerance` | SOS1/2/3, NHX1, HKT1, OsHKT1;5 (Pokkali Saltol) | Coastal / arid irrigated smallholder farming |
| `cold_tolerance` | CBF1/2, ICE1, COR15A | High-latitude / high-altitude winter hardiness |
| `heat_tolerance` | HsfA1a, HsfA2, HSP70, HSP101 | Tropical heat extremes |
| `submergence_tolerance` | SUB1A, SK1, SK2 | Monsoon-region rice (Swarna-Sub1 lineage) |
| `nitrogen_use_efficiency` | NRT1.1/2.1, NRT1.1B, AMT1.1, GS1 | KNF / non-synthetic-fertilizer N-cycling |
| `phosphorus_uptake` | PHT1.1, PHO2, PHR1, PSTOL1 (Kasalath) | Weathered tropical soils + mycorrhizal partnership |
| `iron_uptake` | IRT1, FRO2, FIT, IDS3 | Biofortification + calcareous-soil farming |
| `mycorrhizal_symbiosis` | SYMRK/DMI2, CCaMK/DMI3, DMI1, PT4, RAM1, DELLA | KNF + JADAM nutrient-cycling backbone |
| `rhizobial_nodulation` | NFR1/5, NIN, ERN1, NSP1 | Legume cover-cropping N-fixation engine |
| `root_architecture` | PIN2, ARF7, LBD16, RHD6, DRO1 | Physical interface to managed soil biology |
| `defense_jasmonate` | COI1, MYC2, LOX2, JAR1, JAZ1 | Plant-side counterpart to KNF pest management |
| `terpene_biosynthesis` | TPS21, TPS10, STO1, OsKSL4 | Aroma / allelopathy / heritage flavor |
| `glucosinolate_biosynthesis` | MYB28/29/51, CYP79B2 | Brassica biofumigation cover crops |
| `flowering_photoperiod` | FT, CO, FLC, VRN1, Hd1 | Latitude-of-origin in heritage varieties |
| `plant_height_dwarfing` | SD1, Rht-B1, D8 | Green Revolution alleles vs. tall heritage varieties |
| `tiller_branching` | TB1 (teosinte-maize), MAX2, D14, MOC1 | Yield architecture levers |
| `aluminum_tolerance` | ALMT1, MATE1/AltSB, STOP1 | Acidic tropical soils — landrace heritage |

For each gene the atlas records the species in which it was characterized and a one-line function; pair with `get_orthologs` to translate to the crop you actually grow. The atlas is a **starting-point literature map**, not a closed list.

## Testing & CI

The repository ships a pytest suite (`tests/test_server.py`) using `httpx.MockTransport` — no live network required, runs in ~1 second. GitHub Actions runs it on Python 3.10 / 3.11 / 3.12 on every PR.

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests cover: Cannabis-sativa fallback (zero HTTP), `/lookup/id` 400-vs-404 fallback semantics, region-search truncation, VEP input validation, ortholog symbol fallback, 429/503 Retry-After backoff, retry budget exhaustion, trait atlas invariants, species-name normalization.

## Data sources

- **[Ensembl Plants](https://plants.ensembl.org/)** — gene models and comparative genomics for ~80 plant species; quarterly releases.
- **[1001 Genomes Project](https://1001genomes.org/)** — Arabidopsis thaliana population variation, exposed via Ensembl.
- **[3K Rice Genomes Project](https://www.nature.com/articles/sdata201418)** — rice population variation, exposed via Ensembl.
- **[Ensembl Compara](https://www.ensembl.org/info/genome/compara/index.html)** — protein-tree-based orthology for cross-species translation.

## License & lineage

This is a fork. License terms follow the upstream EVEE MCP project's
license; see the original repo for the canonical terms. Copyleft Cultivars's
own work is licensed under permissive open-source terms (Apache 2.0 / MIT
depending on the project) consistent with the org's free-software ethos.

The org name signals the commitment: **copyleft** (free software / open data
that stays open) for **cultivars** (the heritage and improvement of plant
varieties). Plant genetics, like seeds, should circulate freely.
