---
name: cultivars
description: Plant-genomics lookup for grower-scientists, heritage breeders, and natural-farming researchers across 5 live databases (Ensembl Plants, UniProt, Europe PMC, STRING-db, Medicinal Genomics Kannapedia) plus a 30-category curated trait atlas. Use when the user mentions a specific plant gene (PHYB, DREB1A, OsCKX2, ZmRAP2.7, THCAS, CBDAS), a plant gene ID (AT2G18790, Os01g0100100, Zm00001eb..., Q8GTB6 UniProt), a plant variant or genomic region, a plant trait by name (drought tolerance, mycorrhizal symbiosis, hemp THC compliance, etc.), or asks about cross-species orthology between plants. Trigger on Cannabis-specific questions — the tool has dedicated cannabinoid biosynthesis, terpene chemotype, hemp compliance, and Kannapedia-strain-lookup tools that work despite Cannabis sativa not being in Ensembl Plants. Trigger on questions about a Kannapedia RSP ID (rsp13536, rsp10837 etc.) or cannabis strain by name. Trigger on requests for "recent literature on gene X" — the search_pubmed_for_gene tool returns current papers. Trigger on protein-protein interaction questions ("what does SOS1 interact with?"). Do NOT trigger on general agronomic questions (fertilizer, irrigation, composting, IMO preparation, KNF inputs) — those belong to TinyLLamaFarmer / gemma4-natural-farming. Do NOT trigger on phenotypic breeding advice or on-farm trial design. Do NOT trigger on human or animal genetics.
allowed-tools: mcp__cultivars__list_plant_species mcp__cultivars__lookup_gene mcp__cultivars__search_variants_in_region mcp__cultivars__get_variant mcp__cultivars__predict_variant_effect mcp__cultivars__compare_variants mcp__cultivars__get_orthologs mcp__cultivars__get_sequence mcp__cultivars__list_trait_categories mcp__cultivars__find_trait_genes mcp__cultivars__translate_trait_to_species mcp__cultivars__lookup_gene_evidence mcp__cultivars__lookup_uniprot_entry mcp__cultivars__search_pubmed_for_gene mcp__cultivars__get_string_interactions mcp__cultivars__lookup_kannapedia_strain mcp__cultivars__compare_cannabis_strains mcp__cultivars__cannabis_strain_search_urls mcp__cultivars__list_maize_nam_founders mcp__cultivars__submit_phenotype_observation mcp__cultivars__query_community_phenotypes mcp__cultivars__verify_observation_integrity mcp__cultivars__pin_observation_to_ipfs mcp__cultivars__estimate_gwas_power mcp__cultivars__resolve_accession mcp__cultivars__query_organellar_variants mcp__cultivars__export_offline_snapshot mcp__cultivars__list_orphan_crop_requests
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

## Tool routing — which tool for which question

The read-only genomics tools cluster into seven query patterns (see the
Community Science Layer section below for the write-path / participatory tools).
Use this table as the routing decision:

| When the user asks... | Start with... | Then... |
|---|---|---|
| "What's known about [trait]?" | `list_trait_categories` then `find_trait_genes(trait=...)` | Optionally `lookup_uniprot_entry` for each canonical gene's full curation; or `search_pubmed_for_gene` for newer literature |
| "What's the [crop] equivalent of [Arabidopsis gene]?" | `translate_trait_to_species` (composed) OR `get_orthologs` (one gene) | `lookup_gene_evidence` on the resolved ortholog if veracity matters |
| "Tell me about gene X" | `lookup_gene` | Then `lookup_gene_evidence` for veracity tier + `lookup_uniprot_entry` for curated function |
| "What does the literature say about gene X (recently)?" | `search_pubmed_for_gene(query="X species")` | Pass through 2025/2026 papers — the LIVING document |
| "What variants exist in this region?" | `search_variants_in_region` | Then `predict_variant_effect` or `get_variant` for specifics |
| "Tell me about cannabis strain rspNNNNN" | `lookup_kannapedia_strain(rsp_id=...)` | For multiple strains, `compare_cannabis_strains` (max 5) |
| "What proteins interact with X?" | `get_string_interactions` | Surface evidence channels (textmining vs experimental) so user can grade |

### Cannabis-specific routing

When the user mentions Cannabis sativa, hemp, a chemotype (Type I/II/III), or any cannabinoid/terpene synthase:
1. If they have an RSP ID → `lookup_kannapedia_strain` directly
2. If they have a strain name → `cannabis_strain_search_urls` to give them search links
3. If they ask about chemotype genetics → `find_trait_genes(trait="cannabinoid_biosynthesis")` and `find_trait_genes(trait="hemp_compliance")`
4. For Cannabis protein function → `lookup_uniprot_entry(uniprot_id="Q8GTB6")` (THCAS) or similar — UniProt works despite Ensembl Plants gap
5. For Cannabis interactions → `get_string_interactions(species="cannabis_sativa")` — STRING covers Cannabis (taxon 3483)

### Maize / corn routing

When the user mentions corn, maize, fall armyworm, sweet corn, popcorn, or heritage corn breeding:
1. `find_trait_genes(trait="maize_disease_resistance" | "maize_pest_resistance" | "maize_quality_protein")`
2. `list_maize_nam_founders(subpopulation="Tropical / Subtropical")` for smallholder-relevant breeding lines (CIMMYT CML + Thai Ki3/Ki11 + IITA Tzi8)
3. Use `lookup_gene` on maize stable IDs (Zm00001eb...) directly

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

