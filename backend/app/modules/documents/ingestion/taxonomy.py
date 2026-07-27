"""Two-level policy taxonomy.

Parents + `source_ref` are anchored to recognised policy vocabularies so the
classification is defensible and crosswalks to external datasets:
  - OECD.AI Policy Observatory (AI governance areas)
  - OECD Going Digital (digital transformation)
  - EuroVoc (EU multilingual policy thesaurus)
  - UN SDGs (sustainable development / energy / health)
  - NIST AI RMF (risk categories)

This module holds the DEFAULT tree only. At runtime the live tree lives in the
`policy_taxonomy` DB table and is admin-editable; the DB is seeded from this
default on first use. Keep this in sync as the canonical fallback.
"""

from __future__ import annotations

# Default two-level taxonomy: each parent maps to leaf subcategories.
# Documents are tagged with LEAF labels; parents are derived from the tree.
DEFAULT_TAXONOMY: list[dict] = [
    {
        "parent": "Artificial Intelligence Governance",
        "source_ref": "OECD.AI",
        "children": [
            "National AI Strategy",
            "AI Ethics & Responsible AI",
            "AI Risk & Safety Regulation",
            "AI in Public Services",
            "Generative & Foundation Models",
        ],
    },
    {
        "parent": "Digital Transformation",
        "source_ref": "OECD Going Digital",
        "children": [
            "Digital Government Services",
            "Data Governance & Open Data",
            "Digital Economy & Platforms",
            "Emerging Technologies",
        ],
    },
    {
        "parent": "Digital Inclusion",
        "source_ref": "ITU / EuroVoc",
        "children": [
            "Connectivity & Access Gap",
            "Digital Literacy",
            "Accessibility & Assistive Tech",
        ],
    },
    {
        "parent": "Education and Skills",
        "source_ref": "UN SDG 4",
        "children": [
            "Digital Skills Curriculum",
            "Workforce Reskilling",
            "Research & Higher Education",
        ],
    },
    {
        "parent": "Public Sector Governance",
        "source_ref": "EuroVoc",
        "children": [
            "Regulatory & Legal Framework",
            "Public Administration Reform",
            "Transparency & Accountability",
        ],
    },
    {
        "parent": "Sustainable Development",
        "source_ref": "UN SDGs",
        "children": [
            "SDG Alignment",
            "Green & Circular Economy",
            "Sustainable Cities & Communities",
        ],
    },
    {
        "parent": "Innovation and Industry",
        "source_ref": "OECD STI",
        "children": [
            "R&D & Innovation Funding",
            "Startups & SME Support",
            "Industrial & Manufacturing Strategy",
        ],
    },
    {
        "parent": "Cybersecurity and Data Protection",
        "source_ref": "NIST / GDPR",
        "children": [
            "Personal Data Protection",
            "Critical Infrastructure Security",
            "Cross-border Data Flows",
            "Cyber Resilience & Incident Response",
        ],
    },
    {
        "parent": "Health Policy",
        "source_ref": "UN SDG 3 / WHO",
        "children": [
            "Digital Health & Telemedicine",
            "Health Data & AI Diagnostics",
            "Public Health Systems",
        ],
    },
    {
        "parent": "Energy and Climate",
        "source_ref": "UN SDG 7 & 13",
        "children": [
            "Climate Change Mitigation",
            "Renewable & Clean Energy",
            "Energy Infrastructure & Grids",
        ],
    },
    {
        "parent": "Agriculture and Rural Development",
        "source_ref": "UN SDG 2 / FAO",
        "children": [
            "Digital Agriculture",
            "Rural Connectivity",
            "Food Security",
        ],
    },
    {
        "parent": "Economic Development",
        "source_ref": "World Bank / EuroVoc",
        "children": [
            "Macroeconomic & Trade Policy",
            "Employment & Labour Market",
            "Financial Inclusion & Fintech",
        ],
    },
    {
        "parent": "Social Inclusion",
        "source_ref": "UN SDG 10 / EuroVoc",
        "children": [
            "Equity & Anti-Discrimination",
            "Social Protection & Welfare",
            "Gender & Diversity",
        ],
    },
    {
        "parent": "Infrastructure and Connectivity",
        "source_ref": "OECD / ITU",
        "children": [
            "Broadband & 5G Networks",
            "Cloud & Data Centres",
            "Digital Public Infrastructure",
        ],
    },
    {
        "parent": "Risk Management",
        "source_ref": "NIST AI RMF",
        "children": [
            "Risk Assessment Frameworks",
            "Governance & Compliance Risk",
            "Technology & Operational Risk",
        ],
    },
    {
        "parent": "Other",
        "source_ref": None,
        "children": ["Other"],
    },
]

# Flat list of parent labels (backwards-compatible with the old constant name).
POLICY_TAXONOMY: list[str] = [group["parent"] for group in DEFAULT_TAXONOMY]


def default_leaf_labels() -> list[str]:
    """All leaf (subcategory) labels across the default tree, order preserved."""
    return [child for group in DEFAULT_TAXONOMY for child in group["children"]]


def parent_of_leaf(tree: list[dict]) -> dict[str, str]:
    """Map every leaf label -> its parent label for a given tree."""
    mapping: dict[str, str] = {}
    for group in tree:
        for child in group["children"]:
            mapping[child] = group["parent"]
    return mapping


def normalise_policy_areas(values: list[str], leaf_labels: list[str] | None = None) -> list[str]:
    """Exact (case-insensitive) match of labels to leaf taxonomy labels.

    This is the cheap fallback path. The primary path is embedding
    nearest-neighbour matching in `policy_matcher.py`; this exact matcher is
    used when embeddings are unavailable. Unmatched labels are dropped;
    an all-miss result falls back to ["Other"].
    """
    labels = leaf_labels if leaf_labels is not None else default_leaf_labels()
    lookup = {label.lower(): label for label in labels}
    normalised: list[str] = []
    for value in values:
        match = lookup.get(value.strip().lower())
        if match and match not in normalised:
            normalised.append(match)
    return normalised or ["Other"]
