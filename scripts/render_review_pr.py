#!/usr/bin/env python3
"""Render the review pull request body from the staged uncertain entries.

Usage: python scripts/render_review_pr.py staged_publications/uncertain.json
"""

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    records = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    print(
        "These publications were found automatically but did **not** meet the bar "
        "for committing straight to `main`. Check each one, fix the tags if needed, "
        "then merge."
    )
    print()

    for record in records:
        review = record.get("_review", {})
        print(f"- **{record['title']}**")
        print(f"  - {record['authors']} ({record['year']}). {record['publication_info']}")
        print(f"  - Tags: {', '.join(record['tags']) or '—'}")
        print(
            f"  - Matched member: {review.get('matched_member', '?')} "
            f"(source: {review.get('source', '?')})"
        )
        print(f"  - Needs review because: {'; '.join(review.get('reasons', [])) or '—'}")

    print()
    print(
        "Anything tagged `Uncategorized` needs a real tag from the vocabulary in "
        "`publications/tags-map.json`. If a paper was matched to the wrong person, "
        "delete the entry and add an `orcid` for that member in "
        "`publications/authors.json` so it stops recurring."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
