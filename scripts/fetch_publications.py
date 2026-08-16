#!/usr/bin/env python3
"""Fetch new NADIA publications and merge them into publications/publications.json.

Sources, in order of preference:
  * NASA ADS  -- used when ADS_TOKEN is set. Provides DOI, journal reference,
                 UAT keywords and ORCID-exact author matching.
  * arXiv     -- fallback when ADS_TOKEN is absent or an ADS query fails. Name
                 matching only, and preprints carry no DOI or journal reference.

Every discovered paper is classified as either CONFIDENT or UNCERTAIN. A paper is
CONFIDENT only when all of the following hold:

  1. it was matched to a member via ORCID (not a name search),
  2. the tag map produced at least one real tag,
  3. it has a DOI,
  4. it has a journal reference (not just an arXiv identifier).

The two sets are staged to separate files. A second invocation with --apply
merges a staged file into publications.json, so the workflow can commit the
confident set to main and the uncertain set to a review branch, each producing a
normal reviewable diff of the real publication list.

Usage:
    python scripts/fetch_publications.py                  # last 7 days
    python scripts/fetch_publications.py --days 30        # last 30 days
    python scripts/fetch_publications.py --backfill       # each member's full
                                                          # NADIA window
    python scripts/fetch_publications.py --dry-run        # print, write nothing
    python scripts/fetch_publications.py --apply staged/confident.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLICATIONS_JSON = REPO_ROOT / "publications" / "publications.json"
AUTHORS_JSON = REPO_ROOT / "publications" / "authors.json"
TAGS_MAP_JSON = REPO_ROOT / "publications" / "tags-map.json"
STAGE_DIR = REPO_ROOT / "staged_publications"

ADS_ENDPOINT = "https://api.adsabs.harvard.edu/v1/search/query"
ADS_FIELDS = (
    "bibcode,title,author,doi,pub,volume,page,year,pubdate,keyword,"
    "identifier,abstract,doctype"
)
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    # DOI and journal reference live in arXiv's own namespace, not atom.
    "arxiv": "http://arxiv.org/schemas/atom",
}
ARXIV_PDF = "https://arxiv.org/pdf/{}"

USER_AGENT = "nus-nadia-publications-bot/1.0 (+https://github.com/nus-nadia)"
REQUEST_TIMEOUT = 30
# ADS asks for a courteous request rate; arXiv's terms require >= 3s between calls.
ADS_DELAY = 1.0
ARXIV_DELAY = 3.5


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalize_title(title: str) -> str:
    """Collapse a title to a comparable key for duplicate detection."""
    folded = unicodedata.normalize("NFKD", title or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.lower()
    folded = re.sub(r"[^a-z0-9]+", " ", folded)
    return " ".join(folded.split())


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:", "", doi)
    return doi or None


def parse_date(value: str | None) -> date | None:
    """Parse the assorted date shapes ADS and arXiv return."""
    if not value:
        return None
    value = value.strip()
    # ADS pubdate uses 00 for an unknown month or day, e.g. '2024-09-00'.
    match = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?", value)
    if match:
        year = int(match.group(1))
        month = int(match.group(2)) or 1
        day = int(match.group(3) or 1) or 1
        try:
            return date(year, month, day)
        except ValueError:
            return date(year, month, 1)
    match = re.match(r"^(\d{4})$", value)
    if match:
        return date(int(match.group(1)), 1, 1)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def http_get(url: str, headers: dict | None = None, attempts: int = 4) -> bytes:
    """GET with exponential backoff on rate limiting and transient server errors."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    delay = 5.0
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            # 429 = rate limited, 5xx = transient. Anything else is a real error.
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            wait = float(retry_after) if (retry_after or "").isdigit() else delay
            log(f"  . HTTP {exc.code}; retrying in {wait:.0f}s ({attempt}/{attempts - 1})")
            time.sleep(wait)
            delay *= 2
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------
# membership windows
# --------------------------------------------------------------------------

