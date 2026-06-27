POLICY_TAXONOMY = [
    "Artificial Intelligence Governance",
    "Digital Transformation",
    "Digital Inclusion",
    "Education and Skills",
    "Public Sector Governance",
    "Sustainable Development",
    "Innovation and Industry",
    "Cybersecurity and Data Protection",
    "Health Policy",
    "Energy and Climate",
    "Agriculture and Rural Development",
    "Economic Development",
    "Social Inclusion",
    "Infrastructure and Connectivity",
    "Risk Management",
    "Other",
]


def normalise_policy_areas(values: list[str]) -> list[str]:
    lookup = {item.lower(): item for item in POLICY_TAXONOMY}
    normalised: list[str] = []
    for value in values:
        clean = value.strip()
        match = lookup.get(clean.lower())
        if match and match not in normalised:
            normalised.append(match)
    return normalised or ["Other"]
