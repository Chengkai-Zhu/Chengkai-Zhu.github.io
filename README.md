# Chengkai Zhu's personal website

A bespoke academic homepage for Chengkai Zhu, Scientist at QudeLeap. The site uses serif typography, a portrait sidebar, and a compact research bibliography. It is independent of Academic Pages and Jekyll, with no frontend framework, JavaScript bundle, remote fonts, or third-party runtime assets.

## Preview locally

Building the website requires Python 3.9 or newer and no packages:

```sh
python3 scripts/build.py
python3 scripts/check_site.py
python3 -m http.server 8000 --directory _site
```

Open `http://localhost:8000`. The build output lives in `_site/` and is not committed.

## Edit content

- `data/profile.json`: identity, contact details, education, and teaching.
- `data/publications.json`: curated papers, publication metadata, and selected collaborations.
- `data/synced_publications.json`: automatically discovered first-author papers.
- `templates/`: shared page structure and the About, Research, and Teaching content.
- `assets/style.css`: the complete responsive stylesheet.

Every paper needs a title, ordered author list, ISO date, venue, `abstract_url`, and `pdf_url`. Optional `doi_url` and `code_url` fields produce Journal and Code links. Papers are grouped by year and sorted by date, most recent first. Only the first author is used to determine inclusion in the first-author section; other contributions can be curated separately.

Curated metadata takes precedence over automatic metadata, while a verified journal record is never replaced by a preprint record. Existing publications are retained when an upstream source omits them. Important old URLs redirect to their new equivalents.

## Monthly publication sync

The `Build and deploy homepage` GitHub Actions workflow runs on the first of every month at **09:17 Asia/Shanghai** (01:17 UTC). Manual runs can enable the **Update first-author publications before deployment** checkbox; a manual build without syncing works even while external sources are unavailable. Each scheduled sync fetches the public Google Scholar profile `2c0ZBk8AAAAJ`, verifies the full author order, checks arXiv, merges new first-author records, validates the website, commits the data with an English message, and deploys the result in the same workflow.

Google Scholar can block automated requests; it has no public publication API suitable for this integration. The script uses arXiv as an independent fallback and records which source succeeded in `data/sync_status.json`. An arXiv fallback is **not** a successful Scholar sync and will not discover papers available only on Scholar. If both sources fail, the run fails without replacing the publication data or the live site. Papers without a verified PDF link are listed in the sync report for manual completion rather than receiving a fabricated link.

To sync locally:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/sync_publications.py --dry-run
.venv/bin/python scripts/sync_publications.py
.venv/bin/python -m unittest discover -s tests -v
```

The default public-page/arXiv mode requires no API key. For Scholar access through a supported API provider, optionally add a `SERPAPI_API_KEY` repository secret in **Settings → Secrets and variables → Actions**. The sync then retrieves the same Scholar pages through the [Google Scholar Author API](https://serpapi.com/google-scholar-author-api), including citation details and full author order. This requires a SerpApi account and sufficient API quota; no account, plan, or secret was created by this refactor. Without that secret, direct Scholar access remains subject to Google's automated-access restrictions.

Joint first authors are automatically included only when Chengkai is listed first; equal-contribution papers in a different author position can be added to the curated file after verification.

## GitHub Pages

See [deployment notes](docs/deployment.md). The custom domain remains `chengkaizhu.site`.

The workflow deliberately deploys after the automated data commit: commits made using `GITHUB_TOKEN` do not trigger another Pages build. See [GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token).

GitHub may delay scheduled jobs, and public-repository schedules can be disabled after 60 days of inactivity. The monthly sync writes its check timestamp whenever at least one source succeeds, making successful checks visible in Git history. If all sources keep failing, inspect Actions and re-enable the schedule if GitHub disables it. See [scheduled workflow documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## License

The original MIT license notice is retained in `LICENSE`.
