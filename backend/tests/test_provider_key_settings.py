from app.modules.settings import service
from app.modules.settings.schemas import RuntimeSettings


def test_zhipu_is_a_known_key_provider_from_catalog():
    assert "zhipu" in service._known_provider_ids()


def _memory_settings(monkeypatch):
    state = {"value": RuntimeSettings()}

    def load():
        return state["value"].model_copy(deep=True)

    def save(value):
        state["value"] = value.model_copy(deep=True)

    monkeypatch.setattr(service.settings_repository, "load", load)
    monkeypatch.setattr(service.settings_repository, "save", save)
    return state


def test_catalog_provider_key_is_saved_and_returned_masked(monkeypatch):
    state = _memory_settings(monkeypatch)

    result = service.update_public_settings(
        provider_api_keys={"zhipu": "zhipu-secret-key"}
    )

    assert state["value"].provider_api_keys["zhipu"] == "zhipu-secret-key"
    assert service.get_llm_api_key("zhipu") == ("zhipu-secret-key", "settings")
    assert result["masked_provider_keys"]["zhipu"] == "zhip...-key"


def test_catalog_provider_key_can_be_cleared(monkeypatch):
    state = _memory_settings(monkeypatch)
    state["value"].provider_api_keys["zhipu"] = "zhipu-secret-key"

    result = service.update_public_settings(provider_api_keys={"zhipu": ""})

    assert "zhipu" not in state["value"].provider_api_keys
    assert result["masked_provider_keys"]["zhipu"] is None


def test_unknown_provider_key_is_not_accepted(monkeypatch):
    state = _memory_settings(monkeypatch)

    service.update_public_settings(provider_api_keys={"not-in-catalog": "secret"})

    assert state["value"].provider_api_keys == {}
