# Phenotype Ledger

This directory is the **community phenotype ledger** — the write layer that
turns cultivars-mcp from a read-only genomics query tool into a participatory
community-science instrument.

Observations are written here by the `submit_phenotype_observation` MCP tool
and read back by `query_community_phenotypes` and `estimate_gwas_power`.

## License

All data in this directory is licensed **ODbL-1.0** (open-data copyleft) — see
[`../DATA_LICENSE.md`](../DATA_LICENSE.md). This is distinct from the Apache-2.0
**code** license. Derivative databases must stay open.

## Layout

```
phenotypes/
└── {species}/
    └── {accession_id}/
        └── {trait}_{date}.yaml
```

For example:

```
phenotypes/oryza_sativa/IRGC_12345/submergence_tolerance_2026-05-28.yaml
```

## Schema (v1.0)

```yaml
schema_version: "1.0"
accession_id: "IRGC_12345"          # Formal ID (GRIN/IRRI/USDA) or 'community:{name}'
common_name: "Gobol Sail"           # Farmer-provided name
species: "oryza_sativa"             # Ensembl Plants species string
trait_category: "submergence_tolerance"  # Atlas or organellar trait category
trait_atlas_gene: "SUB1A"           # Canonical gene from the atlas (optional)
measurement:
  type: "binary"                    # binary | continuous | categorical
  value: true
  unit: null
  protocol: "14_day_submergence_field"
environment:
  agroecological_zone: "south_asia_tropical_humid"
  flood_depth_cm: 40
  duration_days: 14
  season: "kharif_2026"
provenance:
  submitter_pubkey: "ed25519:..."   # optional, encouraged
  signature: "..."                  # detached Ed25519 sig over canonical form
  location_proof: null              # optional privacy proof (reserved)
  ipfs_cid: null                    # populated by pin_observation_to_ipfs
license: "ODbL-1.0"
submitted: "2026-05-28"
```

## Why YAMLs aren't all committed

`.gitignore` excludes `phenotypes/**/*.yaml`. Observations accumulate locally
and are contributed deliberately via **pull request**, not bulk-committed. This
keeps attribution and review in the loop and lets growers run a private local
ledger before deciding what to share.

## Integrity

Sign observations with an Ed25519 keypair to attach a verifiable, pseudonymous
attribution (`provenance.submitter_pubkey` + `signature`). Verify any record
with `verify_observation_integrity`. This is scientific credit, **not** a
financial instrument — no tokens, no chain.