def membership_window(author: dict) -> tuple[date, date]:
    """Return the (start, end) dates during which this member counts as NADIA."""
    joined = parse_date(author.get("joined")) or date(1900, 1, 1)
    left = parse_date(author.get("left")) or date.today()
    return joined, left


def in_membership_window(pub_date: date | None, author: dict) -> bool:
    """A paper counts only if it was published while the member was in NADIA."""
    if pub_date is None:
        # Undated results are kept and flagged rather than silently dropped;
        # they can never be CONFIDENT because they lack a journal reference.
        return True
    joined, left = membership_window(author)
    return joined <= pub_date <= left


# --------------------------------------------------------------------------
# tagging
# --------------------------------------------------------------------------

class Tagger:
    def __init__(self, config: dict):
        self.vocabulary = set(config.get("vocabulary", []))
        self.uncategorized = config.get("uncategorized_tag", "Uncategorized")
        self.require_keyword_match = bool(config.get("require_keyword_match", False))
        self.rules_order = list(config.get("vocabulary", []))
        self.rules = []
        for rule in config.get("rules", []):
            tag = rule.get("tag")
            if tag not in self.vocabulary:
                log(f"  ! tag-map rule for '{tag}' is not in the vocabulary; ignoring")
                continue
            implies = [t for t in rule.get("implies", []) if t in self.vocabulary]
            self.rules.append(
                {
                    "tag": tag,
                    "implies": implies,
                    "keywords": {self._fold(k) for k in rule.get("keywords", [])},
                    "patterns": [re.compile(p, re.IGNORECASE) for p in rule.get("patterns", [])],
                }
            )

    @staticmethod
    def _fold(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())

    def tag(self, keywords: list[str], text: str) -> tuple[list[str], bool]:
        """Return (tags, has_keyword_match).

        has_keyword_match distinguishes a UAT-keyword hit from a looser regex
        guess, so require_keyword_match can gate auto-commit on the stronger
        signal.
        """
        folded_keywords = {self._fold(k) for k in keywords or []}
        tags: list[str] = []
        keyword_hit = False

        for rule in self.rules:
            matched_by_keyword = bool(folded_keywords & rule["keywords"])
            if not matched_by_keyword:
                # Substring check catches 'Exoplanet astronomy (486)' style entries.
                matched_by_keyword = any(
                    known and known in candidate
                    for candidate in folded_keywords
                    for known in rule["keywords"]
                )
            matched_by_pattern = any(p.search(text) for p in rule["patterns"])

            if matched_by_keyword or matched_by_pattern:
                tags.append(rule["tag"])
                tags.extend(rule["implies"])
                keyword_hit = keyword_hit or matched_by_keyword

        if not tags:
            return [self.uncategorized], False

        # Preserve the vocabulary's declared order and drop implied duplicates.
        ordered = [t for t in self.rules_order if t in set(tags)]
        return ordered, keyword_hit


# --------------------------------------------------------------------------
# formatting into the site's schema
# --------------------------------------------------------------------------

def format_authors(author_list: list[str], member_keys: set | None = None) -> str:
    """Render 'Hon, M.; Huber, D.; Rui, N. Z.; et al.' as the existing entries do.

    NADIA members are wrapped in <strong>. If every member falls outside the
    first three shown, they are named after 'et al.' instead — otherwise the
    group is invisible on papers where its members are middle authors, which is
    most of them.
    """
    cleaned = [a.strip() for a in (author_list or []) if a and a.strip()]
    if not cleaned:
        return "Unknown"

    member_keys = member_keys or set()
    shown = cleaned[:3]
    rendered = "; ".join(
        f"<strong>{a}</strong>" if name_key(a) in member_keys else a for a in shown
    )
    if len(cleaned) <= 3:
        return rendered

    rendered += "; et al."
    if not any(name_key(a) in member_keys for a in shown):
        hidden = [a for a in cleaned[3:] if name_key(a) in member_keys]
        if hidden:
            named = "; ".join(f"<strong>{a}</strong>" for a in hidden[:2])
            rendered += f" (incl. {named})"
    return rendered


