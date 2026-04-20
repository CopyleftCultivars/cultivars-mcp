"""
EVEE MCP Server — Evo Variant Effect Explorer

Provides tools for querying the EVEE API, which offers interpretable variant
effect predictions from Evo 2 genomic foundation model embeddings for 4.2 million
ClinVar variants.

Reference: Pearce et al., "EVEE: Interpretable variant effect prediction from
genomic foundation model embeddings" (2026). https://evee.goodfire.ai
"""

import time

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://xix0d0o8le.execute-api.us-east-1.amazonaws.com"

mcp = FastMCP(
    "evee",
    instructions=(
        "EVEE (Evo Variant Effect Explorer) provides variant effect predictions "
        "for 4.2 million ClinVar variants using Evo 2 genomic foundation model "
        "embeddings. It predicts pathogenicity (0.997 AUROC on ClinVar SNVs), "
        "generates disruption profiles showing which biological annotations are "
        "affected, and produces AI-generated mechanistic interpretations.\n\n"
        "Typical workflow:\n"
        "1. search_variants — autocomplete-style lookup returning up to 6 matches. "
        "Pass ONLY a gene name (e.g. 'BRCA1'), rsID (e.g. 'rs1234'), or numeric "
        "ClinVar variation ID (e.g. '655979'). Do NOT add keywords like "
        "'pathogenic' or 'missense' — it is a lookup, not a text search. "
        "WARNING: gene-name queries return an adjacent-position autocomplete slice "
        "of that gene's variants, NOT the top-pathogenicity variants. Do not infer "
        "the gene's pathogenic landscape from these 6 rows. For a specific variant, "
        "query by rsID or ClinVar variation ID.\n"
        "2. get_variant — clinical significance, scores, and interpretation "
        "(auto-triggers on-demand analysis when not yet stored)\n"
        "3. compare_variants — side-by-side for 2-10 variants in one call\n"
        "4. get_variant_disruptions — understand WHY a variant is predicted "
        "pathogenic/benign; optional category filter\n"
        "5. get_variant_annotations — deep dive into specific annotation categories\n"
        "6. wait_for_variant_analysis — poll on-demand interpretation to "
        "completion for variants where the stored result isn't ready\n\n"
        "Variant IDs use the format chr:pos:ref:alt.\n\n"
        "IMPORTANT — coordinate convention: EVEE stores variants at 0-based "
        "positions, while ClinVar VCFs, HGVS genomic notation, and standard VCF "
        "files are 1-based. To look up a ClinVar variant at 1-based position P, "
        "query chr{c}:{P-1}:{ref}:{alt}. Example: ClinVar ID 41812 is stored in "
        "EVEE as 'chr17:43092918:G:A' even though CLNHGVS says g.43092919G>A. "
        "For indels the offset is NOT a simple -1 — EVEE stores indels in "
        "VCF-anchored bi-allelic form (e.g. CFTR ΔF508 is chr7:117559589:ATCT:A, "
        "several positions upstream of the ClinVar HGVS position). When you only "
        "have a ClinVar variation ID or rsID, prefer search_variants over "
        "building the ID by hand — it returns the correctly-formed variant_id."
    ),
)

# ---------------------------------------------------------------------------
# Annotation category mapping
# ---------------------------------------------------------------------------

