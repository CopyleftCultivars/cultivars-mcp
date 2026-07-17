# Templates for field-data collection

Starter files for collecting phenotypes and contributing them to the Cultivars
phenotype ledger. Full walkthrough: [`../docs/FIELD_DATA_GUIDE.md`](../docs/FIELD_DATA_GUIDE.md).

All trait names in these templates are chosen to map **1:1** onto the Cultivars
trait atlas, so imports need no extra configuration. A CI test
(`test_shipped_*` in `tests/test_server.py`) imports every file here on each run,
so these stay in sync with the importer and the atlas.

## Field Book (`fieldbook/`)

| File | What it is | Where it goes |
|---|---|---|
| `cultivars_field_template.csv` | Field/plot layout — `unique_id`, `row` (primary order), `column` (secondary order), plus `accession` / `species` / `common_name` metadata | Import **into Field Book** (Fields → Import) to create your field |
| `cultivars_traits.trt` | 16 traits named to match the atlas, with sensible Field Book formats | Import **into Field Book** (Traits → Import), or recreate from the guide's reference table |
| `example_fieldbook_export_long.csv` | An example of what Field Book **exports** after collection (database/long format) | Feed **into Cultivars** via `import_fieldbook_csv` to see the flow |

## BIMS (`bims/`)

| File | What it is | Where it goes |
|---|---|---|
| `phenotype_long_form_bims_template.csv` | BIMS long form — `trait` + `value` columns | `import_bims_submission` |
| `phenotype_bims_wide_template.csv` | BIMS wide form — `#`-prefixed trait columns, one row per accession | `import_bims_submission` (auto-detects `#` columns) |

## License

Template **data** (the example rows) is illustrative. Real observations you
contribute are licensed **ODbL-1.0** — see [`../DATA_LICENSE.md`](../DATA_LICENSE.md).
