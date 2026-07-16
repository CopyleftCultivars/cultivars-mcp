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
├── CHAIN.jsonl                         # append-only hash-chain spine (see below)
├── CHAIN.head.{seq}.ots                # OpenTimestamps proof for a chain head
└── {species}/
    └── {accession_id}/
        ├── {trait}_{date}.yaml
        └── {trait}_{date}.yaml.ots     # optional per-record timestamp proof
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

## Integrity & attribution

Sign observations with an Ed25519 keypair to attach a verifiable, pseudonymous
attribution (`provenance.submitter_pubkey` + `signature`). Verify any record
with `verify_observation_integrity`. This is scientific credit — a CV tied to a
keypair, **not** money.

## The cryptographic ledger

The YAMLs above are individually content-hashed and optionally signed. Two tools
turn that pile of files into a tamper-evident, independently auditable ledger —
this is the "crypto ledger, not just YAML" spine:

1. **Hash-chain (`CHAIN.jsonl`).** `append_observation_to_chain` links each
   observation into an append-only log where every entry commits to the previous
   one (`prev_entry_hash → entry_hash`), exactly like Git or a Merkle log. Any
   later edit to a chained observation — or any attempt to reorder or splice
   history — breaks the chain and is caught by `verify_ledger_chain`. No network,
   no fees; the chain is a plain JSONL file you can read and audit by hand.

2. **OpenTimestamps anchor (Bitcoin).** `anchor_ledger_head` (or, per-record,
   `anchor_observation_timestamp`) submits a hash to the free public
   OpenTimestamps calendar servers and saves a detached `.ots` proof. Because the
   chain head commits to the entire history, one anchor timestamps the whole
   ledger. This proves *when* the data existed by committing its hash into the
   Bitcoin blockchain — a one-way proof-of-existence. Verify structure with
   `verify_timestamp`; for full Bitcoin confirmation run the reference client
   (`pip install opentimestamps-client`, then `ots upgrade` / `ots verify`).

### Crypto**graphic**, not crypto**currency**

To be explicit: there is **no token, no coin, no wallet, no gas, nothing to
buy**. "Crypto" here means cryptography — SHA-256 hash-chaining and a
proof-of-existence timestamp. OpenTimestamps uses Bitcoin only as a public,
append-only clock; contributing to or verifying the ledger costs nothing and
requires no account. The data stays licensed **ODbL-1.0** so derivative
databases must stay open — the anchor makes the commons *auditable*, not
*financialized*.
