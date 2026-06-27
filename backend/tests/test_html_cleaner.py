from app.modules.crawling.cleaning.html import HtmlCleaner


def test_cleaner_preserves_structure_and_discovers_assets() -> None:
    html = """
    <html>
      <head><title>Policy title</title><style>.x { color: red }</style></head>
      <body>
        <nav>Navigation</nav>
        <main>
          <h1>Policy title</h1>
          <p>A <strong>significant</strong> policy.</p>
          <ul><li>First point</li><li>Second point</li></ul>
          <a href="/files/policy.pdf">Official PDF</a>
          <footer>Footer</footer>
        </main>
      </body>
    </html>
    """

    result = HtmlCleaner().clean(html, page_url="https://example.com/policy")

    assert "# Policy title" in result.markdown
    assert "**significant**" in result.markdown
    assert "- First point" in result.markdown
    assert "Navigation" not in result.markdown
    assert "Footer" not in result.markdown
    assert result.assets == [
        {
            "url": "https://example.com/files/policy.pdf",
            "asset_type": "pdf",
            "title": "Official PDF",
            "mime_type": "application/pdf",
        }
    ]


def test_cleaner_ignores_icons_inside_bold_text() -> None:
    html = """
    <html>
      <body>
        <main>
          <p><strong><i class="fa fa-user"></i> Added by:</strong> National contact point</p>
          <p><strong><span class="material-icons">person</span> Updated on:</strong> 2026</p>
        </main>
      </body>
    </html>
    """

    result = HtmlCleaner().clean(html, page_url="https://example.com/policy")

    assert "**Added by:** National contact point" in result.markdown
    assert "**Updated on:** 2026" in result.markdown
    assert "** Added by" not in result.markdown
    assert "person" not in result.markdown
