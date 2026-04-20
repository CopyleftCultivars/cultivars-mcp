---
name: evee
description: Look up pathogenicity, mechanistic interpretation, and disruption profiles for specific genetic variants via the EVEE API (Evo 2 genomic foundation model). Use when the user mentions a specific variant by gene name (BRCA1, TP53), rsID (rs1597537935), ClinVar variation ID (655979), HGVS notation (c.1234A>G, p.Arg412Gln), or genomic coordinate (chr17:43044295:A:G) — even if they don't mention "EVEE" or "ClinVar" by name. Trigger on questions about whether a variant is pathogenic, benign, or VUS; why it causes disease; how it compares to related variants; or what its predicted effect on protein/splicing/regulation is. Do NOT trigger on general gene-function questions, gene-expression analysis, CRISPR guide design, or evolutionary biology — this skill is for per-variant effect lookup only.
allowed-tools: mcp__evee__search_variants mcp__evee__get_variant mcp__evee__wait_for_variant_analysis mcp__evee__get_variant_disruptions mcp__evee__get_variant_annotations mcp__evee__compare_variants
---

# EVEE — Evo Variant Effect Explorer

## About EVEE

EVEE ([Pearce et al., 2026](https://www.biorxiv.org/content/10.1101/2026.04.10.717844v1)) is a pre-computed resource for interpretable variant effect prediction, powered by embeddings from Evo 2 — a 7B-parameter genomic foundation model.

The pipeline has three stages:

1. **Pathogenicity.** A supervised *covariance probe* is trained on the per-position embedding differences between the reference and alternate sequence (Evo 2 layer 27, 65 kb context window around the variant). It reaches 0.997 AUROC on 833k ClinVar SNVs and transfers zero-shot to indels at 0.991 AUROC, outperforming CADD, AlphaMissense, GPN-MSA, NTv3, AlphaGenome, and loss-based baselines across every consequence type tested.
2. **Disruption profile.** A separate panel of supervised annotation probes predicts 357 binary biological annotations (protein domains, secondary structure, splice sites, chromatin state, PTMs, etc.) at the variant position and 5 flanking positions. The delta between ref and alt for each annotation is the *disruption*. Median probe AUC is 0.919. This panel is what `get_variant_disruptions` and `get_variant_annotations` expose.
3. **Interpretation.** The top 10 disruptions plus gene metadata and HGVS notation are fed to a frontier LLM which synthesizes a natural-language mechanism. LLM-as-judge evaluation against ClinVar expert reviews scored the output 3.89/5 composite (mechanism coverage 3.15, biological accuracy 4.27, specificity 4.15).

Coverage: **4.25 million ClinVar variants** pre-computed. ~1.5M have expert clinical labels (pathogenic / benign); ~2.7M are unlabeled (VUS, conflicting, zero-star). The goal of EVEE is explicitly to help reason about the VUS backlog.

## Gotchas (read this before constructing variant IDs)

These are environment-specific facts that defy reasonable assumptions. Ignoring any one of them produces silent wrong answers or silent empty results.

- **Coordinates are 0-based. ClinVar VCF / HGVS / VCF are 1-based.** To query a ClinVar variant at 1-based position `P`, use `chr{c}:{P-1}:{ref}:{alt}`. The off-by-one doesn't always 404 — at many positions it returns a *different real variant*, which is worse than an error.
- **The −1 rule does NOT generalize to indels.** Indels in EVEE are stored in VCF-anchored bi-allelic form (`chr7:117559589:ATCT:A` for CFTR ΔF508), with the anchor base often several positions upstream of the ClinVar HGVS position. Naive `pos−1` constructions 404 on ~25% of indels. **Prefer `search_variants` with the ClinVar variation ID or rsID for any indel** — it returns the correctly-formed ID.
- **`search_variants` silently returns `[]` for qualified queries.** `search_variants("BRCA1;")`, `search_variants("BRCA1 pathogenic")`, `search_variants("rs")`, `search_variants("rs1")` all return `[]`, not an error. Strip trailing punctuation and extra tokens before passing — the query must be a bare identifier.
- **Chromosome and nucleotide casing is strict.** Must be `chr1…chr22`, `chrX`, `chrY`, `chrM` (not `chrMT`, not `MT`, not `1`, not `Chr1`). Nucleotides must be uppercase `A/C/G/T`. Anything else 404s.
- **`pathogenicity_score` and `clinical_label` can diverge sharply.** TP53 R175H is ClinVar Pathogenic (3-star, expert panel) but `pathogenicity_score ≈ 0.54`. The EVEE score is independent of the ClinVar label — present both when they disagree, and trust ClinVar's expert panel over EVEE for well-annotated hotspots.
- **Minus-strand genes report plus-strand `ref`/`alt`, but `hgvsc` is gene-strand.** TP53 R175H returns `ref=C, alt=T` (plus strand) while `hgvsc="c.524G>A"` (gene strand). Biologically correct but the strings will look mismatched to a user comparing them; call out the strand explicitly when this happens.
- **`compare_variants` does not deduplicate inputs.** Passing the same ID 3× issues 3 GETs and returns 3 identical rows. Dedupe client-side.

## Reliability by variant class

EVEE is not uniform across variant types. When you report results, caveat appropriately:

- **Strong:** missense (0.971 AUROC), synonymous (0.961), splice (0.924), UTR (0.929), intronic (0.984), small indels ≤20 bp (0.984–0.991), insertions (0.991), deletions (0.988). EVEE's central strength is that it handles coding *and* non-coding variants in one framework.
- **Moderate:** nonsense (0.900), large indels >20 bp (0.916).
- **Weaker:** frameshifts (0.770 — but the benchmark is 99% pathogenic, so this number is dominated by class imbalance, not model failure).
- **Conservation range:** EVEE is robust across the conservation spectrum. Annotation-based methods like CADD and AlphaMissense degrade sharply at fast-evolving sites; EVEE does not.

When a user asks about a variant that sits in one of the weaker classes, surface that caveat.

## Known limitations (from the authors)

1. **Evolutionary prior.** Evo 2 was trained on the tree of life. It excels at detecting the strong deleterious signatures of Mendelian pathogenic variants, but is likely *less calibrated* for subtle polygenic / complex-trait effects where each variant has a small individual contribution.
2. **Known-annotation ceiling.** The annotation probes predict *known* biological features. A variant acting through a truly novel mechanism may still score pathogenic but won't have a clean disruption-profile explanation. If the disruptions look diffuse or generic, say so.
3. **Interpretations are hypotheses.** The LLM-generated `interpretation` field is a structured hypothesis, not a clinical diagnosis. Both the paper and the public blog say it "should be treated as hypotheses requiring expert review, not as clinical conclusions." Reflect this in how you present results.
4. **Preprint.** The paper is not yet peer-reviewed.

## How to use the tools

### Step 1: Find variants with `search_variants`

The query parameter is an **autocomplete-style lookup** that returns **at most 6 matches**. Pass exactly ONE of:
- A gene name: `BRCA1`, `TP53`, `FBN1`
- An rsID: `rs1597537935`
- A ClinVar variation ID (numeric): `655979`

**Do NOT** add qualifiers like "pathogenic", "missense", or combine terms — it is a lookup, not a text search. See Gotchas for the silent-empty failure mode.

**Warning — gene queries:** a gene-name query returns an adjacent-position autocomplete slice of candidate variants in that gene — **NOT** a complete gene-wide ranking. Do not conclude "gene X has no highly pathogenic variants" from a bare gene search; you're only seeing 6 rows. To look up a specific variant, prefer an rsID or ClinVar variation ID.

### Step 2: Get clinical summary with `get_variant`

Pass a variant ID from search results (format: `chr:pos:ref:alt`). Returns:
- Clinical label, pathogenicity score, disease associations
- HGVS coding/protein notation, gene constraint (LOEUF)
- `model_derived_scores` (EVEE heads aligned to AlphaMissense / CADD / REVEL / SIFT etc.) and `reference_predictor_scores` (raw values from source databases when present)
- `interpretation` — either the full AI-generated mechanistic interpretation (summary / mechanism / key_evidence / confidence) or, when not yet ready, a `{status, detail}` entry to prompt polling
- `evee_url` deep-link to the web UI

If `interpretation` comes back as a status dict instead of text, call `wait_for_variant_analysis` to poll until generation completes. If it's still unavailable, rely on `get_variant_disruptions` and say so plainly — don't invent a mechanism.

### Step 2b (optional): Wait for interpretation with `wait_for_variant_analysis`

When `get_variant` reports `interpretation.status` as `queued` / `processing`, use `wait_for_variant_analysis(variant_id)` to poll EVEE's on-demand generation. Returns the same curated summary plus a `wait_status` entry. If it still times out, call it again to keep polling.

### Comparing variants with `compare_variants`

When the user asks to contrast, rank, or compare 2+ variants, call `compare_variants(variant_ids=[...])` (max 10 IDs) instead of looping `get_variant`. Returns a compact row per variant — `variant_id`, `evee_url`, `gene`, `clinical_label`, `pathogenicity_score`, `hgvs_protein_short`, `consequence`, and the top-1 disruption. One call beats N. Dedupe input IDs yourself — the tool doesn't.

### Step 3 (optional): Understand WHY with `get_variant_disruptions`

Use when the user wants to know *why* a variant is pathogenic/benign, or you need to explain the mechanism in more detail. This is especially important when interpretation text is pending. Returns the top disruptions ranked by magnitude across 325 biological annotations. The probe operates at per-position resolution and reports disruptions up to ±5 positions from the variant, so long-range effects (e.g. splice disruption spanning an exon–intron boundary) do show up.

Pass the optional `category` arg to restrict the ranking to one class of annotations:
- Splice-related / genomic flags → `category='genomic_feature'`
- Protein-domain hits → `category='interpro'` or `category='protein_feature'`
- Chromatin / regulatory → `category='chromhmm'`, `category='chipseq'`, `category='ccre'`

### Step 4 (optional): Deep dive with `get_variant_annotations`

Use when investigating specific annotation categories in depth. Pass `category` to filter:
`amino_acid`, `atacseq`, `ccre`, `chipseq`, `chromhmm`, `elm`, `fstack`, `protein_feature`, `interpro`, `genomic_feature`, `ptm`, `region`, `secondary_structure`

Omit `category` to get all 325 annotations.

## Presenting results

- Lead with the clinical bottom line: is it pathogenic, benign, or uncertain?
- Include the HGVS notation and gene name for precision.
- When an AI interpretation is available, use it — it synthesizes the disruption profile into a readable mechanistic explanation. Frame it as a *hypothesis*, not a diagnosis.
- Be precise about scores: `model_derived_scores` are EVEE probe outputs aligned to external predictors, not raw AlphaMissense / CADD / REVEL / SIFT values. `reference_predictor_scores`, when present, are the raw external values.
- **Predictor consensus:** when EVEE agrees with several of the aligned probes (alphamissense / revel / cadd / clinpred), call that out as high confidence. When EVEE diverges sharply, flag it — that divergence is informative, not noise, and often highlights the interesting cases.
- **Score vs. label disagreement:** if `pathogenicity_score` and `clinical_label` disagree, say so explicitly and defer to ClinVar's expert-panel label for well-annotated variants. Don't paper over it.
- For disruptions, highlight the top 3–5 most biologically meaningful changes rather than listing all of them.
- **Caveat the variant class** when relevant (frameshifts, large indels, subtle polygenic effects — see the Reliability section above).
- Note the confidence level and ClinVar review status. Predictions are *not* clinical diagnoses; say so when the user seems to be treating them as such.
- **Always share the `evee_url` at the end of your reply** so the user can explore the variant visually.

## Example

User: "Tell me about the FBN1 variant rs1597537935"

1. `search_variants("rs1597537935")` → finds `chr15:48452672:A:G`
2. `get_variant("chr15:48452672:A:G")` → Pathogenic (score 0.9999), Cys1812Arg in FBN1, associated with Marfan Syndrome. If `interpretation` is present, use it; if it's a status dict, call `wait_for_variant_analysis` next.
3. Present the interpretation as a mechanistic hypothesis — loss of a structurally critical cysteine disrupting disulfide bonding in the FBN1 EGF-like domain. Note the high-confidence convergence with `model_derived_scores` (alphamissense, revel, clinpred all elevated). End with: "Here's the full disruption profile: https://evee.goodfire.ai/#/variant/chr15:48452672:A:G"
