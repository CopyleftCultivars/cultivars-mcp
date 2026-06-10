# 🌱 Introducing **Cultivars** — the open plant-genomics tool for grower-scientists

*A note from Copyleft Cultivars Nonprofit to our Patreon members*

---

Hi friends,

We built something we're excited to share with you.

You already know our flagship project, **TinyLLamaFarmer** — the offline natural-farming AI assistant for the field. And **gemma4-natural-farming**, our open-weight model trained on Korean Natural Farming and JADAM literature. Both of those are for **when you're in the field, off-grid, hands in the soil.**

This one is different. **Cultivars** is the **desk-side companion** — for the moments when you sit down with your morning coffee and want to actually understand *why* something in your garden is doing what it's doing. Why does this landrace tolerate the drought better than the seed-catalog hybrid? Why does this hemp cultivar test below 0.3% THC consistently while your neighbor's hot-tests every season? What's actually happening at the molecular level when a maize plant senses fall armyworm and ramps up its defenses?

Cultivars is a software tool that connects you to the open plant-genomics literature — the same databases that university researchers and seed banks use — and answers those questions with citations.

## Why we built it

The original tool this is forked from was for **human** clinical-variant analysis — predicting whether a mutation in a person's DNA might cause disease. It's a beautiful piece of software. But its data only covers humans, and the closer you look at plant-genomics tooling, the more you notice something off: most of the well-funded software in this space is built for industrial breeders and corporate seed companies. It's locked behind logins, or it's paywalled, or it doesn't cover the crops smallholder farmers actually grow.

Meanwhile, the **public** plant-genomics resources — Ensembl Plants (~80 plant species), UniProt (curated protein function), the European Bioinformatics Institute's literature search, the STRING protein-interaction database, Medicinal Genomics's Kannapedia cannabis-strain database — are all free, all online, all maintained by public-sector scientists. They just aren't easy to use.

So we built a tool that talks to all of them, ties their answers together, and lets a grower-scientist ask a question in plain language and get back an answer with primary-literature citations.

It serves three audiences who matter to us:
- 🌿 **Cannabis & hemp growers** — Type I/II/III chemotype questions, hemp compliance (the THCAS/CBDAS BT/BD allele system), Kannapedia strain lookups, cannabinoid biosynthesis pathway, terpene chemotype profiling.
- 🌽 **Heritage corn & smallholder maize growers** — Quality Protein Maize (Opaque-2), disease resistance (Ht1, Htn1, Rcg1), pest resistance (Mir1-CP for fall armyworm), the 26-line CIMMYT/IITA/Thai NAM founder diversity panel.
- 🌾 **Natural-farming / regenerative researchers across all crops** — drought tolerance gene families, mycorrhizal symbiosis (the SYM pathway), nitrogen-use-efficient varieties (the NRT1.1B indica rice allele, PSTOL1 from Kasalath), aluminum-tolerance for acidic tropical soils, root architecture (DRO1), heritage variety photoperiod adaptation (FT-CO module, Vrn-A1 wheat).

## What it can answer right now

Some real example questions Cultivars answers end-to-end:

> **"I bought hemp seed from a breeder I don't fully trust. How do I tell if it's actually a stable Type III hemp strain or if it might hot-test?"**
> → Cultivars walks through the **BT/BD allele system** at the THCAS/CBDAS locus on cannabis chromosome 6, cites the 2003 de Meijer paper and the 2015 Weiblen paper that genetically characterized the system, and (if the breeder registered the strain) pulls the **live Kannapedia chemotype data** for that specific lineage.

> **"I'm growing a sorghum landrace from my grandmother's village in Kenya. What drought-tolerance genes might be contributing to its resilience, and are there equivalent genes in maize?"**
> → Cultivars surfaces the canonical drought-tolerance gene family (**DREB1A, DREB2A, OST1, RD29A, HVA1, DRO1**) — each with the PubMed-cited paper that originally characterized it — then translates each Arabidopsis-canonical gene into its sorghum and maize orthologs via the Ensembl Compara plant tree. **One command, ~2 seconds.**

> **"What does the canonical Korean Natural Farming idea of 'feeding the indigenous microorganisms' look like at the genetic level — what genes does the plant use to communicate with arbuscular mycorrhizal fungi?"**
> → Cultivars returns the **SYM (symbiosis) pathway**: SYMRK / CCaMK / DMI1 (the calcium-signaling decoder), RAM1 (the arbuscule-branching TF), PT4 (the phosphate transporter the plant uses to receive nutrients from the fungus). Each with a UniProt-curated function statement and primary-literature citations.

> **"What's the most recent (2025/2026) literature on PSTOL1, the rice phosphorus-uptake gene from the Kasalath landrace?"**
> → Cultivars hits Europe PMC live and returns the freshest papers. Not training-data answers — *actual* current literature.

> **"Compare these three cannabis strains I'm thinking about breeding from."**
> → Cultivars pulls all three from Kannapedia in parallel and gives you chemotype, plant sex, Y-ratio, heterozygosity, grower attribution, rarity, and — critically — **which canonical cannabis genes are flagged with variants on multiple of the three strains** (so you can see what allelic ground they share).

## What it deliberately doesn't try to do

We're going to be straight with you about what this tool isn't:

