# Automated publication fetching

`.github/workflows/publications.yml` runs every Monday at 01:00 UTC (09:00 Singapore
time) and adds newly published papers by NADIA members to `publications.json`.

It only ever **adds** entries. Nothing already in the list is rewritten or removed,
and entries added by hand are left alone.

## One-time setup

Add a free [NASA ADS API token](https://ui.adsabs.harvard.edu/user/settings/token)
as the repository secret **`ADS_TOKEN`** (Settings → Secrets and variables → Actions).

Without the token the workflow falls back to arXiv. That still produces good
entries — arXiv reports the journal reference and DOI once a preprint is published
— but it can only match on author name, and the auto-commit bar requires an ORCID
match. So without the token every result lands in the review pull request. It
works; it is just more to review.

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

ORCIDs are on record for Marc Hon, Riley Clarke and Matthew Sung. The other five
members have none — see *Known limitations*.

### Two switches at the top of `authors.json`

`restrict_to_astronomy` (default `true`) accepts only astronomy results: ADS
`database:astronomy`, arXiv `astro-ph` categories. Without it a name search for
`Clarke, R.` returns particle-accelerator and elastomer-actuator papers by unrelated
researchers — that is measured, not hypothetical.

`require_member_coauthor` (default `true`) makes a name-based ADS search additionally
require the ORCID of a member who has one, and the arXiv equivalent check the author
list for that member. This is what keeps `Wu, Y.` and `Lin, Y.` usable. The trade-off
is that a solo paper, or one with no ORCID-carrying member as co-author, will be
missed. Members who have their own ORCID are unaffected.

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

### Testing on a branch before merging

Pushing to the `publications-automation` branch runs the workflow in **read-only**
mode. Any ref other than the default branch skips every write step: nothing is
committed, no branch is touched, no pull request is opened.

Instead the run uploads a **`publications-preview`** artifact containing:

| File | What it is |
|---|---|
| `publications.json` | the full list as it *would* look, for local preview |
| `publications.before.json` | the current list, for diffing |
| `staged-confident.json` | entries that would auto-commit to `main` |
| `staged-uncertain.json` | entries that would go to the review PR, with reasons |
| `review-notes.md` | the pull request body that would have been posted |

The job summary shows both counts and the full review notes without downloading
anything. To preview the rendered page, copy the artifact's `publications.json` over
`publications/publications.json` locally, serve the site, then `git checkout --
publications/publications.json` to discard it.

Set the `ADS_TOKEN` secret **before** the test run, otherwise it silently falls back
to arXiv and you will not be testing what you think you are. The run emits a warning
annotation when the secret is missing.

Note that GitHub Pages serves one site per repository, so there is no way to deploy a
branch for preview without replacing the live site. Use the artifact instead.

### Backfilling the existing list

`--backfill` searches each member's whole membership window instead of the last week.
Run it once, with `--dry-run` first, after you have filled in real `joined` dates and
as many ORCIDs as you can. Expect most results to land in the review PR the first
time; that is the intended behaviour, since a backfill is exactly when a name-based
search is most likely to pull in a stranger's paper.

## Known limitations

- **Five of eight members have no ORCID:** Rishi Chandramohan, Lin Yihan, Wu Yuzhe,
  Wu Yuxin and Nguyen Thai Huy. A search of the ORCID registry found no record for
  Rishi at all, and nothing distinguishing among the 21/14/94 candidates for the
  other names. Their papers therefore fall back to name search and can never
  auto-commit. Asking them to register at [orcid.org](https://orcid.org) is the
  single highest-value fix available.

- **Auto-tagging is approximate.** Against the five publications already on the site,
  title-only tagging reproduces the hand-assigned tags exactly for 2 of 5. Real runs
  also see the abstract and UAT keywords, so accuracy is better than that — but assume
  new entries need a glance rather than trusting them blindly. Improve accuracy by
  adding keywords and patterns to `tags-map.json` as you spot misses.
- **The tag vocabulary does not yet cover time-domain astronomy.** A trial run tagged
  Riley Clarke's stellar-flare and LSST papers `Uncategorized`, because the vocabulary
  is built around asteroseismology, exoplanets and ML. Consider adding tags such as
  *Time-Domain Astronomy*, *Variable Stars* or *Microlensing* to match what the group
  actually works on now.
- **Preprints never auto-commit.** They have no DOI or journal reference. A preprint
  appears in the review PR; once it is published, ADS returns the journal version and
  the duplicate check matches it by title, so it will not be added twice.

## Links

`pdf_link` points at the free arXiv PDF whenever the paper has an arXiv identifier.
`doi_link` points at the version of record, and is an **empty string** when the paper
has no DOI yet.

`publications.js` renders each button only when its link has a real target, treating
both `""` and the legacy `"#"` placeholder as "no link". So a preprint shows a PDF
button and no DOI button, and the five original hand-written entries — which all
carry `pdf_link: "#"` — no longer show a dead PDF button. Fill those in by hand if
you have the URLs.
