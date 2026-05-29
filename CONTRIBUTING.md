# Contributing to Cultivars MCP

Plant genomics moves. Heritage breeders learn new things every season. Living-database APIs change. We add trait categories in response to grower-scientist questions, not in response to what gets the most academic citations.

If you're reading this, you probably want to do one of these:

- [Add a new trait category to the atlas](#1-add-a-new-trait-category)
- [Fix a gene that should resolve in Ensembl but doesn't](#2-fix-an-atlas-genes-resolution)
- [Re-run the atlas evidence audit](#3-regenerate-atlas_evidencejson)
- [Add a plant species to the STRING / NCBI taxon table](#4-add-a-new-species-to-_ncbi_taxon_ids)
- [Add a primary literature citation to an atlas gene](#5-add-primary-literature-citations)
- [Run the test suite locally](#6-run-the-tests)
- [Write up a new workflow recipe](#7-add-a-workflow-recipe)
- [Plug in another living-document database](#8-add-a-new-external-data-source)

If your contribution is something not on this list, open an issue and we'll figure it out together.

---

## 1. Add a new trait category

The atlas lives in `server.py` as the `TRAIT_ATLAS` dict. Each top-level key is a trait category (snake_case). Each entry has:

```python
"<trait_key>": {
    "description": "<one-sentence summary of the trait>",
    "natural_farming_relevance": "<why this matters to KNF / regenerative / smallholder agriculture; one paragraph>",
    "ensembl_caveat": "<optional — only if the canonical species isn't in Ensembl Plants>",
    "genes": [
        {
            "symbol": "<gene symbol from primary literature>",
            "alias": "<optional — alternate names>",
            "ensembl_id": "<optional — Ensembl Plants stable ID; preferred when known>",
            "characterized_in": "<Ensembl species name, e.g. arabidopsis_thaliana>",
            "function": "<one paragraph summary of what the gene does>",
            "primary_ref": "<optional — canonical characterization paper, e.g. 'Shi et al. 2000 PNAS 97:6896 (PMID 10823923)'>",
            "evidence_level": "<optional — knockout_phenotype | transgenic_complementation | qtl_mapped | gwas_locus | biochemical_activity | sequence_similarity_only>",
            "note": "<optional — flag literature-handle entries that don't resolve by symbol in Ensembl>",
        },
        # ... more genes
    ],
},
```

### Style guidelines for atlas entries

- **Lead the description with what the trait IS,** not why it matters. Save the "why" for `natural_farming_relevance`.
- **Pick well-characterized genes.** If you can't cite a primary characterization paper, it's a literature handle — mark it with `note`.
- **Use Ensembl Plants species names** (`oryza_sativa`, not `Oryza sativa`). Run `list_plant_species` if unsure.
- **`primary_ref` format**: "Authors YEAR Journal Vol:PageOrArticleID (PMID NNNNNNNN) — short summary of what the paper proved."
- **Acknowledge what you don't know.** Better to flag a `note` saying "literature handle, not directly resolvable in Ensembl" than to assert a wrong stable ID.

### After adding a category

1. Run pytest to confirm the atlas shape still validates:
   ```bash
   pytest tests/ -v
   ```
2. If you added genes with `ensembl_id` fields, re-run the audit (see §3).
3. Add example tests if your category has novel structure.

---

# ORPHAN CROPS BOUNTY

The atlas has historically over-indexed on the three most-funded model systems
(Arabidopsis, rice, maize). Copyleft Cultivars's actual audience grows **orphan
crops**: teff, fonio, cowpea, pigeon pea, finger millet, amaranth, enset, grass
pea, bambara groundnut, quinoa. These feed billions but are systematically
underrepresented in public genomics. **Closing this gap is the single
highest-value data contribution you can make.**

### The bounty list

Open requests live in [`WANTED_TRAITS.yaml`](WANTED_TRAITS.yaml) and are surfaced
at runtime by the `list_orphan_crop_requests` MCP tool. Each entry names a crop,
trait, candidate genes, and the minimum evidence tier we'll accept.

We seed-funded the category with five initial entries already in `TRAIT_ATLAS`:
`teff_drought_tolerance`, `cowpea_heat_tolerance`,
`finger_millet_calcium_accumulation`, `pigeon_pea_salinity_tolerance`,
`amaranth_c4_photosynthesis`. Use these as templates.

### How to claim a bounty

1. Pick an entry from `WANTED_TRAITS.yaml` (or propose a new orphan crop).
2. On the corresponding GitHub Issue, comment to claim it. Maintainers label
   these issues **`bounty`**; if no issue exists, open one with that label.
3. Open a PR that:
   - Adds the trait category to `TRAIT_ATLAS` in `server.py` following the
     schema in §1 above.
   - Sets `status: claimed` (then `merged` on merge) for the entry in
     `WANTED_TRAITS.yaml`.
   - Includes at least one gene with a `primary_ref` citation.

### Evidence-tier requirement for orphan-crop entries

Because most orphan crops are **not in Ensembl Plants**, symbol resolution
won't work — entries are literature handles and MUST carry honest provenance:

- **Minimum tier: `gwas_mapped`** (a published GWAS/QTL associating the locus
  with the trait) for new bounty entries. `sequence_similarity_only` is
  acceptable only as a *secondary* gene alongside at least one mapped gene.
- Add an `ensembl_caveat` on the category and a `note` on each gene stating it
  is an orphan-crop literature handle (e.g. *"Cajanus cajan genome published
  (Varshney 2012) but not in Ensembl Plants"*).
- Prefer the published reference genome's gene IDs where one exists; cite the
  genome paper.

This keeps the orphan-crop atlas honest about the difference between "we have a
mapped locus" and "this looks similar to a known gene in another species."

---

## 2. Fix an atlas gene's resolution

If a gene in the atlas returns `error` from `lookup_gene`, you have three paths:

### Option A — the gene has a different display name in Ensembl

Ensembl's display name sometimes diverges from the literature canonical name (e.g., PIN2 → "EIR1", ARF7 → "NPH4", OsHKT1;5 → "SKC1"). Fix:

```python
{"symbol": "EIR1", "alias": "PIN2", "ensembl_id": "AT5G57090", ...}
```

The atlas symbol becomes the Ensembl name; the literature name moves into `alias`. The audit treats matches on either as hits.

### Option B — the gene has a stable ID but isn't symbol-indexed

Some plant genes (especially in non-Arabidopsis species) don't have curated gene symbols in Ensembl. Add `ensembl_id` directly:

```python
{"symbol": "SUB1A", "ensembl_id": "Os09g0286600", "characterized_in": "oryza_sativa", ...}
```

### Option C — the gene is a real literature handle that doesn't resolve at all

Some classic genes (barley HVA1, sorghum SbMATE) just aren't symbol-indexed in current Ensembl Plants releases. Flag with `note`:

```python
{
    "symbol": "HVA1",
    "characterized_in": "hordeum_vulgare",
    "function": "...",
    "primary_ref": "Hong et al. 1988 ...",
    "note": "Literature handle — barley HVA1 doesn't resolve by symbol in Ensembl Plants; cited via the source literature.",
}
```

Literature handles are honest and useful. Don't fabricate stable IDs that "look right" — the audit will catch it.

---

## 3. Regenerate `atlas_evidence.json`

The evidence cache lives at the repo root and is loaded at module init. After adding new atlas entries with `ensembl_id` fields, regenerate:

```bash
python evals/atlas_audit.py
```

This runs `lookup_gene_evidence` against every atlas gene with an `ensembl_id` (or a resolvable symbol) and writes the audit output to `evals/atlas_evidence.json`. Then copy the relevant subset to the root `atlas_evidence.json` (the file the server loads). The audit script handles this end-to-end — read `evals/atlas_audit.py` for details.

**Audit runtime: ~80–250 seconds** depending on Ensembl REST response times (it issues one xref call per gene, capped at ~15 req/sec by Ensembl's soft limit).

The `test_atlas_evidence_drift_warning` pytest will flag if the atlas grows new `ensembl_id` entries that aren't represented in the cache — you'll know immediately if a re-audit is needed.

---

## 4. Add a new species to `_NCBI_TAXON_IDS`

STRING-db queries require an NCBI taxon ID rather than the Ensembl species name. The `_NCBI_TAXON_IDS` table in `server.py` maps them. To add a species:

```python
_NCBI_TAXON_IDS = {
    ...
    "your_species_name": 9999,  # NCBI taxon ID
}
```

Look up the NCBI taxon ID at https://www.ncbi.nlm.nih.gov/taxonomy. Common ones already present: Arabidopsis (3702), rice (4530), maize (4577), Cannabis (3483), Medicago (3880). Add a test in `test_server.py::test_string_cannabis_is_supported`-style to lock in the mapping.

---

## 5. Add primary literature citations

The `primary_ref` field on an atlas gene cites the seminal characterization paper. Format:

```
"Authors YEAR Journal Vol:PageOrArticleID (PMID NNNNNNNN) — short summary."
```

Examples in the existing atlas:
- `"Shi et al. 2000 PNAS 97:6896 (PMID 10823923) — sos1 mutant + cloning."`
- `"Sasaki et al. 2002 Nature 416:701 (PMID 11961545) — sd1 cloning; the IR8 dee-geo-woo-gen-derived loss-of-function allele behind the rice Green Revolution."`

For genes with multiple foundational papers, separate with `.` and list 2–3:

```
"Liu et al. 1998 Plant Cell 10:1391 (PMID 9707537) — original characterization. Kasuga et al. 1999 Nat Biotechnol 17:287 (PMID 10096295) — transgenic overexpression confers drought + freezing tolerance."
```

The `test_primary_ref_present_on_canonical_genes` test enforces that the seminal entries (DREB1A, SOS1, SUB1A, PSTOL1, NRT1.1B, SD1, TB1, ALMT1, BADH2) keep their `primary_ref` field. Don't remove it without updating the test.

---

## 6. Run the tests

```bash
# Set up a venv
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dev dependencies
pip install -e ".[dev]"

# Run the full mocked suite (no network needed)
pytest tests/ -v
```

Target: all tests should pass in ~1.5 seconds. The mocked suite uses `httpx.MockTransport` so no live API calls.

For live integration testing against real APIs (slower, requires internet):

```bash
PYTHONIOENCODING=utf-8 python evals/all_tools_live.py
PYTHONIOENCODING=utf-8 python evals/workflow_integration.py
PYTHONIOENCODING=utf-8 python evals/cross_source_consistency.py
PYTHONIOENCODING=utf-8 python evals/robustness.py
```

These scripts live in `evals/` (gitignored — measurement artifacts, regeneratable).

---

## 7. Add a workflow recipe

If you've found a useful multi-tool sequence answering a grower-scientist question, add it to `docs/USER_GUIDE.md` under "Workflow recipes". Format:

```markdown
### Recipe N: "[plain-language question a grower would ask]"

```
tool_call_1(args)
   → expected result shape
tool_call_2(args)
   → ...
```
```

We organize recipes by user persona (cannabis grower / hemp compliance / heritage corn breeder / natural-farming researcher). Add yours to the appropriate persona's section.

---

## 8. Add a new external data source

Cultivars currently integrates 5 living-document APIs. To add a 6th:

1. **Decide it's worth adding.** Criteria: free, no-auth (or trivially-auth), public-sector or open-data, covers plant-genomics or plant-agronomy data we don't already serve.
2. **Add the base URL constant** at the top of `server.py`:
   ```python
   YOUR_API_BASE_URL = "https://api.example.org"
   ```
3. **Add a per-API client-factory helper** mirroring `_uniprot_client` / `_europepmc_client` / `_string_client`:
   ```python
   def _your_api_client() -> httpx.Client:
       return httpx.Client(base_url=YOUR_API_BASE_URL, headers={"Accept": "application/json"}, timeout=30)
   ```
4. **Route requests through `_get_with_retry`** so Retry-After backoff applies uniformly:
   ```python
   with _your_api_client() as client:
       resp = _get_with_retry(client, "/endpoint", params={...})
   ```
5. **Add a `@mcp.tool()` wrapper** with clear docstring + structured response. Surface honest fields: source attribution, follow-up URLs, fallback when the API doesn't have data.
6. **Add mocked tests** using the `_patch_helper(monkeypatch, "_your_api_client", ...)` pattern.
7. **Update**:
   - `README.md` — add to the "What it does" tool inventory
   - `docs/USER_GUIDE.md` — add to the tool reference + an example workflow
   - `SKILL.md` — add to the routing decision table + the `allowed-tools` frontmatter
   - `CHANGELOG.md` — record what + why
   - `NOTICE` — credit the data source

8. **Be conservative with rate limits.** If the upstream documents a limit (STRING-db asks ≤1 req/s on the public endpoint), respect it in defaults.

### Examples of data sources that would fit

- **MaizeGDB API** for richer maize annotation beyond Ensembl xrefs
- **Cannabis Genome Database** if a programmatic interface becomes available
- **NCBI Datasets API v2** for genome assembly metadata (Cannabis CS10, Jamaican Lion, NAM founders)
- **Plant Reactome REST** for pathway membership queries beyond the Ensembl xref
- **GrainGenes** for wheat/barley/oat curation
- **Sol Genomics Network** for Solanaceae

### Examples of data sources we deliberately don't integrate

- **Phytozome** (JGI) — paywalled behind a login; against CC's open-access principles
- **TAIR** — became paywalled in 2024 (Phoenix Bioinformatics); we use Ensembl + Araport instead
- Proprietary breeder-tool APIs

---

## Style guidelines for code contributions

- **No comments explaining what code does.** Well-named identifiers do that. Comments should explain WHY a non-obvious thing is non-obvious.
- **Honest error messages.** "EuropePMC returned 503" beats "Internal Error". Surface upstream context.
- **Test seam helpers.** New API clients use the `_<name>_client()` factory pattern so `monkeypatch.setattr(server, "_<name>_client", factory)` works in tests.
- **No silent fallbacks.** If a tool can't resolve something, return a structured `{"error": "...", "hint": "..."}` dict — don't return empty data that looks valid.
- **Cite primary literature in atlas entries.** "I read about this gene somewhere" isn't a citation. PMID is.

---

## Project values

Reminders we put in PR templates:

- **Open over proprietary.** If a public-sector resource exists, use it. Avoid login-gated tools.
- **Heritage and crop-diversity over industrial monoculture.** Default examples should lean toward smallholder-relevant crops (rice, sorghum, common bean, cassava, finger millet) alongside Arabidopsis.
- **Honest about gaps.** When Ensembl doesn't have data, say so. When a gene is a literature handle, say so.
- **Genomics is one lens.** Documentation should not promise that this tool replaces farmer observation, indigenous knowledge, or on-farm trials.
- **The literature is alive.** Prefer live queries (Europe PMC, UniProt direct) over baking citations into static catalogs. Static catalogs go stale.

---

## Code of conduct

Be kind to grower-scientists, breeders, and seed-keepers — they're often working without a degree, without lab access, and with stakes that matter for their families' food security. Be kind to public-sector curators (Ensembl, UniProt, NCBI staff) — they maintain the infrastructure we depend on without venture funding. Be kind to each other.

Caleb DeLeeuw and the Copyleft Cultivars team will moderate contributions in line with Copyleft Cultivars Nonprofit's mission.

---

🌱 Plant genetics, like seeds, should circulate freely.
