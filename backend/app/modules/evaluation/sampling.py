"""Deterministic small batches covering categories and split labels."""

from collections import defaultdict, deque


def balanced(cases, limit):
    if len(cases) <= limit:
        return cases
    groups = defaultdict(deque)
    for case in cases:
        groups[(case.get("category", ""), case.get("split", ""))].append(case)
    result = []
    while len(result) < limit:
        for group in groups.values():
            if group and len(result) < limit:
                result.append(group.popleft())
    return result
