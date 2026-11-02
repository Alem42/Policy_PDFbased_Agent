"""Materialise source-anchored cases; fail if a gold quote isn't in its PDF page."""
import json

import fitz

from app.modules.evaluation.corpus import CORPUS, DATA, manifest, verified_files
from app.modules.evaluation.metrics import normalized

# Physical PDF pages, not printed page numbers. Quotes are evidence anchors, not model answers.
ANNOTATIONS = [
    ("What are the four core functions used to organize AI risk management activities?", 25,
     "govern, map, measure, and manage AI risks"),
    ("How is confabulation defined as a generative AI risk?", 8,
     "The production of confidently stated but erroneous or false content"),
    ("List the five cross-sectoral principles proposed for regulating AI.", 12,
     "Safety, security and robustness o Appropriate transparency and explainability o Fairness o Accountability and governance o Contestability and redress"),
    ("处理不满十四周岁未成年人的个人信息，应当取得谁的同意？", 8,
     "应当取得未成年人的父母或者其他监护人的同意"),
    ("国家根据哪些因素对数据实行分类分级保护？", 5,
     "根据数据在经济社会发展中的重要程度"),
    ("Which five functions are used to manage privacy risks arising from data processing?", 10,
     "Identify-P, Govern-P, Control-P, Communicate-P, and Protect-P"),
    ("What offshore wind capacity does the plan aim to produce by 2030, including floating offshore wind?", 12,
     "40GW of offshore wind, including 1GW of innovative floating offshore wind"),
    ("What are Australia's greenhouse gas emissions targets for 2030 and 2050, and what is the baseline year?", 10,
     "43% below 2005 levels by 2030"),
    ("Who is this social housing and homelessness agreement intended to help, and which services does it support?", 2,
     "help people who are experiencing, or at risk of, homelessness"),
    ("Name all six core cybersecurity functions.", 31,
     "Govern, Identify, Protect, Detect, Respond, and Recover"),
    ("Which three functions help organizations discover, contain, eradicate and recover from cybersecurity incidents?", 9,
     "Detect, Respond, and Recover help organizations discover, manage, prioritize, contain, eradicate, and recover"),
    ("What are the four pillars of the response to biological risks?", 8,
     "Understand the biological risks"),
]


def main():
    files = verified_files()
    entries = manifest()["documents"]
    positives, cases = [], []
    for index, (question, page, quote) in enumerate(ANNOTATIONS):
        entry = entries[index]
        with fitz.open(CORPUS / entry["local_path"]) as pdf:
            assert normalized(quote) in normalized(pdf[page-1].get_text()), entry["id"]
        case = {"id": f"P{index+1:02}", "question": question, "source_ids": [entry["id"]],
                "expected_allow": True, "category": "answerable", "split": "calibration" if index % 2 == 0 else "validation",
                "claim_group": entry["id"], "evidence": [{"source_id": entry["id"], "page": page, "quote": quote}]}
        positives.append(case)
        cases.append(case)
    # Ask questions whose evidence exists elsewhere in the pack, outside the selected document.
    # This checks scope discipline and abstention rather than the LLM's general knowledge.
    for index, target in enumerate([9, 3, 4, 6, 7, 8, 10, 5, 11, 0, 1, 2]):
        cases.append({"id": f"N{index+1:02}", "question": positives[target]["question"],
                      "source_ids": positives[index]["source_ids"], "expected_allow": False,
                      "category": "out_of_scope", "split": positives[index]["split"],
                      "claim_group": positives[index]["claim_group"], "evidence": [],
                      "rationale": "The selected document does not specify this fact; the known supporting source is outside the selected scope.",
                      "supporting_source_outside_scope": entries[target]["id"]})
    for name, indices, question in [
        ("C01", [0, 9], "Compare the core functions for AI risk management and cybersecurity. List both sets and their differences."),
        ("C02", [3, 4], "分别说明未满十四周岁个人信息处理的同意要求，以及数据分类分级保护的依据。"),
        ("C03", [6, 7], "Compare the UK plan's 2030 offshore wind ambition with Australia's 2030 emissions reduction target. Give units and baseline where applicable."),
    ]:
        cases.append({"id": name, "question": question,
                      "source_ids": [entries[i]["id"] for i in indices], "expected_allow": True,
                      "category": "cross_document", "split": "diagnostic",
                      "claim_group": name, "evidence": [positives[i]["evidence"][0] for i in indices]})
    payload = {"version": "1.0", "corpus_id": manifest()["corpus_id"],
               "page_numbering": "physical_pdf_1_based", "cases": cases}
    (DATA / "cases-v1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Verified {len(files)} checksums and {len(positives)} page anchors; wrote {len(cases)} cases.")


if __name__ == "__main__":
    main()
