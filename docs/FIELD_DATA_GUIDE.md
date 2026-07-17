# Collecting field data and contributing it to Cultivars

This guide walks a grower or breeder from **collecting phenotypes in the field**
to **contributing them to the open Cultivars phenotype ledger**. Two collection
paths are covered:

- **Path A — the Field Book app** (Android; works offline in the field)
- **Path B — BIMS** (Breeding Information Management System; web)

Both end at the same place: the `import_fieldbook_csv` / `import_bims_submission`
tools map your data into the ledger, where it becomes tamper-evident, citable,
and aggregatable for community GWAS.

```
   FIELD                          IMPORT                         LEDGER
┌───────────┐  export CSV   ┌───────────────────┐   write    ┌──────────────┐
│ Field Book├──────────────►│ import_fieldbook_ │───────────►│ phenotypes/  │
│  (Android)│               │ csv (dry-run→write)│            │  *.yaml      │
└───────────┘               └───────────────────┘            │  CHAIN.jsonl │
┌───────────┐  export CSV   ┌───────────────────┐   write    │  *.ots       │
│   BIMS    ├──────────────►│ import_bims_      │───────────►│              │
│   (web)   │               │ submission        │            └──────┬───────┘
└───────────┘               └───────────────────┘                   │ PR
                                                                     ▼
                                                          open commons (ODbL-1.0)
```

Everything we ship for this lives in [`../templates/`](../templates/).

---

## Path A — Field Book app

### 1. Install Field Book