# Maps user-facing category names to the key prefixes used in the API response.
ANNOTATION_CATEGORIES = {
    "amino_acid": {
        "prefixes": ["amino_acid_"],
        "description": "Predicted amino acid probabilities at the variant position (20 standard amino acids)",
    },
    "atacseq": {
        "prefixes": ["atacseq_"],
        "description": "ATAC-seq chromatin accessibility peaks across 7 tissues/cell types",
    },
    "ccre": {
        "prefixes": ["ccre_"],
        "description": "ENCODE candidate cis-regulatory element annotations (enhancers, promoters, CTCF, etc.)",
    },
    "chipseq": {
        "prefixes": ["chipseq_"],
        "description": "ChIP-seq histone modification peaks (H3K27ac, H3K27me3, H3K36me3, H3K4me1, H3K4me3, H3K9me3) across tissues",
    },
    "chromhmm": {
        "prefixes": ["chromhmm_"],
        "description": "ChromHMM chromatin state predictions (active TSS, bivalent, enhancer, repressed, transcribed) across 10 cell types",
    },
    "elm": {
        "prefixes": ["elm_"],
        "description": "Eukaryotic Linear Motif predictions (DOC, LIG, MOD, TRG)",
    },
    "fstack": {
        "prefixes": ["fstack_"],
        "description": "FStack functional state predictions (enhancer, promoter, quiescent, repressed, transcribed)",
    },
    "protein_feature": {
        "prefixes": ["in_"],
        "description": "Protein structural features from UniProt (domain, disulfide bond, transmembrane, coiled coil, active/binding sites, etc.)",
    },
    "interpro": {
        "prefixes": ["interpro_"],
        "description": "InterPro protein domain family predictions (117 domain types)",
    },
    "genomic_feature": {
        "prefixes": ["is_"],
        "description": "Binary genomic feature flags (splice donor/acceptor, CpG island, repeat elements, exon-intron boundaries, etc.)",
    },
    "ptm": {
        "prefixes": ["ptm_"],
        "description": "Post-translational modification predictions (acetylation, glycosylation, methylation, phosphorylation, sumoylation, ubiquitination)",
    },
    "region": {
        "prefixes": ["region_"],
        "description": "Genomic region annotations (CDS, intron, 3'UTR, 5'UTR)",
    },
    "secondary_structure": {
        "prefixes": ["secondary_structure_"],
        "description": "Protein secondary structure predictions (C=coil, E=strand, H=helix)",
    },
}


def _get_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30)


def _evee_url(variant_id: str | None) -> str | None:
    return f"https://evee.goodfire.ai/#/variant/{variant_id}" if variant_id else None


def _fetch_analysis(client: httpx.Client, variant_id: str, timeout: float | None = None) -> dict:
    """Hit /variants/{id}/analysis once.

    Returns one of:
      {"status": "complete", "result": {...}}         — interpretation ready
      {"status": "queued", "retry_after": N}          — generation in progress
      {"status": "not_found"}                         — variant missing
    """
    kwargs = {"timeout": timeout} if timeout is not None else {}
    resp = client.get(f"/variants/{variant_id}/analysis", **kwargs)
    if resp.status_code == 404:
        return {"status": "not_found"}
    resp.raise_for_status()
    return resp.json()


def _interpretation_from_analysis(analysis: dict) -> dict | None:
    """Build the curated `interpretation` dict from an /analysis response."""
    if analysis.get("status") != "complete":
        return None
    r = analysis.get("result") or {}
    return {
        "summary": r.get("summary"),
        "mechanism": r.get("mechanism"),
        "key_evidence": r.get("key_evidence"),
        "confidence": r.get("confidence"),
    }


def _extract_annotations(data: dict, category: str | None) -> dict:
    """Extract ref/var annotation pairs from the variant response, optionally filtered by category."""
    if category and category not in ANNOTATION_CATEGORIES:
        return {"error": f"Unknown category '{category}'. Valid categories: {', '.join(sorted(ANNOTATION_CATEGORIES))}"}

    if category:
        prefixes = ANNOTATION_CATEGORIES[category]["prefixes"]
    else:
        prefixes = None

    ref_keys = sorted(k for k in data if k.startswith("ref_") and not k[0].isdigit())
    annotations = {}
    for rk in ref_keys:
        name = rk[4:]
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue
        vk = f"var_{name}"
        ref_val = data.get(rk)
        var_val = data.get(vk)
        if ref_val is not None and var_val is not None:
            delta = round(var_val - ref_val, 4) if isinstance(ref_val, (int, float)) and isinstance(var_val, (int, float)) else None
            annotations[name] = {"ref": ref_val, "alt": var_val, "delta": delta}

    return annotations


def _extract_top_disruptions(data: dict, top_n: int, category: str | None = None) -> list[dict]:
    """Extract and rank annotation disruptions by magnitude of change."""
    filter_prefixes = ANNOTATION_CATEGORIES[category]["prefixes"] if category else None
    ref_keys = sorted(k for k in data if k.startswith("ref_") and not k[0].isdigit())
    disruptions = []
    for rk in ref_keys:
        name = rk[4:]
        if filter_prefixes and not any(name.startswith(p) for p in filter_prefixes):
            continue
        vk = f"var_{name}"
        mk = f"maxpos_{name}"
        ref_val = data.get(rk)
        var_val = data.get(vk)
        if ref_val is None or var_val is None:
            continue
        if not isinstance(ref_val, (int, float)) or not isinstance(var_val, (int, float)):
            continue
        delta = var_val - ref_val
        abs_delta = abs(delta)
        if abs_delta < 0.001:
            continue

        cat = "other"
        for cat_name, cat_info in ANNOTATION_CATEGORIES.items():
            if any(name.startswith(p) for p in cat_info["prefixes"]):
                cat = cat_name
                break

        disruptions.append({
            "annotation": name,
            "category": cat,
            "ref": round(ref_val, 4),
            "alt": round(var_val, 4),
            "delta": round(delta, 4),
            "abs_delta": round(abs_delta, 4),
            "max_disruption_position": data.get(mk),
        })

    disruptions.sort(key=lambda x: x["abs_delta"], reverse=True)
    return disruptions[:top_n]


