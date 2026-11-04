"""Download the newest N CRS report PDFs from EveryCRSReport.com and write manifest.csv.

CRS reports are works of the U.S. Government (not under U.S. copyright).
From backend/: python -m scripts.download_crs --count 1000
Files land in data/corpus/crs/ at the project root; already downloaded reports are skipped.
Import them with scripts.import_documents and the generated manifest.csv.
"""

import argparse
import asyncio
import csv
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2] / "data" / "corpus" / "crs"
BASE = "https://www.everycrsreport.com/"
HEADERS = {"User-Agent": "policy-library-corpus-builder/1.0"}


async def main(count: int, concurrency: int) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "reports.csv").exists():
        async with httpx.AsyncClient(headers=HEADERS, timeout=120) as client:
            response = await client.get(BASE + "reports.csv")
            response.raise_for_status()
            (ROOT / "reports.csv").write_bytes(response.content)
    rows = [r for r in csv.DictReader(open(ROOT / "reports.csv", encoding="utf-8")) if r["latestPDF"]]
    rows.sort(key=lambda r: r["latestPubDate"], reverse=True)
    rows = rows[:count]
    (ROOT / "pdfs").mkdir(exist_ok=True)
    gate, done, failed = asyncio.Semaphore(concurrency), 0, []

    async def fetch(client, row):
        nonlocal done
        target = ROOT / "pdfs" / Path(row["latestPDF"]).name
        if not target.exists():
            async with gate:
                try:
                    response = await client.get(BASE + row["latestPDF"])
                    response.raise_for_status()
                    if not response.content.startswith(b"%PDF"):
                        raise ValueError("not a PDF")
                    target.write_bytes(response.content)
                    await asyncio.sleep(0.2)  # stay polite to a volunteer-run site
                except Exception as exc:  # noqa: BLE001 - report and continue
                    failed.append((row["number"], str(exc)[:80]))
                    return
        done += 1
        if done % 100 == 0:
            print(f"{done}/{len(rows)}", flush=True)

    async with httpx.AsyncClient(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        await asyncio.gather(*(fetch(client, row) for row in rows))

    with open(ROOT / "manifest.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["filename", "title", "source_organisation", "country_or_region", "published_year", "source_url", "tags"])
        for row in rows:
            name = Path(row["latestPDF"]).name
            if (ROOT / "pdfs" / name).exists():
                writer.writerow([name, row["title"], "Congressional Research Service", "United States",
                                 row["latestPubDate"][:4], f"{BASE}reports/{row['number']}.html", "CRS"])
    print(f"downloaded {done}, failed {len(failed)}: {failed[:5]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    asyncio.run(main(args.count, args.concurrency))