## Community Science Layer (write path + participatory tools)

The tools above are read-only genomics lookups. The tools below let a
grower-scientist *contribute* observations and reason about collective
statistical power. Route to them when the user wants to record field data,
check community data, attribute/verify a contribution, resolve a folk seed
name, query organellar genomes, or hand off to the offline field tool.

### `submit_phenotype_observation` — record a field observation

**Trigger when:** the user reports a measured phenotype they want to
contribute ("my Oaxacan maize survived 14 days of flooding", "this landrace
flowered after 95 days", "record that…"). This is the *write* path — the
commons grows here.

**Parameter guidance:**
- `trait_category` MUST be an atlas category (`list_trait_categories`) or an
  organellar trait (`cms`, `plastid_herbicide_resistance`,
  `plastid_photosynthesis`). Validate first if unsure.
- `measurement_type` is `binary` (bool value), `continuous` (numeric + unit),
  or `categorical` (string).
- Use `accession_id="community:{name}"` when there's no formal ID.

**Integration:** If the user gives an informal seed name, run
`resolve_accession` FIRST to get a formal GRIN ID, then pass it in. After
submission, the response returns a `canonical_form` the user can sign with an
Ed25519 key and resubmit (with `submitter_pubkey` + `signature`) for verifiable
attribution.

**Gotcha:** The tool writes a local YAML and returns PR instructions — it does
**not** push to GitHub itself (no credentials at runtime). Tell the user to
open a PR. Same accession + trait + date overwrites (one observation per day).

### `query_community_phenotypes` — what does the ledger already hold?

**Trigger when:** "how many observations of X do we have?", or as a precursor
to a power estimate. Returns count, measurement distribution, and accessions.

### `estimate_gwas_power` — can the community detect a locus?

**Trigger when:** "can my village's 12 rice varieties detect the SUB1A
locus?", "how many samples do we need?". If `n_observations` is omitted it
pulls the live count from the ledger.

**Gotcha:** This is order-of-magnitude guidance (Bonferroni over an approximate
SNP count, additive common-variant model). Always surface the caveat that real
plant GWAS needs kinship/structure correction, which raises required N. Don't
present the number as a guarantee.

### `verify_observation_integrity` — attribution proof

**Trigger when:** the user wants to confirm who signed an observation or that
it wasn't altered. Ed25519 over the canonical form. Unsigned observations are
still valid data — say so; they just lack an attribution proof. **Not** a
financial instrument — no tokens/chain (decline requests to add them).

### `pin_observation_to_ipfs` — content addressing

**Trigger when:** the user wants a permanent, tamper-evident, decentralized
identifier for an observation (and optionally a VCF). **Gotcha:** needs a
running local kubo node; if unreachable it returns a structured fallback with
setup instructions, not an error. The observation is valid without a CID.

### `resolve_accession` — folk name → formal GRIN ID

**Trigger when:** the user names a landrace/heritage seed informally ("my
grandmother's Hopi blue corn", "Gobol Sail rice"). Bridges to USDA GRIN-Global
and maps back to an Ensembl species string. **Run before** `lookup_gene` /
`find_trait_genes` / `submit_phenotype_observation` when the name is informal.
**Gotcha:** GRIN's REST schema varies; a `match_count: 0` with the manual-search
fallback link is a legitimate honest answer.

### `query_organellar_variants` — Mt / Pt genomes

**Trigger when:** the user asks about cytoplasmic male sterility (CMS, hybrid
seed), plastid/chloroplast herbicide resistance (psbA/atrazine), maternal
inheritance, or `rbcL` barcoding. **Gotcha:** `Mt` and `Pt` are valid Ensembl
chromosome identifiers, NOT errors — say so. Organellar genomes are maternally
inherited (relevant to how GM/herbicide-resistance traits spread via seed).

### `export_offline_snapshot` — hand off to the field

**Trigger when:** the user wants to take a trait's genomics offline / into
TinyLLamaFarmer. Packages the atlas entry, species coverage, and (optionally)
target-species orthologs into a portable JSON. Online→offline only; the reverse
(field→ledger) is `submit_phenotype_observation`.

### `list_orphan_crop_requests` — contribution bounty

**Trigger when:** the user asks how to contribute, or about underrepresented
crops (teff, fonio, cowpea, pigeon pea, finger millet, amaranth, enset, grass
pea, quinoa). Returns the `WANTED_TRAITS.yaml` bounty list and PR guidance.

### `get_variant(..., population_context=True)` — allele frequencies + Fst

Set `population_context=True` when the user asks about allele frequency across
populations or subpopulation differentiation (e.g. Indica vs Japonica rice).
**Gotcha:** Only meaningful for `richly_covered` species; otherwise the tool
returns a structured "not available" note rather than fabricating numbers.

### Values note for the write path

The ledger data is licensed **ODbL-1.0** (open-data copyleft, see
`DATA_LICENSE.md`), distinct from the Apache-2.0 code license — this keeps the
commons open against enclosure. Attribution is via Ed25519 signatures, a
scientific-credit mechanism, never a token or financial instrument.
