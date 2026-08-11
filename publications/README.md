# Automated publication fetching

`.github/workflows/publications.yml` runs every Monday at 01:00 UTC (09:00 Singapore
time) and adds newly published papers by NADIA members to `publications.json`.

It only ever **adds** entries. Nothing already in the list is rewritten or removed,
and entries added by hand are left alone.

## One-time setup

Add a free [NASA ADS API token](https://ui.adsabs.harvard.edu/user/settings/token)
as the repository secret **`ADS_TOKEN`** (Settings → Secrets and variables → Actions).

Without the token the workflow falls back to arXiv, which matches on author name
only and has no DOIs. In that state nothing can meet the auto-commit bar, so every
result lands in the review pull request instead. It still works — it is just noisier.

## The two files you edit

### `authors.json` — who to search for

```json
{
  "name": "Marc Hon",
  "orcid": "0000-0000-0000-0000",
  "name_variants": ["Hon, M.", "Hon, Marc"],
  "joined": "2025-01-01",
  "left": null
}
```

| Field | Meaning |
|---|---|
| `orcid` | The reliable matcher. Set this whenever you can — see below. |
| `name_variants` | Searched only when `orcid` is `null`. Use ADS's `Surname, F.` form. |
| `joined` | First day of NADIA membership. Earlier papers are ignored. |
| `left` | Last day of membership, or `null` for current members. Later papers are ignored. |

The `joined`/`left` window is what keeps the list accurate as people come and go:
alumni keep the papers they published while they were here, and nothing they publish
afterwards is picked up.

> **The `joined` dates currently in the file are placeholders.** Replace them with
> real dates, otherwise the backfill will pull in the wrong range of papers.

**Why ORCID matters.** A name search for `Wu, Y.` matches a great many astronomers
who are not in this group. ORCID is exact, and it is the difference between a paper
appearing on the site automatically and sitting in a PR waiting for someone to check
it. Members can find or create theirs at [orcid.org](https://orcid.org).

### `tags-map.json` — how tags get assigned

`vocabulary` is the closed set of allowed tags. The fetcher will never emit a tag
outside it, so the topic filter on the page stays clean.

Each rule assigns its tag when either:

- one of its `keywords` appears in the paper's ADS/UAT keyword list (a strong signal), or
- one of its `patterns` (regex, case-insensitive) matches the title + abstract (a guess).

`implies` adds broader tags automatically — a Deep Learning match also tags Machine
Learning, matching how the existing entries are tagged.

Papers that match nothing get the `Uncategorized` tag and are always routed to the
review PR. To require the stronger signal for auto-commit, set
`"require_keyword_match": true`.

**Tagging is the part most likely to need your attention.** See the caveats below.

## Where results go

Each paper found is classified. It is committed straight to `main` only if **all four**
hold:

1. matched to a member via ORCID, not a name search
2. at least one real tag from the vocabulary
3. has a DOI
4. has a journal reference, not just an arXiv identifier

Everything else — name-matched, `Uncategorized`, or a preprint — is added to a rolling
review pull request on the `publications-review` branch. Fix the tags there, delete
anything that was matched to the wrong person, and merge.

**Weeks with nothing new produce no commit and no pull request.** Silence means
nothing was found.

### How the review branch avoids conflicts

Each run rebuilds `publications-review` from the current `main` rather than merging
into it. Entries still awaiting review are recovered by diffing the branch's
`publications.json` against `main`'s, which means tag corrections made inside the PR
survive the rebuild. If the branch contains commits by anyone other than the bot, it
is left untouched and the run says so in its summary rather than overwriting work.

## Running it by hand

Actions tab → **Fetch new publications** → **Run workflow**, which exposes `days`,
`backfill` and `dry_run`. Or locally:

```bash
export ADS_TOKEN=...                                  # optional; arXiv fallback without it

python3 scripts/fetch_publications.py --dry-run       # report only, write nothing
python3 scripts/fetch_publications.py --days 30       # widen the look-back window
python3 scripts/fetch_publications.py --backfill      # each member's full NADIA window
```

A dry run writes nothing and is the right way to sanity-check `authors.json` and
`tags-map.json` after editing them.

### Backfilling the existing list

`--backfill` searches each member's whole membership window instead of the last week.
Run it once, with `--dry-run` first, after you have filled in real `joined` dates and
as many ORCIDs as you can. Expect most results to land in the review PR the first
time; that is the intended behaviour, since a backfill is exactly when a name-based
search is most likely to pull in a stranger's paper.

## Known limitations

- **Auto-tagging is approximate.** Against the five publications already on the site,
  title-only tagging reproduces the hand-assigned tags exactly for 2 of 5. Real runs
  also see the abstract and UAT keywords, so accuracy is better than that — but assume
  new entries need a glance rather than trusting them blindly. Improve accuracy by
  adding keywords and patterns to `tags-map.json` as you spot misses.
- **`pdf_link` is always `#`.** Neither ADS nor arXiv reliably gives a free full-text
  PDF URL, and the existing entries use `#` too. Fill it in by hand where you have one.
- **Preprints never auto-commit.** They have no DOI or journal reference. A preprint
  appears in the review PR; once it is published, ADS returns the journal version and
  the duplicate check matches it by title, so it will not be added twice.
