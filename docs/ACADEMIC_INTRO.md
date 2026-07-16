# Cultivars MCP — an introduction for researchers and educators

> **A short, shareable brief for plant-science, breeding, and bioinformatics
> faculty.** It explains what the tool is, why it may be useful in a research or
> teaching setting, and how on-farm data collection (Field Book, BIMS) connects
> to an open, auditable phenotype commons.

<!--
COLLABORATORS: this is a scaffold. The structure, links, and technical claims
are filled in from the codebase; the framing prose in the "In one paragraph"
and "Why it may be useful" sections is meant to be tightened by whoever is
writing the PSU-facing intro. Anything in <!-- --> comments is guidance, not
content — delete before sharing. Placeholders to complete are marked TODO.
-->

## In one paragraph

Cultivars MCP is an open-source [Model Context Protocol](https://modelcontextprotocol.io)
server that gives an AI assistant structured, live access to **five public
plant-genomics databases** and a curated trait atlas — and, beyond read-only
lookup, a **write path** for community phenotype observations. It lets a
researcher (or a student, or a grower) ask questions like *"which genes underlie
submergence tolerance in rice, and what are the maize orthologs?"* in plain
language and get answers grounded in Ensembl Plants, UniProt, and the primary
literature, with provenance attached. It is part of the
[Copyleft Cultivars](https://github.com/CopyleftCultivars) ecosystem, whose
mission is to keep plant-genetics tooling in the open-data commons rather than
behind proprietary enclosure.

## Why it may be useful in research and teaching

<!-- TODO(collaborator): sharpen these to the specific PSU departments/courses
you're reaching out to — e.g. plant breeding, agronomy, plant pathology,
bioinformatics, horticulture. -->

- **A single natural-language interface over federated databases.** Instead of
  learning each database's REST API, a user composes cross-database workflows
  (gene → orthologs → variants → literature) conversationally. Useful as a
  teaching aid and as a rapid-hypothesis tool.
- **Honest, reproducible framings.** Every response surfaces its source, its
  coverage limits, and evidence tier (e.g. UniProt-curated vs. GWAS-mapped).
  Variant effects come from Ensembl VEP (a rule-based predictor), not a black-box
  model — the tool states this explicitly.
- **A participatory community-science layer.** Growers and field trials can
  contribute phenotype observations that aggregate toward community GWAS; the
  tool includes a power estimator that turns "my village's 12 rice varieties"
  into a concrete recruitment target for detecting a locus.
- **Open licensing designed to keep derivatives open** (see *Licensing* below).

## The five live databases

| Source | What it provides |
|---|---|
| **Ensembl Plants** | Gene models, variants (VEP), orthology (Compara), sequence — ~80 species |
| **UniProt** | Manually-curated protein entries + evidence for the trait atlas |
| **Europe PMC** | Primary literature search for a given gene |
| **STRING-db** | Protein–protein interaction networks |
| **Medicinal Genomics Kannapedia** | Cannabis strain genomics (not in Ensembl Plants) |

Plus a curated **trait atlas** (30+ categories, ~123 genes, ~73% verified
against UniProt with PubMed citations) spanning natural-farming-relevant traits:
drought and salt tolerance, mycorrhizal symbiosis, nitrogen-use efficiency,
flowering/photoperiod, and more.

## From the field to an open, auditable commons

This is the part most relevant to breeders and field researchers, and the newest
bridge in the ecosystem:

1. **Collect in the field.** Phenotypes are recorded with the open-source
   [Field Book app](https://github.com/PhenoApps/Field-Book) or submitted through
   **BIMS** (a Breeding Information Management System), aligned with the
   [CopyleftCultivars/bims-cultivar-submission](https://github.com/CopyleftCultivars)
   pipeline.
2. **Import into the ledger.** `import_fieldbook_csv` / `import_bims_submission`
   map those tabular exports directly into the phenotype ledger's schema —
   validating, mapping trait names to the atlas, and (optionally) writing
   observation records. A dry-run reports exactly what would import and what was
   skipped and why.
3. **Make it tamper-evident and citable.** Each observation is content-hashed and
   can be Ed25519-signed for pseudonymous scientific attribution. Observations
   link into an append-only **hash-chain**, and the chain head can be anchored to
   the Bitcoin blockchain via [OpenTimestamps](https://opentimestamps.org) — a
   free, token-less *proof of existence*. The result is a phenotype commons whose
   integrity anyone can verify independently, with no trust in the maintainers.

> **On "crypto":** the ledger is *cryptographic*, not a *cryptocurrency*. There is
> no token, coin, wallet, or fee. Hash-chaining + OpenTimestamps make the data
> auditable; they do not financialize it. Contributed data stays under an
> open-data copyleft license so derivative databases must remain open.

## Trying it

Cultivars MCP runs as a standard MCP server (Python ≥3.10). It can be connected
to any MCP-compatible client — for example Claude Desktop or Claude Code — with a
few lines of config. See the repository [README](../README.md) and
[USER_GUIDE](USER_GUIDE.md) for installation, the full tool reference, and worked
example recipes. No API keys or accounts are required to use the read-only
genomics tools.

## Licensing

- **Code:** Apache-2.0 — permissive, standard for research software.
- **Contributed data:** ODbL-1.0 (Open Database License) — an open-data *copyleft*
  license chosen so that derivative databases must themselves stay open,
  preventing enclosure of the community-contributed commons. See
  [`../DATA_LICENSE.md`](../DATA_LICENSE.md).

<!-- Note: the project is also exploring a purpose-restricted data license
building on the Hippocratic License; that work is tracked separately and is not
reflected here yet. -->

## Collaborating with us

We would welcome collaboration with faculty and students on: trait-atlas
curation (adding well-evidenced genes for orphan and heritage crops), field-data
pipelines, and validating the community-GWAS workflow against real breeding
programs.

- **Repository / issues:** <https://github.com/CopyleftCultivars/cultivars-mcp>
- **Contributing guide:** [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- **Contact:** <!-- TODO(collaborator): add the preferred contact name/email and
  Discord/Patreon links you want to share with PSU faculty. -->

## How to cite

<!-- TODO(collaborator): add a preferred citation / DOI once available. A
CITATION.cff in the repo root would let GitHub render a "Cite this repository"
button. -->

*Citation forthcoming.* For now, please cite the repository URL and commit hash.
