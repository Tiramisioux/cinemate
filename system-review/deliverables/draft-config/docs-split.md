# The `docs.yml` edit — split build from deploy

**DRAFT — not applied.** Target file: `.github/workflows/docs.yml`.
Evidence: F-006, and `findings/F-006.md` for the trap.

---

## Why this is the highest value-per-effort change in the ledger

`docs.yml` is the repository's only workflow. It triggers on:

```yaml
on:
  push:
    branches:
      - main
  workflow_dispatch:
```

Development happens on `dev`. Pull requests therefore get **zero checks** — PR #129 has
none — and the 27 test files under `_test/` have never been executed by anything.

Making CI run on pull requests is a three-line change to the `on:` block. The reason it is
not *just* a three-line change is the trap below.

---

## The trap: two steps publish, and they run unconditionally

Adding `pull_request` to the trigger list without touching anything else means **every pull
request would publish the documentation site and push a commit to the branch.**

Two steps are responsible. Neither has a condition today:

1. **`Deploy to GitHub Pages`** — `peaceiris/actions-gh-pages@v4` with
   `publish_branch: gh-pages` and `allow_empty_commit: true`. On a PR build this force-
   publishes whatever that PR's docs happen to look like. `allow_empty_commit` means it
   publishes even when nothing changed.

2. **`Copy PDF to docs/renders and push`** — runs `git config`, `git add`, `git commit`,
   `git push`. On a PR from a branch this pushes a commit onto that branch mid-review. From
   a fork it fails outright, because `GITHUB_TOKEN` on a fork PR is read-only.

The workflow also holds `contents: write`, `pages: write` and `id-token: write` at the top
level, so a PR build would run with full publish rights.

---

## The edit

**1. Widen the trigger.**

```yaml
on:
  push:
    branches:
      - main
      - dev
  pull_request:
  workflow_dispatch:
```

**2. Guard the two publishing steps.** Add the same condition to each:

```yaml
      - name: Deploy to GitHub Pages
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: peaceiris/actions-gh-pages@v4
        # ... rest unchanged
```

```yaml
      - name: Copy PDF to docs/renders and push
        if: >
          github.event_name == 'push' &&
          github.ref == 'refs/heads/main' &&
          steps.rendered_pdf.outputs.exists == 'true'
        run: |
        # ... rest unchanged
```

Note the second one already has an `if:` (`steps.rendered_pdf.outputs.exists == 'true'`) —
the new condition must be **added to** it, not replace it.

**3. Optional but recommended — narrow the default permissions.** Move the write scopes off
the workflow and onto the job, or gate them, so a PR build cannot publish even if a
condition is later dropped by mistake. The minimum viable version is to leave the block
alone; the safer version sets `permissions: contents: read` at the top and grants the write
scopes only where they are needed.

---

## What this buys, immediately

- Broken docs, a missing include, or a failed `mkdocs build` gets caught **on the pull
  request** instead of after merge to `main`.
- `dev` — where the work actually happens — gets built.
- Nothing publishes from a pull request.
- The workflow becomes the place the `checks.yml` jobs can sit alongside, so the repo has
  one obvious answer to "what runs on a PR?"

## What it does not buy

It does not run any tests. That is `checks.yml`, and the test job there is blocked on
PI-002 for anything beyond discovery mode.

---

## Confidence

`confirmed` — every line quoted above was read from `.github/workflows/docs.yml` in this
repository. The *behaviour* of the guarded workflow is `unverified`: no Actions run has
executed this edit. The conditions are standard GitHub Actions expressions, but the first
adoption should be watched on one PR before trusting it.
