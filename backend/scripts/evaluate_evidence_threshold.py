"""Diagnostic script for calibrating evidence-detection thresholds.

Run from the backend/ directory:
    python -m scripts.evaluate_evidence_threshold

What it does
------------
For each test case it computes:
  • cosine DISTANCE between the query and the passage
    (distance = 1 − cosine_similarity; lower = more similar)
  • bge-reranker-base cross-encoder score

The two thresholds in evidence.py are:
  MAX_VECTOR_DISTANCE   – chunks with distance > this are "low evidence"
  MIN_RERANKER_SCORE    – if best reranker score < this, also "low evidence"

This script prints the actual numbers so you can see where the boundary
really falls and decide whether the current values are too strict/lenient.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.modules.documents.embeddings import embed_documents, embed_query
from app.modules.documents.reranker import rerank_chunks

# ── Thresholds currently set in evidence.py (copy here for reference) ─────
MAX_VECTOR_DISTANCE = 0.45
MIN_RERANKER_SCORE = -7.0


@dataclass(frozen=True)
class EvidenceCase:
    name: str
    query: str
    passage: str          # text that would realistically be retrieved
    expect_sufficient: bool  # True = should be within threshold; False = low evidence


# ── Test cases based on the US AI Action Plan (July 2025) ─────────────────
# Relevant cases (evidence SHOULD be sufficient)
CASES: list[EvidenceCase] = [
    EvidenceCase(
        name="three_pillars",
        query="What are the three pillars of America's AI Action Plan?",
        passage=(
            "America's AI Action Plan has three pillars: innovation, infrastructure, "
            "and international diplomacy and security."
        ),
        expect_sufficient=True,
    ),
    EvidenceCase(
        name="open_source_ai",
        query="How does the US plan support open-source AI models?",
        passage=(
            "Open-source and open-weight AI models are made freely available by developers "
            "for anyone in the world to download and modify. The Federal government should "
            "create a supportive environment for open models."
        ),
        expect_sufficient=True,
    ),
    EvidenceCase(
        name="semiconductor_manufacturing",
        query="What measures does the action plan propose for semiconductor manufacturing?",
        passage=(
            "America jump-started modern technology with the invention of the semiconductor. "
            "Now America must bring semiconductor manufacturing back to U.S. soil. "
            "A revitalized U.S. chip industry will generate thousands of high-paying jobs."
        ),
        expect_sufficient=True,
    ),
    EvidenceCase(
        name="worker_displacement",
        query="How will the plan help workers displaced by AI automation?",
        passage=(
            "Led by DOL, leverage available discretionary funding to fund rapid retraining "
            "for individuals impacted by AI-related job displacement. Issue clarifying guidance "
            "to help states identify eligible dislocated workers."
        ),
        expect_sufficient=True,
    ),
    EvidenceCase(
        name="ai_government_adoption",
        query="How does the plan accelerate AI adoption within the federal government?",
        passage=(
            "With AI tools in use, the Federal government can serve the public with far greater "
            "efficiency and effectiveness. Use cases include accelerating slow and often manual "
            "internal processes, streamlining public interactions."
        ),
        expect_sufficient=True,
    ),
    EvidenceCase(
        name="cybersecurity_critical_infra",
        query="How does the plan protect critical infrastructure from AI-related cyber threats?",
        passage=(
            "Establish an AI Information Sharing and Analysis Center (AI-ISAC), led by DHS, "
            "to promote the sharing of AI-security threat information and intelligence across "
            "U.S. critical infrastructure sectors."
        ),
        expect_sufficient=True,
    ),
    EvidenceCase(
        name="export_ai_allies",
        query="What is the US strategy for exporting AI technology to allied countries?",
        passage=(
            "The United States must meet global demand for AI by exporting its full AI technology "
            "stack—hardware, models, software, applications, and standards—to all countries "
            "willing to join America's AI alliance."
        ),
        expect_sufficient=True,
    ),
    EvidenceCase(
        name="dod_ai_adoption",
        query="What specific AI initiatives are planned for the Department of Defense?",
        passage=(
            "Establish an AI and Autonomous Systems Virtual Proving Ground at DOD. "
            "Develop a streamlined process within DOD for classifying, evaluating, and "
            "optimizing workflows involved in its major operational and enabling functions."
        ),
        expect_sufficient=True,
    ),

    # ── Off-topic cases (evidence should be LOW / insufficient) ──────────
    # IMPORTANT: these passages simulate what the retrieval system would actually
    # return — the NEAREST chunks from the US AI Action Plan for each off-topic query.
    # The test checks whether those best-match chunks are still too far/irrelevant.
    EvidenceCase(
        name="eu_ai_act_regulation",
        query="What are the key requirements of the European Union's AI Act for high-risk systems?",
        # Nearest chunk from US AI Plan: about removing US regulation / NIST RMF
        passage=(
            "To maintain global leadership in AI, America's private sector must be unencumbered "
            "by bureaucratic red tape. AI is far too important to smother in bureaucracy at this "
            "early stage. Led by NIST at DOC, revise the NIST AI Risk Management Framework to "
            "eliminate references to misinformation, Diversity, Equity, and Inclusion, and climate change."
        ),
        expect_sufficient=False,
    ),
    EvidenceCase(
        name="france_ai_education",
        query="How does France plan to train 15 million professionals in AI by 2030?",
        # Nearest chunk: US AI workforce training section
        passage=(
            "Led by the Department of Labor (DOL), the Department of Education (ED), NSF, and "
            "DOC, prioritize AI skill development as a core objective of relevant education and "
            "workforce funding streams. This should include promoting the integration of AI skill "
            "development into relevant programs, including career and technical education."
        ),
        expect_sufficient=False,
    ),
    EvidenceCase(
        name="uk_nhs_healthcare",
        query="What is the UK government's plan to reform NHS healthcare using digital technology?",
        # Nearest chunk: US domain-specific AI efforts mentioning healthcare
        passage=(
            "Launch several domain-specific efforts (e.g., in healthcare, energy, and agriculture), "
            "led by NIST at DOC, to convene a broad range of public, private, and academic "
            "stakeholders to accelerate the development and adoption of national standards for "
            "AI systems and to measure how much AI increases productivity."
        ),
        expect_sufficient=False,
    ),
    EvidenceCase(
        name="climate_carbon_neutrality",
        query="What is the US strategy for achieving carbon neutrality and net-zero emissions by 2050?",
        # Nearest chunk: energy section which is closest to climate/energy topic
        passage=(
            "We need to build and maintain vast AI infrastructure and the energy to power it. "
            "To do that, we will continue to reject radical climate dogma and bureaucratic red tape. "
            "Prioritize the interconnection of reliable, dispatchable power sources and embrace "
            "new energy generation sources at the technological frontier, such as enhanced geothermal, "
            "nuclear fission, and nuclear fusion."
        ),
        expect_sufficient=False,
    ),
    EvidenceCase(
        name="stem_immigration_visa",
        query="What changes to immigration visas are proposed to attract STEM workers to the US?",
        # Nearest chunk: talent exchange / workforce section
        passage=(
            "Create a talent-exchange program designed to allow rapid details of Federal staff to "
            "other agencies in need of specialized AI talent (e.g., data scientists and software "
            "engineers). Grow our Senior Military Colleges into hubs of AI research, development, "
            "and talent building, teaching core AI skills and literacy to future generations."
        ),
        expect_sufficient=False,
    ),
]


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def main() -> None:
    print("=" * 90)
    print("Evidence Threshold Calibration")
    print(f"  MAX_VECTOR_DISTANCE = {MAX_VECTOR_DISTANCE}")
    print(f"  MIN_RERANKER_SCORE  = {MIN_RERANKER_SCORE}")
    print("=" * 90)

    queries = [c.query for c in CASES]
    passages = [c.passage for c in CASES]

    print(f"\nEmbedding {len(queries)} query–passage pairs...")
    query_vectors = [embed_query(q) for q in queries]
    passage_vectors = embed_documents(passages)

    # Compute distances
    distances = [
        cosine_distance(qv, pv)
        for qv, pv in zip(query_vectors, passage_vectors, strict=True)
    ]

    # Build chunk-like dicts for reranker
    chunk_dicts = [{"text": p} for p in passages]

    print("Running reranker...")
    # Rerank each query independently against its single passage
    # (single-passage reranking just gives us the raw score)
    reranker_scores: list[float] = []
    for query, chunk in zip(queries, chunk_dicts, strict=True):
        ranked = rerank_chunks(query, [chunk], limit=1)
        score = ranked[0].get("reranker_score", float("nan")) if ranked else float("nan")
        reranker_scores.append(score)

    print()
    print(f"{'Case':<30} {'Expect':<12} {'Distance':>9} {'Dist OK':>8} {'Rerank':>8} {'Rnk OK':>7} {'Overall':>8}")
    print("-" * 90)

    correct = 0
    for case, dist, rscore in zip(CASES, distances, reranker_scores, strict=True):
        dist_ok = dist <= MAX_VECTOR_DISTANCE
        rnk_ok = math.isnan(rscore) or rscore >= MIN_RERANKER_SCORE
        pred_sufficient = dist_ok and rnk_ok
        correct_prediction = pred_sufficient == case.expect_sufficient

        label = "SUFFICIENT" if case.expect_sufficient else "LOW_EVID"
        pred_label = "sufficient" if pred_sufficient else "low_evid"
        flag = "OK" if correct_prediction else "WRONG"
        correct += int(correct_prediction)

        print(
            f"{case.name:<30} {label:<12} {dist:>9.4f} {str(dist_ok):>8} "
            f"{rscore:>8.3f} {str(rnk_ok):>7} {flag:>8}"
        )

    n = len(CASES)
    n_sufficient = sum(1 for c in CASES if c.expect_sufficient)
    n_low = n - n_sufficient

    print("-" * 90)
    print(f"Accuracy: {correct}/{n} = {correct/n:.0%}")

    print()
    print("Distance distribution by label:")
    relevant_dists = [d for c, d in zip(CASES, distances) if c.expect_sufficient]
    offtopic_dists = [d for c, d in zip(CASES, distances) if not c.expect_sufficient]
    if relevant_dists:
        print(f"  Relevant  (n={n_sufficient}): "
              f"min={min(relevant_dists):.4f}  max={max(relevant_dists):.4f}  "
              f"avg={sum(relevant_dists)/len(relevant_dists):.4f}")
    if offtopic_dists:
        print(f"  Off-topic (n={n_low}): "
              f"min={min(offtopic_dists):.4f}  max={max(offtopic_dists):.4f}  "
              f"avg={sum(offtopic_dists)/len(offtopic_dists):.4f}")

    relevant_scores = [s for c, s in zip(CASES, reranker_scores) if c.expect_sufficient]
    offtopic_scores = [s for c, s in zip(CASES, reranker_scores) if not c.expect_sufficient]
    if relevant_scores:
        print("\nReranker score distribution by label:")
        print(f"  Relevant  (n={n_sufficient}): "
              f"min={min(relevant_scores):.3f}  max={max(relevant_scores):.3f}  "
              f"avg={sum(relevant_scores)/len(relevant_scores):.3f}")
    if offtopic_scores:
        print(f"  Off-topic (n={n_low}): "
              f"min={min(offtopic_scores):.3f}  max={max(offtopic_scores):.3f}  "
              f"avg={sum(offtopic_scores)/len(offtopic_scores):.3f}")

    print()
    print("Threshold recommendation:")
    if relevant_dists and offtopic_dists:
        max_relevant_dist = max(relevant_dists)
        min_offtopic_dist = min(offtopic_dists)
        if max_relevant_dist < min_offtopic_dist:
            mid = (max_relevant_dist + min_offtopic_dist) / 2
            print(f"  Gap detected: relevant max={max_relevant_dist:.4f}, "
                  f"off-topic min={min_offtopic_dist:.4f}")
            print(f"  Suggested MAX_VECTOR_DISTANCE ≈ {mid:.4f}")
            if mid < MAX_VECTOR_DISTANCE:
                print(f"  Current threshold ({MAX_VECTOR_DISTANCE}) is TOO LENIENT "
                      f"— lower it to ~{mid:.2f}")
            elif mid > MAX_VECTOR_DISTANCE:
                print(f"  Current threshold ({MAX_VECTOR_DISTANCE}) is TOO STRICT "
                      f"— raise it to ~{mid:.2f}")
            else:
                print(f"  Current threshold ({MAX_VECTOR_DISTANCE}) looks appropriate.")
        else:
            overlap = max_relevant_dist - min_offtopic_dist
            print(f"  Distributions overlap by {overlap:.4f}. "
                  f"No single distance threshold perfectly separates them.")
            print("  Rely more on reranker score for borderline cases.")


if __name__ == "__main__":
    main()