def _curate_variant_summary(data: dict) -> dict:
    """Curate the massive variant response into a structured summary for LLM consumption."""
    summary = {}

    # --- Identity ---
    variant_id = data.get("variant_id")
    summary["variant_id"] = variant_id
    summary["evee_url"] = _evee_url(variant_id)
    summary["rs_id"] = data.get("rs_id")
    summary["chrom"] = data.get("chrom")
    summary["pos"] = data.get("pos")
    summary["ref"] = data.get("ref")
    summary["alt"] = data.get("alt")
    summary["variation_id"] = data.get("variation_id")

    # --- Gene ---
    summary["gene"] = data.get("gene_name")
    summary["gene_id"] = data.get("gene_id")
    summary["gene_strand"] = data.get("gene_strand")
    summary["loeuf"] = data.get("loeuf")
    summary["loeuf_label"] = data.get("loeuf_label")

    # --- Consequence & HGVS ---
    summary["consequence"] = data.get("consequence_display") or data.get("consequence")
    summary["hgvs_coding"] = data.get("hgvsc")
    summary["hgvs_protein"] = data.get("hgvsp")
    summary["hgvs_coding_short"] = data.get("hgvsc_short")
    summary["hgvs_protein_short"] = data.get("hgvsp_short")
    summary["vep_transcript_id"] = data.get("vep_transcript_id")
    summary["vep_protein_id"] = data.get("vep_protein_id")
    summary["exon"] = data.get("exon")
    summary["vep_impact"] = data.get("vep_impact")

    # --- Clinical ---
    summary["clinical_label"] = data.get("label_display") or data.get("label")
    summary["pathogenicity_score"] = data.get("pathogenicity") or data.get("score")
    summary["disease"] = data.get("disease")
    summary["clinical_features"] = data.get("clinical_features")
    summary["significance"] = data.get("significance")
    summary["review_status"] = data.get("review_status")
    summary["stars"] = data.get("stars")
    summary["n_submissions"] = data.get("n_submissions")
    summary["last_evaluated"] = data.get("last_evaluated")
    summary["origin"] = data.get("origin")
    summary["acmg"] = data.get("acmg")

    # --- Model-derived scores (EVEE heads / probes aligned to external predictors) ---
    scores = {}
    score_keys = {
        "evee_pathogenic": "eff_pathogenic",
        "evee_splice_disrupting": "eff_splice_disrupting",
        "alphamissense": "eff_alphamissense_c",
        "cadd": "eff_cadd_c",
        "revel": "eff_revel_c",
        "sift": "eff_sift_c",
        "polyphen": "eff_polyphen_c",
        "spliceai_max": "eff_spliceai_max_c",
        "clinpred": "eff_clinpred_c",
        "bayesdel": "eff_bayesdel_c",
        "vest4": "eff_vest4_c",
        "blosum62": "eff_blosum62_c",
        "grantham": "eff_grantham_c",
        "charge_altering": "eff_charge_altering",
        "hydrophobicity": "eff_hydrophobicity_c",
        "mpc": "eff_mpc_c",
        "mcap": "eff_mcap_c",
        "metalr": "eff_metalr_c",
        "mvp": "eff_mvp_c",
        "primateai": "eff_primateai_c",
        "deogen2": "eff_deogen2_c",
        "mutpred": "eff_mutpred_c",
        "cadd_wg": "eff_cadd_wg_c",
    }
    for name, key in score_keys.items():
        val = data.get(key)
        if val is not None:
            scores[name] = val
    summary["model_derived_scores"] = scores

    # --- Reference predictor scores (raw values from source databases, when present) ---
    gt_scores = {}
    gt_keys = {
        "alphamissense": "gt_alphamissense_c",
        "cadd": "gt_cadd_c",
        "revel": "gt_revel_c",
        "sift": "gt_sift_c",
        "spliceai_max": "gt_spliceai_max_c",
    }
    for name, key in gt_keys.items():
        val = data.get(key)
        if val is not None:
            gt_scores[name] = val
    if gt_scores:
        summary["reference_predictor_scores"] = gt_scores

    # --- Protein domains ---
    summary["domains"] = data.get("domains")

    # --- AI interpretation (from stored processed_result) ---
    pr = data.get("processed_result")
    if pr and isinstance(pr, dict) and pr.get("status") == "ok":
        summary["interpretation"] = {
            "summary": pr.get("summary"),
            "mechanism": pr.get("mechanism"),
            "key_evidence": pr.get("key_evidence"),
            "confidence": pr.get("confidence"),
        }
    else:
        summary["interpretation"] = None

    # --- Similar variants ---
    neighbors = data.get("neighbors", [])
    if neighbors:
        summary["similar_variants"] = [
            {
                "variant_id": n.get("id"),
                "gene": n.get("gene"),
                "consequence": n.get("consequence_display"),
                "label": n.get("label_display") or n.get("label"),
                "score": n.get("score"),
                "similarity": n.get("similarity"),
            }
            for n in neighbors
        ]

    return summary


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_variants(query: str) -> list[dict] | dict:
    """Autocomplete-style variant lookup (up to 6 matches) in the EVEE database.

    The query must be ONE of these exact types — do NOT combine them or add
    extra words like "pathogenic":
      - A gene name: "BRCA1", "TP53", "FBN1"
      - An rsID: "rs1597537935"
      - A ClinVar variation ID (numeric): "655979"

    Returns at most 6 autocomplete-style matches. Pagination/limit params are
    ignored by the backend.

    WARNING: a gene-name query returns an adjacent-position autocomplete slice
    of variants in that gene — NOT the top-pathogenicity variants of the gene.
    Do not infer the gene's pathogenic landscape from these 6 rows. To look up
    a specific variant, query by rsID or ClinVar variation ID.

    Use this as the starting point to find variant IDs for the other tools.
    """
    q = query.strip().rstrip(";,.:|/\\")
    if not q:
        return []
    if any(ch.isspace() for ch in q):
        return {"error": f"search_variants expects a single bare identifier. Got {query!r} with internal whitespace — pass one of: a gene symbol (e.g. 'BRCA1'), an rsID (e.g. 'rs1597537935'), or a numeric ClinVar variation ID (e.g. '655979'). Do not add qualifiers."}
    if q.lower() == "rs" or (q.lower().startswith("rs") and len(q) <= 4 and not q[2:].isdigit()):
        return {"error": f"search_variants got {query!r}, which looks like a truncated rsID. Supply a full rsID (e.g. 'rs1597537935')."}

    with _get_client() as client:
        resp = client.get("/variants/search", params={"q": q})
        resp.raise_for_status()
        results = resp.json()

    return [
        {
            "variant_id": r["v"],
            "gene": r.get("g"),
            "clinical_label": r.get("l"),
            "pathogenicity_score": r.get("s"),
            "consequence": r.get("c"),
        }
        for r in results
    ]


