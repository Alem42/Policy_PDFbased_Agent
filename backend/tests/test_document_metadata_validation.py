import pytest

from app.modules.documents import service


def test_update_document_metadata_rejects_encoding_damaged_title(monkeypatch) -> None:
    monkeypatch.setattr(
        service.document_content_repository,
        "update_metadata",
        lambda *_args, **_kwargs: pytest.fail("Damaged metadata must not reach persistence."),
    )

    with pytest.raises(ValueError, match="encoding-damaged"):
        service.update_document_metadata("doc-1", {"title": "?????????? 1.0"})


def test_update_document_metadata_accepts_utf8_title(monkeypatch) -> None:
    captured: dict = {}

    def fake_update(identifier: str, payload: dict) -> dict:
        captured.update({"identifier": identifier, "payload": payload})
        return {"id": identifier, **payload}

    monkeypatch.setattr(service.document_content_repository, "update_metadata", fake_update)

    result = service.update_document_metadata(
        "doc-1",
        {"title": "Artificial Intelligence Safety Governance Framework"},
    )

    assert result["title"] == "Artificial Intelligence Safety Governance Framework"
    assert captured["identifier"] == "doc-1"