Install **Field Book** (free, open-source) from
[Google Play](https://play.google.com/store/apps/details?id=com.fieldbook.tracker)
or build it from [PhenoApps/Field-Book](https://github.com/PhenoApps/Field-Book).
Docs: <https://docs.fieldbook.phenoapps.org>.

### 2. Load the field layout (creates your "field")

Copy our starter layout onto the device and import it:

- File: [`templates/fieldbook/cultivars_field_template.csv`](../templates/fieldbook/cultivars_field_template.csv)
- In Field Book: **Fields → Import → Local**, pick the file, then map columns:
  - **Unique ID** → `unique_id`
  - **Primary Order** → `row`
  - **Secondary Order** → `column`
- The extra columns (`accession`, `species`, `common_name`) ride along as plot
  metadata and show up in the InfoBars.

Replace the example rows with your own plots. Keep `unique_id` unique across all
your fields, and keep `accession` as a formal ID (GRIN/IRRI/USDA, e.g.
`IRGC_121316`) where you have one — otherwise use `community:your_name`.

> Field Book requires three columns — a unique ID, a primary order, and a
> secondary order — and forbids the characters `/ ? < > \ * | "` in headers and
> filenames.

### 3. Load the traits

- File: [`templates/fieldbook/cultivars_traits.trt`](../templates/fieldbook/cultivars_traits.trt)
- In Field Book: **Traits → Import**, pick the file.
- These 16 traits are named to map **1:1** onto the Cultivars trait atlas, so no
  extra configuration is needed at import time.

If your Field Book version rejects the `.trt` import (the app prefers trait files
it exported itself), just **create the traits by hand** from the
[trait reference table](#trait-reference-table) below — the names and formats are
all you need.

### 4. Collect

Score plots in the field as usual. The trait *formats* were chosen to match how
these traits are actually measured (a boolean "survived", a numeric height, a
categorical tolerance class, etc.).

### 5. Export

**Export → CSV → Database (long) format.** This produces one row per observation
(`unique_id, trait, value, timestamp, ...`), which the importer auto-detects.

> Prefer **database (long)** over **table (wide)** format: the wide export needs
> you to name the trait columns explicitly at import, and some Field Book
> versions drop plot metadata from the long export — that's fine here because you
> pass `species` at import time (see next step).

### 6. Import into Cultivars

Ask your MCP client (Claude Desktop / Claude Code with the Cultivars server
connected) to import the file. It calls:

```
import_fieldbook_csv(
    csv_content_or_path = "/path/to/your_export.csv",
    species = "oryza_sativa",     # applied to all rows; or add a species column
    write = False,                # DRY RUN first
)
```

Review the report — `imported` (with content hashes) and `skipped` (with
reasons). Common fixes:

- **"trait did not map"** → add a `trait_map`, e.g.
  `trait_map = {"SubTol": "submergence_tolerance"}`.
- **"no species"** → pass `species="..."` or add a `species` column.

When it looks right, re-run with `write = True` to write the YAML records.

A worked example you can try immediately:
[`templates/fieldbook/example_fieldbook_export_long.csv`](../templates/fieldbook/example_fieldbook_export_long.csv).

### 7. Make it tamper-evident and contribute

- `append_observation_to_chain(path)` — link each record into the hash-chain.
- `anchor_ledger_head()` — timestamp the whole chain into Bitcoin via
  OpenTimestamps (free, no wallet).
- Commit the new files under `phenotypes/` and open a pull request against
  `CopyleftCultivars/cultivars-mcp`. Merged observations feed community GWAS
  (`estimate_gwas_power`).

---

## Path B — BIMS

BIMS can **generate** Field Book trait/field files for you and **import** the
data back; it also exports phenotype tables directly. Either export both work:

- **Long form** (`phenotype_long_form_bims`): a `trait` column + a `value` column.
- **Wide form** (`phenotype_bims`): trait descriptors as column headings with a
  **`#` prefix**, one row per accession.

Import with:

```
import_bims_submission(csv_content_or_path = "/path/to/bims_export.csv",
                       species = "oryza_sativa", write = False)
```

The importer recognises the BIMS identifier columns (`accession`, `unique_id`,
`primary_order`, `secondary_order`), auto-detects long form, and auto-detects the
`#`-prefixed trait columns in wide form — so **neither template needs extra
arguments.** Reference templates:

- [`templates/bims/phenotype_long_form_bims_template.csv`](../templates/bims/phenotype_long_form_bims_template.csv)
- [`templates/bims/phenotype_bims_wide_template.csv`](../templates/bims/phenotype_bims_wide_template.csv)

Then chain, anchor, and PR exactly as in Path A step 7.

---

## Trait reference table

The 16 traits in `cultivars_traits.trt`. **Trait name** is what appears on the
Field Book button; it maps to the atlas **category** automatically. Recreate any
of these by hand in Field Book if the `.trt` import doesn't take.

| Trait name (Field Book) | Field Book format | Values / range | → Atlas category | Ledger measurement |
|---|---|---|---|---|
| drought tolerance | categorical | susceptible / moderate / tolerant | drought_tolerance | categorical |
| salt tolerance | categorical | susceptible / moderate / tolerant | salt_tolerance | categorical |
| cold tolerance | categorical | susceptible / moderate / tolerant | cold_tolerance | categorical |
| heat tolerance | categorical | susceptible / moderate / tolerant | heat_tolerance | categorical |
| submergence tolerance | boolean | true / false (survived) | submergence_tolerance | binary |
| plant height | numeric | 0–500 cm | plant_height_dwarfing | continuous |
| tiller branching | counter | integer count | tiller_branching | continuous |
| flowering photoperiod | numeric | 0–400 (days to 50% flowering) | flowering_photoperiod | continuous |
| grain quality | categorical | poor / fair / good / excellent | grain_quality | categorical |
| mycorrhizal symbiosis | boolean | true / false (colonized) | mycorrhizal_symbiosis | binary |
| nitrogen use efficiency | categorical | low / moderate / high | nitrogen_use_efficiency | categorical |
| root architecture | categorical | shallow / intermediate / deep | root_architecture | categorical |
| aluminum tolerance | categorical | susceptible / moderate / tolerant | aluminum_tolerance | categorical |
| hemp compliance | percent | 0–100 (% total THC dry wt) | hemp_compliance | continuous |
| cannabinoid biosynthesis | percent | 0–100 (% dry wt) | cannabinoid_biosynthesis | continuous |
| cannabis terpene profile | categorical | myrcene / limonene / caryophyllene / terpinolene / pinene / linalool | cannabis_terpene_profile | categorical |

Want a trait that isn't listed? The atlas has **35 categories** — run
`list_trait_categories`, add a Field Book trait with a matching name, and (if the
name isn't an obvious match) pass a `trait_map` at import.

---

## Infrastructure — what you need to run this

The short version: **a laptop and a phone are enough.** Nothing here requires a
cloud server, a database engine, a GPU, or any paid service.

### Minimum (individual grower)

| Piece | Requirement |
|---|---|
| **Cultivars MCP server** | Python ≥ 3.10 with `mcp`, `httpx`, `pyyaml`, `cryptography`. Runs on a laptop, a Raspberry Pi, or a small VPS. It's a local **stdio** MCP server — no inbound ports, no web server to expose. |
| **MCP client** | Any MCP-compatible client — Claude Desktop, Claude Code, or an IDE plugin — to drive the tools conversationally. |
| **Network** | Outbound HTTPS only, for live database queries (Ensembl Plants, UniProt, Europe PMC, STRING, Kannapedia, GRIN) and OpenTimestamps calendars. The ledger write path and hash-chain work fully offline. |
| **Field data collection** | An **Android** device for Field Book, or a web browser + a **BIMS** account for the BIMS path. |
| **Contributing** | `git` + a GitHub account to open pull requests. No server-side credentials are needed at runtime. |

Resource footprint is tiny: it idles at rest and uses a few hundred MB of RAM
during a query. No persistent daemon beyond the MCP process your client starts.

### Optional add-ons

| Feature | Needs |
|---|---|
| **IPFS pinning** (`pin_observation_to_ipfs`) | A local [kubo](https://docs.ipfs.tech/install/) node (`ipfs daemon`) at `127.0.0.1:5001`, or a remote gateway via `CULTIVARS_IPFS_API`. Degrades gracefully if absent. |
| **OpenTimestamps verification/upgrade** | The reference `ots` client — `pip install "cultivars-mcp[anchor]"` (pulls `opentimestamps-client`). Creating proofs needs only outbound HTTPS; `ots upgrade`/`ots verify` confirm against Bitcoin via public block explorers (no node required). |
| **Offline field use** | `export_offline_snapshot` packages a trait's genomics into a portable JSON for the offline [TinyLLamaFarmer](https://github.com/CopyleftCultivars/TinyLLamaFarmer) assistant. |

### Shared / community deployment (optional)

For a lab or co-op running a shared ledger rather than a personal one:

- Point `CULTIVARS_LEDGER_DIR` at a git working copy so observations accumulate
  in one place and are reviewed via PR.
- Run a periodic job (e.g. a nightly cron) that calls `anchor_ledger_head` so the
  growing chain is regularly timestamped into Bitcoin.
- Optionally run or subscribe to an IPFS pinning service for durable,
  content-addressed storage of observations and any associated VCFs.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `CULTIVARS_LEDGER_DIR` | Where observation YAMLs + `CHAIN.jsonl` live | `./phenotypes` |
| `CULTIVARS_SNAPSHOTS_DIR` | Offline-bridge snapshot output | `./snapshots` |
| `CULTIVARS_IPFS_API` | kubo HTTP API endpoint | `http://127.0.0.1:5001` |
| `CULTIVARS_OTS_CALENDARS` | Comma-separated OpenTimestamps calendars | two public pools |

---

## Troubleshooting

- **Rows skipped as "trait did not map"** — the field trait name didn't match an
  atlas category. Pass `trait_map={"Your Name": "atlas_category"}`, or rename the
  Field Book trait to match the reference table.
- **Rows skipped as "no species"** — pass `species="..."` to the import call, or
  add a `species`/`crop` column to the CSV.
- **Rows skipped as "empty value"** — expected for blank cells in a sparse wide
  matrix; only filled cells become observations.
- **BIMS wide file not detected** — ensure trait columns carry the `#` prefix
  (e.g. `#plant height`); that's how `import_bims_submission` finds them.
- **Formal vs. informal accessions** — use a GRIN/IRRI/USDA ID where possible;
  `resolve_accession` can turn a folk seed name into a formal accession, which
  improves downstream GWAS aggregation.