@mcp.tool()
def get_variant(variant_id: str) -> dict:
    """Get comprehensive information about a specific genetic variant.

    Returns clinical significance, model-derived scores from EVEE's heads
    (aligned to AlphaMissense, CADD, REVEL, SIFT, etc.), reference predictor
    scores from external databases when present, gene constraint (LOEUF), HGVS
    notation, disease associations, protein domains, and the AI-generated
    mechanistic interpretation.

    If the stored interpretation isn't ready, this tool hits EVEE's on-demand
    /analysis endpoint once: if generation has already completed, the fresh
    interpretation is returned inline; otherwise the response carries an
    `interpretation = {status: queued/processing, detail: ...}` entry and you
    should call `wait_for_variant_analysis` to poll until it finishes.

    Args:
        variant_id: Variant identifier in chr:pos:ref:alt format
                    (e.g. "chr17:43092918:G:A" for BRCA1 ClinVar ID 41812).
                    NOTE: EVEE uses 0-based positions; ClinVar/VCF/HGVS are
                    1-based. Subtract 1 from ClinVar pos for SNVs; for indels
                    the offset varies — prefer search_variants.
    """
    with _get_client() as client:
        resp = client.get(f"/variants/{variant_id}")
        if resp.status_code == 404:
            return {"error": "Variant not found", "variant_id": variant_id}
        resp.raise_for_status()
        data = resp.json()

        summary = _curate_variant_summary(data)

        if summary["interpretation"] is None:
            analysis = _fetch_analysis(client, variant_id)
            interp = _interpretation_from_analysis(analysis)
            if interp:
                summary["interpretation"] = interp
            else:
                summary["interpretation"] = {
                    "status": analysis.get("status", "unavailable"),
                    "detail": "Interpretation is being generated on-demand. Call wait_for_variant_analysis to poll for completion.",
                }

    return summary