def format_publication_info(pub: str | None, volume: str | None, page) -> str:
    parts = [p for p in [pub, volume] if p]
    if isinstance(page, list):
        page = page[0] if page else None
    if page:
        parts.append(str(page))
    return ", ".join(str(p) for p in parts)


def build_entry(
    *,
    title: str,
    authors: list[str],
    member_keys: set | None = None,
    publication_info: str,
    doi: str | None,
    year: int,
    tags: list[str],
    pdf_link: str = "",
) -> dict:
    """Produce a record in exactly the shape publications.js already renders.

    A link with no target is left as an empty string rather than '#'; the page
    omits the button entirely in that case.
    """
    return {
        "title": title,
        "authors": format_authors(authors, member_keys),
        "publication_info": publication_info,
        "pdf_link": pdf_link,
        "doi_link": f"https://doi.org/{doi}" if doi else "",
        "year": year,
        "tags": tags,
    }


# --------------------------------------------------------------------------
# NASA ADS
# --------------------------------------------------------------------------

def ads_query(token: str, query: str, rows: int = 200) -> list[dict]:
    params = urllib.parse.urlencode(
        {"q": query, "fl": ADS_FIELDS, "rows": rows, "sort": "date desc"}
    )
    url = f"{ADS_ENDPOINT}?{params}"
    payload = http_get(url, headers={"Authorization": f"Bearer {token}"})
    data = json.loads(payload)
    return data.get("response", {}).get("docs", [])


def ads_date_clause(start: date, end: date) -> str:
    return f"pubdate:[{start:%Y-%m} TO {end:%Y-%m}]"


# Excludes same-name researchers publishing outside astronomy.
ADS_ASTRO_CLAUSE = " AND database:astronomy"


def coauthor_clause(anchors: list[str], exclude: str | None = None) -> str:
    """An ADS clause requiring at least one ORCID-carrying member on the paper.

    Names like 'Wu, Y.' match a great many unrelated astronomers, so a bare name
    search is close to useless. Anchoring it to a colleague's ORCID removes
    nearly all of that noise, at the cost of missing solo papers.
    """
    usable = [a for a in anchors if a and a != exclude]
    if not usable:
        return ""
    return " AND (" + " OR ".join(f'orcid:"{a}"' for a in usable) + ")"


def fetch_from_ads(
    token: str,
    author: dict,
    start: date,
    end: date,
    anchors: list[str] | None = None,
    astro_only: bool = True,
) -> list[tuple[dict, bool]]:
    """Return (raw_doc, matched_by_orcid) pairs for one member."""
    results: list[tuple[dict, bool]] = []
    seen_bibcodes: set[str] = set()
    date_clause = ads_date_clause(start, end) + (ADS_ASTRO_CLAUSE if astro_only else "")

    queries: list[tuple[str, bool]] = []
    orcid = (author.get("orcid") or "").strip()
    if orcid:
        queries.append((f'orcid:"{orcid}" {date_clause}', True))
    else:
        anchor_clause = coauthor_clause(anchors or [])
        for variant in author.get("name_variants", []):
            queries.append((f'author:"{variant}" {date_clause}{anchor_clause}', False))

    for query, by_orcid in queries:
        try:
            docs = ads_query(token, query)
        except urllib.error.HTTPError as exc:
            log(f"  ! ADS HTTP {exc.code} for query {query!r}")
            if exc.code in (401, 403):
                raise
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            log(f"  ! ADS unreachable for query {query!r}: {exc}")
            continue
        finally:
            time.sleep(ADS_DELAY)

        for doc in docs:
            bibcode = doc.get("bibcode")
            if bibcode and bibcode in seen_bibcodes:
                continue
            if bibcode:
                seen_bibcodes.add(bibcode)
            results.append((doc, by_orcid))

    return results


