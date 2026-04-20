# EVEE MCP Server

MCP server for the [EVEE (Evo Variant Effect Explorer)](https://evee.goodfire.ai) API — interpretable variant effect prediction from Evo 2 genomic foundation model embeddings.

EVEE provides pre-computed pathogenicity predictions, disruption profiles, and AI-generated mechanistic interpretations for 4.2 million ClinVar variants. See [Pearce et al. (2026)](https://www.biorxiv.org/content/10.64898/2026.04.10.717844v3) for the full paper.

## Tools

| Tool | Description |
|---|---|
| `search_variants` | Autocomplete-style lookup (≤6 matches) for a gene symbol, rsID, or ClinVar variation ID; useful for finding candidate variant IDs, not an exhaustive gene-wide ranking |
| `get_variant` | Clinical summary, EVEE-derived effect outputs, database comparison scores when present, and the AI-generated mechanistic interpretation (auto-triggers on-demand generation when not yet stored) |
| `wait_for_variant_analysis` | Poll EVEE's on-demand interpretation generation until it completes or times out |
| `compare_variants` | Side-by-side summary (up to 10 variants in one call) — clinical label, pathogenicity, top-1 disruption, HGVS, deep link |
| `get_variant_disruptions` | Top biological annotation disruptions ranked by magnitude, optionally scoped to a category — explains *why* a variant is predicted pathogenic or benign |
| `get_variant_annotations` | Full annotation probe values (325 annotations across 13 categories), optionally filtered by category |

### Annotation categories

`amino_acid`, `atacseq`, `ccre`, `chipseq`, `chromhmm`, `elm`, `fstack`, `protein_feature`, `interpro`, `genomic_feature`, `ptm`, `region`, `secondary_structure`

## Skill

A Claude Code skill lives at `.claude/skills/evee/SKILL.md`. Agents that load it get ~120 lines of guidance on how to use the tools effectively — workflow steps, reliability caveats by variant class, and gotchas (0-based coords, indel VCF anchoring, case-sensitivity).

## Usage

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:goodfire-ai/evee-mcp.git
cd evee-mcp
uv sync
```

### Claude Code

The repo ships a `.mcp.json`; opening the directory triggers the permission prompt:

```bash
claude
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "evee": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/evee-mcp", "python3", "server.py"]
    }
  }
}
```

### Example

> Is the FBN1 variant rs1597537935 pathogenic, and why?

The agent searches, fetches the clinical summary with the AI-generated mechanistic interpretation, and pulls out the top disruption evidence.
