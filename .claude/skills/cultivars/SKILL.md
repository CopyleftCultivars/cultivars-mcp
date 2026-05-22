---
name: cultivars
description: Plant-genomics lookup for grower-scientists, heritage breeders, and natural-farming researchers via the Ensembl Plants REST API. Use when the user mentions a specific plant gene (PHYB, DREB1A, OsCKX2, ZmRAP2.7), a plant gene ID (AT2G18790, Os01g0100100, Zm00001eb...), a plant species' variant, a genomic region in Arabidopsis / rice / maize / sorghum / common bean / cassava / tomato / sunflower / grape (and other Ensembl Plants species), or asks about cross-species orthology between plants ("what's the rice equivalent of this Arabidopsis gene?"). Trigger on questions about variant effects in plants, predicted impact of a plant SNP/indel, plant gene structure (transcripts, biotype, coordinates), plant gene sequences (genomic / cDNA / CDS / protein), or 1001 Genomes / 3K Rice Genomes variants. Trigger on questions about Cannabis sativa genetics too — the tool surfaces an honest gap notice with NCBI / Cannabis Genome DB pointers rather than failing silently. Do NOT trigger on general agronomic questions (fertilizer, irrigation, composting, IMO preparation, KNF inputs) — those belong to TinyLLamaFarmer / gemma4-natural-farming. Do NOT trigger on phenotypic breeding advice or on-farm trial design. Do NOT trigger on human or animal genetics.
allowed-tools: mcp__cultivars__list_plant_species mcp__cultivars__lookup_gene mcp__cultivars__search_variants_in_region mcp__cultivars__get_variant mcp__cultivars__predict_variant_effect mcp__cultivars__compare_variants mcp__cultivars__get_orthologs mcp__cultivars__get_sequence mcp__cultivars__list_trait_categories mcp__cultivars__find_trait_genes
---

# Cultivars — Plant Genomics for the Commons

## What this skill is for

