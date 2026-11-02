"""Deterministic candidate allocation, independent of models or HTTP."""


def allocate(ranked, limit, *, groups=(), per_document=False):
    selected, seen = [], set()

    def take(row):
        key = str(row["chunk_id"])
        if key not in seen and len(selected) < limit:
            selected.append(row)
            seen.add(key)

    # A required subquestion gets its best candidate before global fillers.
    for group in groups:
        if group:
            take(group[0])
    if per_document:
        documents = set()
        for row in ranked:
            doc = str(row["document_id"])
            if doc not in documents:
                documents.add(doc)
                take(row)
    for row in ranked:
        take(row)
    return selected
