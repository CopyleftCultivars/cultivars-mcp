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

## Use cases for grower-scientists

These map natural-farming and heritage-breeding questions to concrete tool
sequences. The genomics doesn't answer the farming question on its own —
but it grounds the molecular conversation.

### "Why is this landrace drought-tolerant?"
1. `lookup_gene("DREB1A", species="arabidopsis_thaliana")` — the canonical
   drought-responsive transcription factor in Arabidopsis.
2. `get_orthologs(...)` — find the ortholog in your species (rice OsDREB1A,
   maize ZmDREB1A, etc.).
3. `search_variants_in_region(...)` over the ortholog's locus to see what
   allelic diversity is documented in the breeding pool.

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
