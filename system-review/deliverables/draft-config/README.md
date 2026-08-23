# `draft-config/` — proposed configuration, none of it applied

Everything in this directory is a **draft**. Per KICKOFF §2.2 this review makes no source
edits: nothing here has been copied into the repository, and none of it has been executed.

Read `../STANDARDS-PROPOSAL.md` first — it is the argument. These are its attachments.

| File | Target path | Status |
|---|---|---|
| `ruff.toml` | `<root>/ruff.toml` | never run against `src/` |
| `editorconfig` | `<root>/.editorconfig` | inert by nature; safe |
| `checks.yml` | `<root>/.github/workflows/checks.yml` | never executed; YAML parses |
| `docs-split.md` | an edit to the existing `.github/workflows/docs.yml` | not applied |

`editorconfig` is stored without its leading dot so it is visible in a directory listing.
Rename it on adoption.

## Adoption order

`../STANDARDS-PROPOSAL.md` §9 has the full table with effort and risk. The short version:
`.editorconfig`, then the `docs.yml` split, then shellcheck, then ruff, then the drift
checks. Items 1–7 are about one focused day and cover every mechanical finding in the
ledger.

## The one thing not to skip

`ruff.toml` carries a block comment forbidding `ERA001`. That is not decoration. F-133
catalogued 47 comments in this codebase that encode *why* — including two experiments that
were tried and falsified — and several of them are commented-out code kept deliberately.
`ERA001` would delete them and the diff would look like housekeeping.
