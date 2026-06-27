from bs4 import BeautifulSoup

from app.extraction.fields import ConfigFieldExtractor


def test_config_field_extractor_supports_core_and_metadata_fields() -> None:
    soup = BeautifulSoup(
        """
        <main>
          <h1>National AI Strategy</h1>
          <p class="summary">A national policy for responsible AI.</p>
          <span class="country">Australia</span>
          <div data-status="active"></div>
          <span class="year">Started in 2025</span>
          <ul class="tags"><li>Safety</li><li>Transparency</li></ul>
          <a class="official" href="/official">Official site</a>
        </main>
        """,
        "html.parser",
    )
    config = {
        "title": "h1",
        "summary": {"selector": ".summary"},
        "country": {"selector": ".country"},
        "policy_status": {
            "selector": "[data-status]",
            "attribute": "data-status",
            "transform": "upper",
        },
        "start_year": {
            "selector": ".year",
            "regex": r"(\d{4})",
            "transform": "year",
        },
        "metadata": {
            "tags": {"selector": ".tags li", "multiple": True},
            "official_url": {
                "selector": "a.official",
                "attribute": "href",
            },
        },
    }

    result = ConfigFieldExtractor().extract(
        soup,
        page_url="https://example.com/policies/1",
        config=config,
    )

    assert result.structured == {
        "title": "National AI Strategy",
        "summary": "A national policy for responsible AI.",
        "country": "Australia",
        "policy_status": "ACTIVE",
        "start_year": 2025,
    }
    assert result.metadata == {
        "tags": ["Safety", "Transparency"],
        "official_url": "https://example.com/official",
    }
