from __future__ import annotations

import argparse
import math
import statistics
from dataclasses import dataclass

from app.modules.documents.embeddings import EMBEDDING_MODEL_NAME, embed_text

EXPECTED_DIMENSIONS = 384
MIN_TOP1_ACCURACY = 0.75
MIN_MEAN_MARGIN = 0.05


@dataclass(frozen=True)
class RetrievalCase:
    name: str
    query: str
    relevant: str
    lexical_distractor: str


CASES = [
    RetrievalCase(
        name="electric_vehicle_support",
        query="What financial support is available for battery-powered cars?",
        relevant="The government provides subsidies to buyers of electric vehicles.",
        lexical_distractor=(
            "The report compares battery performance in cars and financial risks "
            "for manufacturers."
        ),
    ),
    RetrievalCase(
        name="gasoline_vehicle_ban",
        query="Which rules ban gasoline vehicles?",
        relevant="The regulation prohibits petrol-powered cars.",
        lexical_distractor=(
            "The rules classify gasoline vehicles by engine size and weight."
        ),
    ),
    RetrievalCase(
        name="household_energy_bills",
        query="How does the law help poor families pay energy bills?",
        relevant="The scheme gives utility rebates to low-income households.",
        lexical_distractor=(
            "The law report estimates energy bills paid by commercial offices."
        ),
    ),
    RetrievalCase(
        name="factory_emissions",
        query="What measures reduce carbon emissions from factories?",
        relevant=(
            "Industrial plants must cut greenhouse-gas pollution through "
            "efficiency standards."
        ),
        lexical_distractor=(
            "The survey measures factory output and carbon accounting software."
        ),
    ),
    RetrievalCase(
        name="personal_data_protection",
        query="How are citizens protected from misuse of personal data?",
        relevant=(
            "Residents receive safeguards against improper handling of private "
            "information."
        ),
        lexical_distractor=(
            "The data appendix lists personal identification fields collected "
            "from citizens."
        ),
    ),
    RetrievalCase(
        name="automated_decision_transparency",
        query="What obligations make automated decisions explainable?",
        relevant=(
            "Organisations must disclose how algorithmic outcomes are produced."
        ),
        lexical_distractor=(
            "The automated system stores decisions in an explainable file format."
        ),
    ),
    RetrievalCase(
        name="renewable_electricity_target",
        query="What goal increases clean electricity generation?",
        relevant="The policy sets a target for expanding renewable power.",
        lexical_distractor=(
            "The electricity report records generation from clean and fossil sources."
        ),
    ),
    RetrievalCase(
        name="worker_technology_training",
        query="How does the programme prepare employees for new technology?",
        relevant="The initiative funds digital-skills training for workers.",
        lexical_distractor=(
            "The technology programme tracks employee attendance and payroll."
        ),
    ),
    RetrievalCase(
        name="public_transport",
        query="What policy encourages people to use buses and trains?",
        relevant="Discounted fares promote public transit use.",
        lexical_distractor=(
            "The policy database lists bus and train route identifiers."
        ),
    ),
    RetrievalCase(
        name="household_water_saving",
        query="How are households encouraged to save water?",
        relevant="Residents receive rebates for installing efficient fixtures.",
        lexical_distractor=(
            "The water report records household addresses and meter readings."
        ),
    ),
    RetrievalCase(
        name="cyber_incident_reporting",
        query="When must companies disclose a cyber incident?",
        relevant=(
            "Firms have to report a security breach within seventy-two hours."
        ),
        lexical_distractor=(
            "The cyber dashboard lists company incident identification numbers."
        ),
    ),
    RetrievalCase(
        name="rural_healthcare_access",
        query="How does the programme improve access to doctors in remote areas?",
        relevant=(
            "The initiative finances telehealth services for rural communities."
        ),
        lexical_distractor=(
            "The programme records doctor names and remote server access logs."
        ),
    ),
]


def cosine_similarity(first: list[float], second: list[float]) -> float:
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm == 0.0 or second_norm == 0.0:
        return 0.0
    dot_product = sum(a * b for a, b in zip(first, second, strict=True))
    return dot_product / (first_norm * second_norm)


def vector_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def evaluate() -> dict[str, object]:
    probe = embed_text("A simple English policy sentence.")
    deterministic = probe == embed_text("A simple English policy sentence.")
    finite = all(math.isfinite(value) for value in probe)

    margins: list[float] = []
    relevant_scores: list[float] = []
    distractor_scores: list[float] = []
    top1_wins = 0

    print(f"Embedding model: {EMBEDDING_MODEL_NAME}")
    print(f"Dimensions: {len(probe)}")
    print(f"Deterministic: {deterministic}")
    print(f"Finite values: {finite}")
    print(f"English vector norm: {vector_norm(probe):.4f}")
    print("\nSynthetic semantic retrieval benchmark")
    print("-" * 78)

    for index, case in enumerate(CASES, start=1):
        query_vector = embed_text(case.query)
        relevant_score = cosine_similarity(query_vector, embed_text(case.relevant))
        distractor_score = cosine_similarity(
            query_vector,
            embed_text(case.lexical_distractor),
        )
        margin = relevant_score - distractor_score
        relevant_wins = margin > 0.0
        top1_wins += int(relevant_wins)
        relevant_scores.append(relevant_score)
        distractor_scores.append(distractor_score)
        margins.append(margin)

        result = "PASS" if relevant_wins else "FAIL"
        print(
            f"{index:02d}. {case.name:<34} {result} "
            f"relevant={relevant_score:.4f} "
            f"distractor={distractor_score:.4f} margin={margin:.4f}"
        )

    top1_accuracy = top1_wins / len(CASES)
    mean_relevant = statistics.fmean(relevant_scores)
    mean_distractor = statistics.fmean(distractor_scores)
    mean_margin = statistics.fmean(margins)

    chinese_vector = embed_text("政府为新能源汽车提供财政补贴。")
    chinese_zero_vector = vector_norm(chinese_vector) == 0.0

    first_order_vector = embed_text("government taxes companies")
    reversed_order_vector = embed_text("companies taxes government")
    word_order_collision = first_order_vector == reversed_order_vector

    contract_pass = (
        len(probe) == EXPECTED_DIMENSIONS
        and deterministic
        and finite
        and vector_norm(probe) > 0.0
    )
    semantic_pass = (
        top1_accuracy >= MIN_TOP1_ACCURACY
        and mean_margin >= MIN_MEAN_MARGIN
    )

    print("-" * 78)
    print(f"Top-1 accuracy: {top1_wins}/{len(CASES)} = {top1_accuracy:.1%}")
    print(f"Mean relevant similarity: {mean_relevant:.4f}")
    print(f"Mean distractor similarity: {mean_distractor:.4f}")
    print(f"Mean semantic margin: {mean_margin:.4f}")
    print(f"Chinese input becomes zero vector: {chinese_zero_vector}")
    print(f"Different word order gives identical vector: {word_order_collision}")
    print(f"Vector contract: {'PASS' if contract_pass else 'FAIL'}")
    print(f"Semantic retrieval: {'PASS' if semantic_pass else 'FAIL'}")

    return {
        "contract_pass": contract_pass,
        "semantic_pass": semantic_pass,
        "top1_accuracy": top1_accuracy,
        "mean_margin": mean_margin,
        "chinese_zero_vector": chinese_zero_vector,
        "word_order_collision": word_order_collision,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit with status 1 when semantic acceptance criteria fail.",
    )
    args = parser.parse_args()

    results = evaluate()
    if args.enforce and not results["semantic_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
