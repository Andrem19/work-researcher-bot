"""Recheck a saved nightly report without searching, using GLM or sending Telegram."""

import argparse
import asyncio
import json
from pathlib import Path

from work_researcher.domain import JobCard
from work_researcher.freshness import verify_cards


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    cards = [JobCard(source=job["source"], title=job["title"], company=job.get("company"),
                     url=job["url"], description=job.get("description_evidence"))
             for job in report["jobs"]]
    statuses = await verify_cards(cards)
    for card, status in zip(cards, statuses, strict=True):
        print(json.dumps({"title": card.title, "company": card.company, "url": card.url,
                          **status, "evidence": card.extra}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