@mcp.tool()
def wait_for_variant_analysis(
    variant_id: str,
    timeout_seconds: float = 20.0,
    poll_interval_seconds: float = 2.0,
) -> dict:
    """Poll EVEE's on-demand interpretation until it completes or times out.

    Use this when `get_variant` reports `interpretation.status` as queued or
    processing. Returns the same curated variant summary as `get_variant`, plus
    a `wait_status` entry with attempts / elapsed_seconds. If the deadline
    hits before completion, call this tool again to keep polling.

    Args:
        variant_id: Variant identifier in chr:pos:ref:alt format.
        timeout_seconds: Maximum wall-clock time to wait (clamped to [1, 60]).
        poll_interval_seconds: Delay between polls (clamped to [0.5, 10]).
    """
    timeout_seconds = min(max(timeout_seconds, 1.0), 60.0)
    poll_interval_seconds = min(max(poll_interval_seconds, 0.5), 10.0)

    started = time.monotonic()
    deadline = started + timeout_seconds
    attempts = 0
    analysis: dict = {"status": "unavailable"}

    def _remaining() -> float:
        return max(0.0, deadline - time.monotonic())

    with _get_client() as client:
        resp = client.get(f"/variants/{variant_id}", timeout=max(1.0, _remaining()))
        if resp.status_code == 404:
            return {"error": "Variant not found", "variant_id": variant_id}
        resp.raise_for_status()
        data = resp.json()

        while True:
            remaining = _remaining()
            if remaining <= 0:
                break
            try:
                analysis = _fetch_analysis(client, variant_id, timeout=max(1.0, remaining))
            except httpx.TimeoutException:
                analysis = {"status": "queued"}
                break
            attempts += 1
            if analysis.get("status") in ("complete", "not_found"):
                break
            if _remaining() <= 0:
                break
            time.sleep(min(poll_interval_seconds, _remaining()))

    if analysis.get("status") == "not_found":
        return {"error": "Variant not found", "variant_id": variant_id}

    summary = _curate_variant_summary(data)
    interp = _interpretation_from_analysis(analysis)
    if interp:
        summary["interpretation"] = interp
        wait_status = "complete"
    else:
        summary["interpretation"] = {
            "status": analysis.get("status", "unavailable"),
            "detail": "Still generating after timeout. Call wait_for_variant_analysis again to continue polling.",
        }
        wait_status = "timeout"

    summary["wait_status"] = {
        "status": wait_status,
        "attempts": attempts,
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    return summary


@mcp.tool()
def get_variant_disruptions(variant_id: str, top_n: int = 15, category: str | None = None) -> dict:
    """Get the top biological annotation disruptions for a variant.

    Shows which molecular features are most affected by the variant, ranked by
    magnitude of change. Each disruption shows what the Evo 2 model predicts
    for the reference vs. alternate allele across 325 biological annotations
    spanning protein structure, chromatin state, regulatory elements, splice
    sites, and more.

    This is the key tool for understanding WHY a variant is predicted pathogenic
    or benign — e.g., a splice-site variant might show large disruptions in
    splice donor/acceptor annotations, while a missense variant might show
    disruptions in protein domain and secondary structure annotations.

    Categories: amino_acid, atacseq, ccre, chipseq, chromhmm, elm, fstack,
    protein_feature, interpro, genomic_feature, ptm, region, secondary_structure.

    Args:
        variant_id: Variant identifier in chr:pos:ref:alt format.
        top_n: Number of top disruptions to return (default 15, max 100).
        category: Optional category filter — restrict ranking to one category
                  (e.g. to see only splice-related disruptions:
                  category='genomic_feature').
    """
    if category is not None and category not in ANNOTATION_CATEGORIES:
        return {"error": f"Unknown category '{category}'. Valid categories: {', '.join(sorted(ANNOTATION_CATEGORIES))}"}

    top_n = min(max(1, top_n), 100)

    with _get_client() as client:
        resp = client.get(f"/variants/{variant_id}")
        if resp.status_code == 404:
            return {"error": "Variant not found", "variant_id": variant_id}
        resp.raise_for_status()
        data = resp.json()

    disruptions = _extract_top_disruptions(data, top_n, category)

    vid = data.get("variant_id")
    result = {
        "variant_id": vid,
        "evee_url": _evee_url(vid),
        "gene": data.get("gene_name"),
        "consequence": data.get("consequence_display"),
        "pathogenicity_score": data.get("pathogenicity") or data.get("score"),
        "disruption_count": len(disruptions),
        "disruptions": disruptions,
    }
    if category:
        result["category"] = category
    return result


@mcp.tool()
def get_variant_annotations(
    variant_id: str,
    category: str | None = None,
) -> dict:
    """Get detailed annotation probe values for a variant.

    Returns the Evo 2 model's predicted annotation values for both the
    reference and alternate allele across 325 biological annotations. Each
    annotation shows ref (reference allele prediction), alt (alternate allele
    prediction), and delta (alt - ref).

    Use this for deep analysis when you need the full picture — e.g., all
    chromatin marks across tissues, all amino acid probabilities, or every
    protein feature prediction. For a quick ranked view of what's most
    disrupted, use get_variant_disruptions instead.

    Args:
        variant_id: Variant identifier in chr:pos:ref:alt format.
        category: Optional filter. One of: amino_acid, atacseq, ccre, chipseq,
                  chromhmm, elm, fstack, protein_feature, interpro,
                  genomic_feature, ptm, region, secondary_structure.
                  Omit to get ALL annotations.
    """
    with _get_client() as client:
        resp = client.get(f"/variants/{variant_id}")
        if resp.status_code == 404:
            return {"error": "Variant not found", "variant_id": variant_id}
        resp.raise_for_status()
        data = resp.json()

    annotations = _extract_annotations(data, category)
    if "error" in annotations:
        return annotations

    vid = data.get("variant_id")
    result = {
        "variant_id": vid,
        "evee_url": _evee_url(vid),
        "gene": data.get("gene_name"),
        "consequence": data.get("consequence_display"),
        "annotation_count": len(annotations),
    }

    if category:
        result["category"] = category
        result["category_description"] = ANNOTATION_CATEGORIES[category]["description"]

    result["annotations"] = annotations

    if not category:
        result["available_categories"] = {
            name: {"description": info["description"], "count": sum(1 for a in annotations if any(a.startswith(p) for p in info["prefixes"]))}
            for name, info in ANNOTATION_CATEGORIES.items()
        }

    return result


@mcp.tool()
def compare_variants(variant_ids: list[str]) -> dict:
    """Compare multiple variants side-by-side.

    Fetches clinical label, pathogenicity score, gene, HGVS protein, consequence,
    and the top-1 disruption for each. Use when the user asks to contrast,
    rank, or compare 2+ variants, instead of looping get_variant.

    Args:
        variant_ids: List of variant IDs in chr:pos:ref:alt format (max 10).
    """
    if len(variant_ids) > 10:
        return {"error": "compare_variants accepts at most 10 variant IDs per call."}

    rows = []
    with _get_client() as client:
        for vid in variant_ids:
            resp = client.get(f"/variants/{vid}")
            if resp.status_code == 404:
                rows.append({"variant_id": vid, "error": "Variant not found"})
                continue
            resp.raise_for_status()
            data = resp.json()
            top = _extract_top_disruptions(data, 1)
            top_disruption = None
            if top:
                t = top[0]
                top_disruption = {"annotation": t["annotation"], "category": t["category"], "delta": t["delta"]}
            rid = data.get("variant_id")
            rows.append({
                "variant_id": rid,
                "evee_url": _evee_url(rid),
                "gene": data.get("gene_name"),
                "clinical_label": data.get("label_display") or data.get("label"),
                "pathogenicity_score": data.get("pathogenicity") or data.get("score"),
                "hgvs_protein_short": data.get("hgvsp_short"),
                "consequence": data.get("consequence_display") or data.get("consequence"),
                "top_disruption": top_disruption,
            })

    return {"variants": rows}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
