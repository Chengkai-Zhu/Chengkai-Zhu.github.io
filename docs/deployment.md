# Deployment

The website is built by Python and published with the official GitHub Pages Actions. There is no Jekyll theme or package manager involved in the build.

## One-time migration

1. Merge the refactor into `master`.
2. In the repository's **Settings → Pages → Build and deployment**, select **GitHub Actions** as the source. Keep the existing custom domain and HTTPS settings.
3. Run **Build and deploy homepage** from the Actions tab. Verify both the build and deployment jobs, then check `https://chengkaizhu.site/`.

For Scholar access through SerpApi, optionally configure the `SERPAPI_API_KEY` repository secret before a manual sync. The website itself does not need this key. Direct Scholar/arXiv requests both returned HTTP 429 during local integration testing on October 5, 2026; the full live sync remains unverified until a source is available. Unit tests cover the API routing, authorship checks, and failure handling.

The equivalent source migration command is:

```sh
gh api --method PUT repos/Chengkai-Zhu/Chengkai-Zhu.github.io/pages -f build_type=workflow
```

Pull requests run the tests, build the site, validate local links, and upload a `homepage-preview` artifact. They do not sync publication data or deploy the production site.

## Monthly runs

Scheduled syncs on `master` write only `data/synced_publications.json` and `data/sync_status.json` back to the repository. To sync manually, enable **Update first-author publications before deployment** in **Run workflow**. The workflow then deploys the already validated site. Run summaries show whether Scholar, arXiv, or both were available. Network failures do not erase existing papers. Manual builds with syncing unchecked do not depend on either publication source.

The first scheduled run after an October 2026 migration is November 1, 2026, at 09:17 Asia/Shanghai, subject to GitHub scheduler delays.

## Recovery

If a publication is incorrect, correct or exclude it in the data files and run the build checks. If a sync fails, use **Run workflow** after the source recovers. To restore a previous design, revert the refactor commit and change the Pages source back to the original `master` branch deployment.
