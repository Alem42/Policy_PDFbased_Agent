from __future__ import annotations

import logging

from app.modules.documents.ingestion.taxonomy import (
    DEFAULT_TAXONOMY,
    parent_of_leaf,
)
from app.modules.documents.repositories.taxonomy import taxonomy_repository

logger = logging.getLogger(__name__)


def get_taxonomy_tree() -> list[dict]:
    """Live taxonomy tree. Seeds the DB from DEFAULT_TAXONOMY on first use.

    Falls back to the in-code default if the DB is unavailable so ingestion and
    the filter UI keep working even before the 004 migration is applied.
    """
    try:
        if taxonomy_repository.is_empty():
            taxonomy_repository.replace_tree(DEFAULT_TAXONOMY)
            logger.info("Seeded policy_taxonomy from DEFAULT_TAXONOMY")
        tree = taxonomy_repository.load_tree()
        return tree or DEFAULT_TAXONOMY
    except Exception as exc:
        logger.warning("Taxonomy DB unavailable, using in-code default: %s", exc)
        return DEFAULT_TAXONOMY


def replace_taxonomy_tree(groups: list[dict]) -> list[dict]:
    """Persist a new taxonomy tree and return the stored result.

    The embedding matcher caches label vectors keyed by the label set itself, so
    a changed taxonomy naturally lands on a fresh cache entry — no manual bust.
    """
    taxonomy_repository.replace_tree(groups)
    return get_taxonomy_tree()


def get_leaf_labels() -> list[str]:
    """Flat list of leaf (subcategory) labels used for tagging + matching."""
    return [child for group in get_taxonomy_tree() for child in group["children"]]


def get_parent_map() -> dict[str, str]:
    """Leaf label -> parent label, for deriving parents from tagged leaves."""
    return parent_of_leaf(get_taxonomy_tree())
