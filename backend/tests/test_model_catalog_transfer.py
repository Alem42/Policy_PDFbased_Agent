import pytest

from scripts.model_catalog_transfer import build_export, validate_import


def test_catalog_export_contains_no_secret_fields():
    payload = build_export(
        providers=[
            {
                "id": "openai",
                "label": "OpenAI",
                "base_url": "https://api.openai.com/v1",
            }
        ],
        endpoints=[
            {
                "provider": "openai",
                "capability": "embedding",
                "model": "text-embedding-3-large",
            }
        ],
    )

    assert payload["format"] == "model-catalog"
    assert payload["version"] == 1
    assert "api_key" not in str(payload).lower()
    assert validate_import(payload) == (payload["providers"], payload["endpoints"])


def test_catalog_import_rejects_wrong_format():
    with pytest.raises(ValueError, match="not a model-catalog"):
        validate_import({"format": "settings-backup", "version": 1})


def test_catalog_import_requires_endpoint_identity():
    payload = build_export(
        providers=[{"id": "openai", "label": "OpenAI"}],
        endpoints=[{"provider": "openai", "capability": "chat"}],
    )

    with pytest.raises(ValueError, match="provider, capability and model"):
        validate_import(payload)
