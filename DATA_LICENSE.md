# Data License — Open Database License (ODbL) v1.0

**This license applies to community-contributed *data*, not to the code.**

- The **code** in this repository (`server.py`, tests, tooling) is licensed
  under **Apache License 2.0** — see [`LICENSE`](LICENSE).
- The **data** under [`phenotypes/`](phenotypes/) — every community phenotype
  observation submitted through `submit_phenotype_observation` — and any
  aggregated derivative database built from it, is licensed under the
  **Open Database License (ODbL) v1.0**.

## Why a different license for data?

A permissive license (like Apache 2.0 or MIT) on *data* allows anyone —
including biotech firms — to incorporate the commons into a proprietary,
closed database and never give anything back. That is **enclosure**: the
community contributes observations, and the value is privatized.

The ODbL is a **copyleft** license for data. It requires that:

1. **Attribution** — you must credit the contributors and this database.
2. **Share-Alike** — if you publicly use an adapted version of the database,
   or produce a derived database, you must offer that derived database under
   the ODbL as well.
3. **Keep-Open** — if you redistribute the database (or a derivative) with
   technical restrictions (e.g. DRM), you must also provide an unrestricted
   version.

This is the same model **OpenStreetMap** uses to keep the world's largest
open geographic database open. It ensures the plant-genomics commons that
grower-scientists, heritage breeders, and resource-limited farmers build
together **stays open** — for them and for everyone after them.

## Full text

The canonical ODbL v1.0 text is published by Open Data Commons:
<https://opendatacommons.org/licenses/odbl/1-0/>

## Contributor terms

By submitting an observation to the ledger you affirm that:

- You have the right to contribute the data.
- You license the contributed data under ODbL-1.0.
- Any contents of individual observation records (the *contents*, as distinct
  from the *database*) that constitute factual measurements are dedicated to
  the public domain to the extent possible, while the **database** as a whole
  is protected by the ODbL share-alike terms above.

Optional Ed25519 signatures (`provenance.submitter_pubkey` / `signature`)
attach a verifiable, pseudonymous attribution to your contribution. They are
a scientific-credit mechanism, **not** a financial instrument — this project
does not use tokens, cryptocurrency, or on-chain storage.