def first(value):
    """ADS returns some scalar fields as single-element lists, or omits them."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def ads_doc_to_candidate(
    doc: dict, tagger: Tagger, by_orcid: bool, member_keys: set | None = None
) -> dict:
    title = first(doc.get("title")) or "(untitled)"
    abstract = doc.get("abstract") or ""
    keywords = doc.get("keyword") or []
    tags, keyword_hit = tagger.tag(keywords, f"{title} {abstract}")

    doi = normalize_doi(first(doc.get("doi")))

    pub = first(doc.get("pub"))

    arxiv_id = None
    for identifier in doc.get("identifier") or []:
        if identifier.lower().startswith("arxiv:"):
            arxiv_id = identifier.split(":", 1)[1]
            break

    pub_date = parse_date(first(doc.get("pubdate")))
    year_field = str(first(doc.get("year")) or "")
    year = int(year_field) if year_field.isdigit() else (
        pub_date.year if pub_date else date.today().year
    )

    # ADS records preprints with pub 'arXiv e-prints'; that is not a journal ref.
    has_journal = bool(pub) and "arxiv" not in pub.lower()

    if has_journal:
        publication_info = format_publication_info(pub, first(doc.get("volume")), doc.get("page"))
    elif arxiv_id:
        # Prefer the citable identifier over the literal string 'arXiv e-prints'.
        publication_info = f"arXiv:{arxiv_id}"
    else:
        publication_info = pub or ""

    return {
        "source": "ads",
        "matched_by_orcid": by_orcid,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title_key": normalize_title(title),
        "pub_date": pub_date,
        "has_journal": has_journal,
        "keyword_tag_match": keyword_hit,
        "tags": tags,
        "entry": build_entry(
            title=title,
            authors=doc.get("author") or [],
            member_keys=member_keys,
            # The preprint PDF is free to read; the DOI is the version of record.
            pdf_link=ARXIV_PDF.format(arxiv_id) if arxiv_id else "",
            publication_info=publication_info,
            doi=doi,
            year=year,
            tags=tags,
        ),
    }


# --------------------------------------------------------------------------
# arXiv fallback
# --------------------------------------------------------------------------

def name_key(name: str) -> tuple[str, str]:
    """Reduce a personal name to (surname, first initial), both lowercased.

    Handles both the 'Hon, M.' form used by ADS and the 'Marc Hon' form arXiv
    returns, so the two can be compared.
    """
    name = " ".join((name or "").replace(".", " ").split())
    if not name:
        return ("", "")
    if "," in name:
        surname, _, rest = name.partition(",")
    else:
        parts = name.split()
        surname, rest = parts[-1], " ".join(parts[:-1])
    surname = surname.strip().lower()
    rest = rest.strip()
    return (surname, rest[0].lower() if rest else "")


def has_member_coauthor(author_names: list[str], anchor_names: list[str]) -> bool:
    """True if any anchor member appears in the paper's author list."""
    present = {name_key(n) for n in author_names}
    return any(name_key(a) in present for a in anchor_names)


