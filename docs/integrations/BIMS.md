# BIMS — Breeding Information Management System (integration context)

> Research note saved for a potential **BIMS ⇄ cultivars-mcp** integration.
> Status: **context only** — no integration code exists yet. Captured June 2026.

## What BIMS is

**BIMS (Breeding Information Management System)** is a free, secure, online breeding-data
management system that lets individual breeders **store, manage, archive, and analyze their
own private phenotypic + genotypic breeding data**, and optionally integrate it with public
genomic/genetic data — while keeping **full ownership and control** of their private data.

It is the first publicly available system to let an individual breeder combine private
phenotype/genotype data with public data and retain control of the private layer.

### Who develops it

- **Mainlab Bioinformatics, Washington State University (WSU)** — led by Dorrie (Dorrie) Main.
  (Note: the request referred to "UW" — the developer is **WSU**, not the University of
  Washington. Worth confirming if a different "UW" system was meant.)
- Funded via **USDA NIFA NRSP10** and **USDA SCRI** (Genome Database for Rosaceae projects).
- Official site: <https://www.breedwithbims.org/> · Program: <https://www.nrsp10.org/bims>
- Reference paper: Jung et al. 2021, *Database*, "The Breeding Information Management System
  (BIMS): an online resource for crop breeding" — doi:10.1093/database/baab054
  (PMC8378516, PMID 34415997).

## Technical architecture

| Layer | Detail |
|---|---|
| Platform | **Tripal** extension module (ontology-based open-source toolkit for biological databases) |
| CMS / framework | **Drupal 7** (Tripal 3); Tripal 4 moves to Drupal 9/10 |
| Database | **PostgreSQL**, storing data in **Chado**'s **Natural Diversity (ND) module** (large-scale phenotype/genotype + germplasm/location/marker/sequence integration) |
| Field collection | Integrates the **Field Book** Android app (open-source field phenotype collection; Google Play) — replaces paper field books, cuts transcription error |
| Interoperability | **BrAPI** (Breeding API) — currently **V1**; V2 planned. Module: <https://github.com/tripal/brapi> (v4.x is a Drupal 8+ rewrite) |
| Source | Open source; installable in **any** Tripal database |

### Core data types managed
Cross records · performance/phenotype data · pedigree · geographical/location data ·
image-based data · genotyping/marker data · germplasm/accession · trait & trial metadata.

### Private vs public data model
Each breeder's private phenotype/genotype data is access-controlled and owned by the breeder;
it can be **integrated with** public genomic/genetic/breeding data inside the host Tripal DB
**without** surrendering control. This ownership-first stance is philosophically close to
cultivars-mcp's ODbL ledger + Ed25519 attribution (breeder controls their own contribution).

### Where BIMS is deployed
Genome Database for Rosaceae (GDR), CottonGen, Citrus Genome Database, Pulse Crop Database
(PulseDB / KnowPulse), Genome Database for Vaccinium (GDV). Installable in others built on
Tripal: TreeGenes, Cucurbit Genomics DB, PeanutBase, CarrotDB, etc.

## Why this matters for cultivars-mcp

BIMS is the **established, standards-based counterpart** to the community-science write layer
this repo just added (`submit_phenotype_observation`, `query_community_phenotypes`, the
ODbL phenotype ledger). Both manage breeder-owned phenotype/genotype observations. The natural
bridge between them is **BrAPI** and the **Field Book** data format.

### Concrete integration surfaces (candidates, not commitments)

1. **BrAPI export/import bridge.** Map the cultivars-mcp observation schema (v1.0 YAML) to
   BrAPI v2 `observations` / `observationunits` / `germplasm` so observations can flow into a
   BIMS/Tripal instance and back. BrAPI v2 is the target since BIMS is moving toward it.
   - cultivars-mcp `trait_category` / `measurement` → BrAPI observation variable + value.
   - cultivars-mcp `accession_id` → BrAPI `germplasmDbId` (and our GRIN `resolve_accession`
     already targets formal germplasm IDs, which aligns with BIMS germplasm records).
2. **Field Book interop.** Field Book exports/imports a defined trait + observation format;
   `export_offline_snapshot` could emit a Field Book–compatible trait file so an offline
   grower's Field Book session round-trips into the ledger (online↔offline, our existing theme).
3. **Germplasm/accession alignment.** `resolve_accession` (GRIN-Global) and BIMS germplasm
   records both key on formal accession IDs — a shared anchor for joining the two systems.
4. **Ownership/attribution parity.** BIMS = breeder-controlled private data; cultivars-mcp =
   Ed25519-signed, ODbL-licensed contributions. An integration should preserve both ownership
   models (don't force private BIMS data into the open ledger without explicit breeder opt-in).

### Open questions to resolve before building
- Which **BrAPI version** to target first (BIMS is V1 now, V2 soon) — recommend building to **V2**.
- Direction of flow: cultivars-mcp **→** BIMS (publish observations), BIMS **→** cultivars-mcp
  (ingest public breeding data), or bidirectional.
- Is the relevant deployment one of the public Tripal DBs (GDR/CottonGen/PulseDB/GDV) or a
  self-hosted BIMS instance? That changes auth + endpoint specifics.
- Boundary with the Copyleft Cultivars ecosystem: BIMS is desktop/web breeding management;
  TinyLLamaFarmer is the offline field tool; cultivars-mcp is the genomics + ledger layer.

## Sources
- Jung et al. 2021, *Database* — <https://academic.oup.com/database/article/doi/10.1093/database/baab054/6355633> (PMC8378516, PMID 34415997)
- NRSP10 BIMS program — <https://www.nrsp10.org/bims>
- Breed with BIMS (official) — <https://www.breedwithbims.org/> · BrAPI page: <https://www.breedwithbims.org/bims_brapi>
- PulseDB BIMS manual — <https://www.pulsedb.org/BIMS_manual>
- GDV BIMS manual — <https://www.vaccinium.org/BIMS_manual>
- Tripal BrAPI module — <https://github.com/tripal/brapi> · Tripal org — <https://github.com/tripal>
- CottonGen BIMS dataset — <https://data.nal.usda.gov/dataset/cottongen-breeding-information-management-system-bims>