- **It's not offline.** The whole point is that it queries live databases over the internet, so it needs connectivity. That's a real contradiction with our offline-first ethos, and we say so explicitly in the tool itself. The **field** tool is TinyLLamaFarmer; this one is for the desk.

- **It's not a substitute for farmer observation, indigenous knowledge, or on-farm trials.** Genomics is one lens. A landrace that has fed your community for ten generations has already passed an evolutionary test that no SNP panel can replicate. The tool says this in its own documentation — we want the agent calling it to remember.

- **It doesn't make crop recommendations or replace breeder judgment.** It surfaces molecular literature; you decide what to do with it.

- **It's honest about gaps.** Cannabis sativa is not in Ensembl Plants (a historical federal-funding gap; the public-sector plant-genomics infrastructure was built before legalization made cannabis research fundable). Many heritage crops have gene models but no allelic-variation database. The tool doesn't pretend otherwise — when you ask about a gap, it tells you it's a gap and points you at NCBI / Cannabis Genome Database / community resources.

## What's under the hood

19 small, composable tools wrapped around 5 open public databases:

- **Ensembl Plants** — gene models, variants, comparative genomics across ~80 plant species
- **UniProt** — manually-curated protein function statements with GO evidence codes and PubMed citations
- **Europe PMC** — open-access literature search (the "living document" — finds newer papers than my training data)
- **STRING-db** — protein-protein interaction networks (covers Cannabis sativa as taxon 3483, even though Ensembl Plants doesn't)
- **Medicinal Genomics Kannapedia** — public cannabis strain database with chemotype + sex + variant calls + downloadable VCF/BAM

Plus a **curated trait atlas** of 30 natural-farming-relevant gene families spanning 123 genes — drought, salt, cold, heat, submergence, nitrogen, phosphorus, iron uptake, mycorrhizal symbiosis, rhizobial nodulation, root architecture, jasmonate defense, terpene biosynthesis, glucosinolate biosynthesis, flowering, dwarfing, tillering, aluminum tolerance, cannabinoid biosynthesis (THCAS/CBDAS/CBCAS), cannabis terpene chemotype synthases (CsTPS family), hemp compliance, cannabis sex/photoperiod, cannabis disease resistance, maize quality protein (Opaque-2), maize disease resistance (Ht1/Htn1/Rcg1), maize pest resistance (Mir1-CP), C4 photosynthesis, cell-wall biosynthesis, grain quality (Wx/Waxy, BADH2/fgr), and general lepidopteran pest resistance.

**73% of those atlas entries link to a manually-curated UniProt entry** — meaning a trained biocurator has read the primary literature and written a function statement with PubMed citations. You can follow the trail from any gene in the atlas back to the original characterization paper.

## How to use it (technical-ish)

If you have **Claude Code** or **Claude Desktop** installed, you can run Cultivars locally:

```bash
git clone https://github.com/CopyleftCultivars/cultivars-mcp.git
cd cultivars-mcp
uv sync
claude  # opens Claude Code with Cultivars MCP automatically loaded
```

Then ask the agent natural-language questions like the examples above. The agent figures out which tools to call.

For non-technical users we're working on a hosted web interface — please support us on Patreon if you want this to happen faster!

## Where this fits in our work

This is the **third** tool in the Copyleft Cultivars ecosystem:

| Tool | When you use it | Where it runs |
|---|---|---|
| **TinyLLamaFarmer** | In the field, deciding what to do today | On your phone, offline |
| **gemma4-natural-farming** | Studying KNF / regenerative methodology | On your laptop or phone, offline |
| **Cultivars** *(new)* | Researching the molecular biology behind a trait you care about | At your desk, online |

Together they cover the **field → method → molecules** spectrum.

## A request

The atlas is a starting point, not a finished work. If you're a grower-scientist or breeder and you notice we're missing a gene family that matters in your domain — heritage tomato disease resistance, garlic flowering, lettuce bolting under heat, your specific crop's anything — please let us know. We add traits in response to grower questions, not in response to what gets the most academic citations.

Same for Kannapedia integration. If there's a specific Cannabis genomics resource we should be talking to, please tell us. Medicinal Genomics has been generous with their public data and we want to honor that by building tools that make their data more accessible to growers, not by silently scraping at scale.

## Sources we lean on

- 📚 **Ensembl Plants** (Sanger / EMBL-EBI) — https://plants.ensembl.org/
- 📚 **UniProt** (SIB / EMBL-EBI / PIR) — https://www.uniprot.org/
- 📚 **Europe PMC** — https://europepmc.org/
- 📚 **STRING-db** (SIB / EMBL) — https://string-db.org/
- 📚 **Medicinal Genomics Kannapedia** — https://www.kannapedia.net/
- 📚 **MaizeGDB** (USDA) — for the NAM panel + maize genome
- 📚 **3K Rice Genomes Project** — for rice population variation
- 📚 **1001 Genomes Project** (Arabidopsis) — for the model-plant variation backbone
- 📚 **Plant Reactome** (Gramene) — for pathway annotations

All free. All public. All maintained by people doing real public-sector science. We owe them.

---

🌱 — Caleb DeLeeuw and the Copyleft Cultivars team

*Cultivars is open-source, copyleft-licensed software. We don't sell it, we don't gate it, we don't track you. If you want to support this kind of work, [Patreon](https://www.patreon.com/copyleftcultivars) is how. Thank you for being part of this.*