Cultivars is the desk-side genomics companion in the
[Copyleft Cultivars](https://github.com/CopyleftCultivars) ecosystem.
It answers molecular questions about plant genes, variants, and orthology
for grower-scientists who already work with seeds, soil, and farm data —
and who occasionally need to dive into the genome literature to ground
something they're observing in the field.

It is NOT a clinical tool, NOT a foundation-model effect predictor, and
NOT a substitute for agronomic guidance. It wraps the
[Ensembl Plants REST API](https://rest.ensembl.org/) — a free, no-auth,
public-sector resource.

Sibling tools in the ecosystem:
- **[TinyLLamaFarmer](https://github.com/CopyleftCultivars/TinyLLamaFarmer)** — offline natural-farming AI assistant for the field
- **[gemma4-natural-farming](https://huggingface.co/CopyleftCultivars/gemma4-natural-farming-gguf)** — open-weight Korean Natural Farming / JADAM / regenerative model

Route agronomic, fertilizer, IMO, and KNF questions to those. Route
gene/variant/sequence/orthology questions here.

## Stance and values

Copyleft Cultivars's mission is *democratizing agricultural knowledge*.
That shapes how to use this tool:

- **Open over proprietary.** Cite Ensembl Plants, NCBI, public reference
  papers. Don't point users at paywalled breeder platforms.
- **Heritage and crop-diversity over industrial monoculture.** When choosing
  example species, lean toward smallholder-relevant crops — rice, sorghum,
  common bean, cassava, finger millet, pearl millet, teff (when in Ensembl)
  — alongside Arabidopsis the model organism.
- **Honest about gaps.** Cannabis sativa is not in Ensembl Plants and many
  heritage crops have gene models but no variation data. Say so plainly
  instead of papering over it. The tool itself returns structured
  "gap notices" for known-absent species.
- **Genomics as one lens.** Always frame results as a molecular hypothesis
  to interrogate alongside farmer observation, not as a ruling.
- **Online dependency is real.** This tool needs the internet. Cultivars's
  offline tooling lives elsewhere (TinyLLamaFarmer). Don't pretend.

## Plant genomes available (highlights)

The full list comes from `list_plant_species()`. Highlights for the
Copyleft Cultivars audience:

| Species (Ensembl `name`) | Common name | Notes |
|---|---|---|
| `arabidopsis_thaliana` | Thale cress | Model plant; richest data (1001 Genomes) |
| `oryza_sativa` | Asian rice (japonica) | 3K Rice Genomes Project variation |
| `oryza_indica` | Indica rice | Major staple lineage |
| `zea_mays` | Maize | Massive breeding pool |
| `sorghum_bicolor` | Sorghum | Drought-tolerant smallholder cereal |
| `triticum_aestivum` | Bread wheat | Hexaploid — be careful with homoeologs |
| `hordeum_vulgare` | Barley | |
| `glycine_max` | Soybean | |
| `phaseolus_vulgaris` | Common bean | Smallholder staple |
| `manihot_esculenta` | Cassava | Tropical-staple, heritage crop |
| `solanum_lycopersicum` | Tomato | |
| `solanum_tuberosum` | Potato | |
| `vitis_vinifera` | Grape | |
| `helianthus_annuus` | Sunflower | |
| `brassica_napus`, `brassica_rapa` | Rapeseed / turnip | Crop-relevant Brassica |

**Not in Ensembl Plants** (but the tool returns a structured fallback):
- `cannabis_sativa` — see NCBI CS10 reference, Cannabis Genome DB
- Many heritage / orphan crops not yet sequenced to reference quality

## How to use the tools

### Step -1 (most common entry point for grower-scientist questions): trait atlas

When a user asks "what's known about *X*?" — drought tolerance, mycorrhiza,
N-use efficiency, photoperiodic flowering, aluminum tolerance on acidic
soils — the **fastest grounding** is the curated trait atlas:

```
list_trait_categories()
find_trait_genes(trait="drought_tolerance", target_species="sorghum_bicolor")
```

`find_trait_genes` returns 3–6 canonical gene symbols per trait, each
tagged with the species in which it was characterized and a one-line
function. Trigger criteria:

- **Use it whenever the user names a trait but not a gene.** That covers
  the vast majority of grower-scientist questions.
- **Use it before `get_orthologs`** — the atlas tells you which gene to
  translate. Without it, you'd be guessing.
- **Don't use it for "what does gene X do?"** — that's `lookup_gene`
  followed by reading the `description` field.

The atlas is a starting-point literature map, **not a closed list**. If
the user names a trait that isn't covered, fall back to literature search
plus `lookup_gene` on a known gene symbol from that literature.

Available trait categories (18 as of this release):
drought_tolerance, salt_tolerance, cold_tolerance, heat_tolerance,
submergence_tolerance, nitrogen_use_efficiency, phosphorus_uptake,
iron_uptake, mycorrhizal_symbiosis, rhizobial_nodulation,
root_architecture, defense_jasmonate, terpene_biosynthesis,
glucosinolate_biosynthesis, flowering_photoperiod, plant_height_dwarfing,
tiller_branching, aluminum_tolerance.

### Step 0: Identify the species

Always confirm the Ensembl species name before any other call. The user
may say "rice", "rice indica", "wild rice" — these are different species.

```
list_plant_species(query="rice")
```

Returns matches; pick the one matching `display_name` or `common_name`.

### Step 1: Resolve the gene

```
lookup_gene(gene="PHYB", species="arabidopsis_thaliana")
lookup_gene(gene="AT2G18790")            # stable ID; species inferred
```

Returns coordinates, biotype, canonical transcript, description, and a
deep link to the Ensembl Plants gene page.

### Step 2 (often the most useful): Translate across species

The headline tool for grower-scientists working outside the model
organism. Plant molecular literature is overwhelmingly Arabidopsis-first;
to apply a finding to rice / maize / cassava / common bean, you need the
ortholog.

```
get_orthologs(gene="AT2G18790", species="arabidopsis_thaliana",
              target_species="oryza_sativa")
get_orthologs(gene="DREB1A",   species="arabidopsis_thaliana",
              target_taxon=4577)   # all of Zea genus
```

Report ortholog type (`ortholog_one2one`, `ortholog_many2many`) and the
`taxonomy_level` of the homology call — `many2many` at deep nodes is
weaker evidence than `one2one` at a recent node.

### Step 3 (variant queries): Find or evaluate variants

For known variants in a region:
```
search_variants_in_region(region="2:8139756-8144461",
                          species="arabidopsis_thaliana", limit=50)
```

For predicting effect of a novel substitution:
```
predict_variant_effect(region="2:8140000-8140000", allele="T",
                       species="arabidopsis_thaliana")
```

For predicting effect of a known variant:
```
predict_variant_effect(variant_id="ENSVATH00237387",
                       species="arabidopsis_thaliana")
```

VEP returns per-transcript consequence terms and an impact level
(HIGH / MODERATE / LOW / MODIFIER). Treat them as descriptive — VEP is
rule-based, not a foundation model. SIFT / PolyPhen scores appear for
some species where Ensembl has run those tools.

### Step 4 (deep dive): Sequence

```
get_sequence(stable_id="AT2G18790.1", seq_type="protein")
get_sequence(stable_id="AT2G18790",   seq_type="genomic")
```

For protein / cDNA / CDS prefer a *transcript* ID (e.g. `AT2G18790.1`),
not the gene ID, to avoid ambiguity.

## Gotchas (read before constructing IDs)

These defy reasonable assumptions in ways that produce silent wrong
answers, not errors.

- **Coordinates are 1-based and fully closed.** Same as VCF and GFF —
  *opposite* of the upstream EVEE fork's 0-based convention. A grower
  reading a VCF can pass positions through unchanged.
- **No `chr` prefix.** Arabidopsis TAIR10 uses `1`..`5`, `Mt`, `Pt`.
  Other plants use their own assembly conventions; if `lookup_gene`
  returned `seq_region_name: "2"`, that's what to pass in regions.
- **Species names are lowercase, underscored.** `arabidopsis_thaliana`,
  not `Arabidopsis thaliana`, not `A_thaliana`.
- **Variation coverage is wildly uneven.** Rich for Arabidopsis (1001
  Genomes) and rice (3K Rice Genomes). Empty or near-empty for many
  crops — `search_variants_in_region` returns `[]`, not an error. Don't
  conclude "no variants exist"; conclude "Ensembl hasn't catalogued any
  in this species."
- **Hexaploid wheat homoeologs.** Bread wheat (`triticum_aestivum`) is
  hexaploid (AABBDD). A gene name like *TaVRN1* exists in three
  homoeologous copies (A, B, D subgenomes). Use stable IDs and report
  the subgenome explicitly.
- **Cannabis sativa is not in Ensembl Plants.** The tools return a
  structured fallback pointing to NCBI CS10 and community databases.
  This is a deliberate Copyleft-Cultivars-aware behavior, not a bug.
- **VEP is not a pathogenicity score.** Consequence terms describe
  *what kind of variant* (missense, splice donor, intron, etc.). They
  do NOT rank biological impact magnitude. Don't say "highly pathogenic"
  for a plant variant — there is no such label in plant population
  genetics.
- **Gene-symbol case sensitivity varies.** Arabidopsis tends to accept
  uppercase symbols (`PHYB`); rice symbols can be `OsCKX2` with
  internal capitalization. When in doubt, try the stable ID.
- **`compare_variants` does not deduplicate.** Strip duplicates client
  side; passing the same ID three times issues three GETs.

## Presenting results to grower-scientists

- **Lead with the practical bottom line.** "PHYB is a red/far-red
  photoreceptor controlling shade avoidance; the rice ortholog is
  OsPHYB" beats "AT2G18790, biotype protein_coding…".
- **Carry the gene's *function* through, not just its ID.** Ensembl's
  `description` field is the most concise function summary; lead with it.
- **Frame variant effects as hypotheses.** "VEP predicts this is a
  missense variant in the FBN1 EGF-like domain; whether that produces
  the observed phenotype depends on context including expression level,
  genetic background, and growing conditions."
- **When orthology is `many2many`, surface that uncertainty.** Plant
  genomes have undergone whole-genome duplications; many "the rice
  equivalent" answers are really "one of several rice paralogs."
- **Connect back to natural-farming concepts when relevant.**
  Stress-response transcription factors (DREB, MYB, WRKY), nutrient
  transporters (NRT, PHT), root-architecture genes (PIN, LBD), and
  defense/secondary-metabolite pathways (LOX, JAR, terpene synthases)
  are the genes most likely to come up when a KNF / regenerative
  grower asks "why does this work?" Highlight the connection.
- **Cannabis sativa: be honest about the gap.** When the tool returns
  the fallback notice, surface it directly to the user — this is a
  Copyleft Cultivars topic, not an inconvenience.
- **Share the `ensembl_url` deep link at the end.** Lets the user
  explore the gene or variant in the Ensembl Plants UI.

## Example

User: *"I'm working with a sorghum landrace that handles drought really
well. What's known about the rice-style drought TFs in sorghum?"*

1. Recognize this as: known stress-response transcription factor family
   + cross-species ortholog question. Route to Cultivars (not
   TinyLLamaFarmer — they're asking for molecular grounding, not field
   method).
2. `find_trait_genes(trait="drought_tolerance", target_species="sorghum_bicolor")`
   → surfaces DREB1A, DREB2A, SnRK2.6/OST1, RD29A, HVA1, DRO1 as
   canonical entries, with characterized species noted. Now you have
   a *list* of genes to translate, not just one.
3. `get_orthologs("DREB1A", species="arabidopsis_thaliana",
   target_species="sorghum_bicolor")` → return the sorghum ortholog
   stable IDs and their homology types. Repeat for the other genes the
   user finds most interesting.
4. `lookup_gene(<stable_id>, species="sorghum_bicolor")` for the most
   one2one ortholog to get coordinates and description.
5. Optionally `search_variants_in_region` over that locus — sorghum
   variation coverage is partial, so be ready to report `count=0` and
   say so.
6. Present: "DREB1A is the canonical Arabidopsis drought-responsive
   transcription factor. The sorghum ortholog is `SbDREB1A` /
   `<stable_id>`; the homology is `ortholog_one2one` at the
   *Mesangiospermae* taxonomy level (high-confidence). Ensembl Plants
   doesn't have a deep variation catalog for sorghum, so I can't show
   what allelic diversity sits in the landrace pool here — for that
   you'd need a population resequencing study like the
   Sorghum-Bicolor-Association-Panel. Worth keeping in mind that
   drought tolerance in a landrace is rarely a single-gene story;
   DREB1A is a starting point, not the whole answer."

End with the Ensembl deep-link.