def fetch_from_arxiv(
    author: dict, start: date, end: date, astro_only: bool = True
) -> list[dict]:
    """Name-based arXiv search. Results can never be ORCID-matched."""
    docs: list[dict] = []
    for variant in author.get("name_variants", []):
        params = urllib.parse.urlencode(
            {
                "search_query": f'au:"{variant}"',
                "start": 0,
                "max_results": 100,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        try:
            payload = http_get(f"{ARXIV_ENDPOINT}?{params}")
        except (urllib.error.URLError, TimeoutError) as exc:
            log(f"  ! arXiv unreachable for {variant!r}: {exc}")
            continue
        finally:
            time.sleep(ARXIV_DELAY)

        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            log(f"  ! arXiv returned unparseable XML for {variant!r}: {exc}")
            continue

        for entry in root.findall("atom:entry", ARXIV_NS):
            published = parse_date((entry.findtext("atom:published", "", ARXIV_NS) or "").strip())
            if published and not (start <= published <= end):
                continue
            categories = [c.get("term", "") for c in entry.findall("atom:category", ARXIV_NS)]
            if astro_only and not any(c.startswith("astro-ph") for c in categories):
                # A same-name researcher in another field. Cheap, decisive filter.
                continue
            docs.append(
                {
                    "title": " ".join((entry.findtext("atom:title", "", ARXIV_NS) or "").split()),
                    "abstract": " ".join(
                        (entry.findtext("atom:summary", "", ARXIV_NS) or "").split()
                    ),
                    "authors": [
                        " ".join((name.text or "").split())
                        for name in entry.findall("atom:author/atom:name", ARXIV_NS)
                    ],
                    "published": published,
                    "arxiv_id": (entry.findtext("atom:id", "", ARXIV_NS) or "")
                    .rstrip("/")
                    .split("/abs/")[-1],
                    "doi": entry.findtext("arxiv:doi", None, ARXIV_NS),
                    "journal_ref": " ".join(
                        (entry.findtext("arxiv:journal_ref", "", ARXIV_NS) or "").split()
                    ),
                    "categories": categories,
                }
            )
    return docs


def arxiv_doc_to_candidate(
    doc: dict, tagger: Tagger, member_keys: set | None = None
) -> dict:
    title = doc["title"]
    tags, keyword_hit = tagger.tag(doc.get("categories", []), f"{title} {doc.get('abstract', '')}")
    doi = normalize_doi(doc.get("doi"))
    published = doc.get("published")
    arxiv_id = doc.get("arxiv_id")

    # arXiv reports the journal reference once a preprint has been published.
    journal_ref = doc.get("journal_ref") or ""
    has_journal = bool(journal_ref)
    publication_info = journal_ref if has_journal else f"arXiv:{arxiv_id}"

    return {
        "source": "arxiv",
        "matched_by_orcid": False,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title_key": normalize_title(title),
        "pub_date": published,
        "has_journal": has_journal,
        "keyword_tag_match": keyword_hit,
        "tags": tags,
        "entry": build_entry(
            title=title,
            authors=doc.get("authors") or [],
            member_keys=member_keys,
            pdf_link=ARXIV_PDF.format(arxiv_id) if arxiv_id else "",
            publication_info=publication_info,
            doi=doi,
            year=published.year if published else date.today().year,
            tags=tags,
        ),
    }


# --------------------------------------------------------------------------
# duplicate detection
# --------------------------------------------------------------------------

class SeenIndex:
    """Tracks what is already published or already queued this run."""

    def __init__(self, existing: list[dict]):
        self.dois: set[str] = set()
        self.arxiv_ids: set[str] = set()
        self.titles: set[str] = set()
        for entry in existing:
            self.add_entry(entry)

    def add_entry(self, entry: dict) -> None:
        doi = normalize_doi((entry.get("doi_link") or "").replace("#", ""))
        if doi:
            self.dois.add(doi)
        info = entry.get("publication_info") or ""
        match = re.search(r"arxiv:\s*([0-9.]+v?\d*)", info, re.IGNORECASE)
        if match:
            self.arxiv_ids.add(match.group(1).split("v")[0])
        title_key = normalize_title(entry.get("title", ""))
        if title_key:
            self.titles.add(title_key)

    def add_candidate(self, candidate: dict) -> None:
        if candidate.get("doi"):
            self.dois.add(candidate["doi"])
        if candidate.get("arxiv_id"):
            self.arxiv_ids.add(str(candidate["arxiv_id"]).split("v")[0])
        if candidate.get("title_key"):
            self.titles.add(candidate["title_key"])

    @staticmethod
    def probe(entry: dict) -> dict:
        """Build a lookup key from a finished publications.json-shaped record."""
        return {
            "doi": normalize_doi((entry.get("doi_link") or "").replace("#", "")),
            "arxiv_id": None,
            "title_key": normalize_title(entry.get("title", "")),
        }

    def contains(self, candidate: dict) -> bool:
        if candidate.get("doi") and candidate["doi"] in self.dois:
            return True
        arxiv_id = candidate.get("arxiv_id")
        if arxiv_id and str(arxiv_id).split("v")[0] in self.arxiv_ids:
            return True
        if candidate.get("title_key") and candidate["title_key"] in self.titles:
            return True
        return False


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------

def is_confident(candidate: dict, tagger: Tagger) -> tuple[bool, list[str]]:
    """Apply the agreed auto-commit rule. Returns (confident, reasons_against)."""
    reasons: list[str] = []
    if not candidate["matched_by_orcid"]:
        reasons.append("matched by author name, not ORCID")
    if tagger.uncategorized in candidate["tags"]:
        reasons.append("no tag matched the tag map")
    elif tagger.require_keyword_match and not candidate["keyword_tag_match"]:
        reasons.append("tag came from a title/abstract guess, not a UAT keyword")
    if not candidate["doi"]:
        reasons.append("no DOI")
    if not candidate["has_journal"]:
        reasons.append("no journal reference (preprint)")
    return (not reasons), reasons


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def merge_into_publications(staged_path: Path) -> int:
    """Merge a staged entry file into publications.json, newest year first.

    Re-checks for duplicates so that applying the same staged file twice, or
    applying a stale branch's file after main has moved on, is a no-op.
    """
    staged = load_json(staged_path)
    existing = load_json(PUBLICATIONS_JSON)
    seen = SeenIndex(existing)

    added = []
    for record in staged:
        entry = {k: v for k, v in record.items() if not k.startswith("_")}
        if seen.contains(SeenIndex.probe(entry)):
            continue
        seen.add_entry(entry)
        added.append(entry)

    if not added:
        log("Nothing to apply — all staged entries are already present.")
        return 0

    merged = added + existing
    merged.sort(key=lambda e: e.get("year", 0), reverse=True)
    PUBLICATIONS_JSON.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    log(f"Applied {len(added)} entries to publications.json")
    return len(added)


def diff_entries(base_path: Path, head_path: Path, out_path: Path) -> int:
    """Write the entries present in head but not in base.

    Used to recover the review branch's still-pending publications by diffing
    its publications.json against main's. Deriving them this way (rather than
    committing a queue file) means the branch can be rebuilt from main each week
    without merge conflicts, it preserves any tag corrections a reviewer made on
    the branch, and it leaves no bookkeeping file behind on main after merge.
    """
    base = load_json(base_path) if base_path.exists() else []
    head = load_json(head_path) if head_path.exists() else []

    seen = SeenIndex(base)
    pending = []
    for record in head:
        if seen.contains(SeenIndex.probe(record)):
            continue
        seen.add_entry(record)
        pending.append(record)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(pending, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    log(f"Recovered {len(pending)} still-pending entries from the review branch")
    return len(pending)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--apply",
        metavar="PATH",
        help="merge a previously staged entry file into publications.json and exit",
    )
    parser.add_argument(
        "--diff-entries",
        nargs=2,
        metavar=("BASE", "HEAD"),
        help="write entries present in HEAD but not BASE to --out, then exit",
    )
    parser.add_argument("--out", metavar="PATH", help="output path for --diff-entries")
    parser.add_argument("--days", type=int, default=7, help="look-back window in days (default 7)")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="ignore --days and search each member's full NADIA window",
    )
    parser.add_argument("--dry-run", action="store_true", help="report only; write no files")
    parser.add_argument(
        "--force-arxiv", action="store_true", help="skip ADS even if ADS_TOKEN is set"
    )
    args = parser.parse_args()

    if args.diff_entries:
        if not args.out:
            parser.error("--diff-entries requires --out")
        diff_entries(Path(args.diff_entries[0]), Path(args.diff_entries[1]), Path(args.out))
        return 0

    if args.apply:
        merge_into_publications(Path(args.apply))
        return 0

    tagger = Tagger(load_json(TAGS_MAP_JSON))
    author_config = load_json(AUTHORS_JSON)
    authors = author_config["authors"]
    existing = load_json(PUBLICATIONS_JSON)
    seen = SeenIndex(existing)

    # Members with an ORCID anchor the name-based searches for those without one.
    require_coauthor = bool(author_config.get("require_member_coauthor", False))
    astro_only = bool(author_config.get("restrict_to_astronomy", True))
    # Used to highlight group members in the rendered author line.
    member_keys = {name_key(v) for a in authors for v in a.get("name_variants", [])}
    anchor_orcids = [(a.get("orcid") or "").strip() for a in authors if (a.get("orcid") or "").strip()]
    anchor_names = [v for a in authors if (a.get("orcid") or "").strip() for v in a.get("name_variants", [])]
    if require_coauthor and not anchor_orcids:
        log("! require_member_coauthor is set but no member has an ORCID; ignoring it")
        require_coauthor = False

    token = "" if args.force_arxiv else os.environ.get("ADS_TOKEN", "").strip()
    if token:
        log("Source: NASA ADS")
    else:
        log("Source: arXiv (ADS_TOKEN not set — name matching only, nothing can auto-commit)")

    today = date.today()
    window_start = today - timedelta(days=args.days)

    confident: list[dict] = []
    uncertain: list[dict] = []

    for author in authors:
        joined, left = membership_window(author)
        if args.backfill:
            start, end = joined, left
        else:
            start, end = max(joined, window_start), min(left, today)
        if start > end:
            log(f"{author['name']}: outside NADIA window, skipping")
            continue

        log(f"{author['name']}: searching {start} .. {end}")
        candidates: list[dict] = []

        own_orcid = (author.get("orcid") or "").strip()
        anchors = anchor_orcids if (require_coauthor and not own_orcid) else []

        if token:
            try:
                for doc, by_orcid in fetch_from_ads(token, author, start, end, anchors, astro_only):
                    candidates.append(ads_doc_to_candidate(doc, tagger, by_orcid, member_keys))
            except urllib.error.HTTPError as exc:
                log(f"  ! ADS rejected the token (HTTP {exc.code}); falling back to arXiv")
                token = ""

        if not token:
            for doc in fetch_from_arxiv(author, start, end, astro_only):
                # arXiv exposes no ORCIDs, so the same constraint is applied by
                # checking the author list for a member who has one.
                if require_coauthor and not own_orcid:
                    # Compare via name_variants: the display names are given in
                    # surname-first order, which name_key would misparse.
                    own_keys = {name_key(v) for v in author.get("name_variants", [])}
                    others = [n for n in anchor_names if name_key(n) not in own_keys]
                    if not has_member_coauthor(doc.get("authors") or [], others):
                        continue
                candidates.append(arxiv_doc_to_candidate(doc, tagger, member_keys))

        for candidate in candidates:
            if not in_membership_window(candidate["pub_date"], author):
                continue
            if seen.contains(candidate):
                continue
            seen.add_candidate(candidate)

            ok, reasons = is_confident(candidate, tagger)
            if ok:
                confident.append(candidate)
                log(f"  + [auto] {candidate['entry']['title'][:70]}")
            else:
                candidate["review_reasons"] = reasons
                candidate["matched_member"] = author["name"]
                uncertain.append(candidate)
                log(f"  ? [review] {candidate['entry']['title'][:70]} — {'; '.join(reasons)}")

    log("")
    log(f"{len(confident)} confident, {len(uncertain)} needing review")

    # Written before the dry-run bail-out so the workflow's step conditions always
    # see real numbers rather than an empty string.
    summary_path = os.environ.get("GITHUB_OUTPUT")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(f"confident_count={len(confident)}\n")
            handle.write(f"uncertain_count={len(uncertain)}\n")

    if args.dry_run:
        log("Dry run — no files written.")
        return 0

    STAGE_DIR.mkdir(exist_ok=True)

    # Confident entries are clean records ready to merge as-is.
    (STAGE_DIR / "confident.json").write_text(
        json.dumps([c["entry"] for c in confident], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Uncertain entries carry _review metadata for the PR body. The `--apply`
    # step strips any underscore-prefixed key, so it never reaches the site.
    pending = []
    for candidate in uncertain:
        record = dict(candidate["entry"])
        record["_review"] = {
            "matched_member": candidate["matched_member"],
            "source": candidate["source"],
            "reasons": candidate["review_reasons"],
        }
        pending.append(record)
    (STAGE_DIR / "uncertain.json").write_text(
        json.dumps(pending, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
