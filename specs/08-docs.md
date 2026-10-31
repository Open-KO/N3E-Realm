# 08 — Docs on Pages (AI-friendly)

Implements flow Ⓔ and Pushback #8 from `architecture.md`.

## Purpose

Publish the repo's documentation to GitHub Pages in a form that an agent (and any other
AI tooling) can consume without a browser: plain Markdown, a stable index, no
JS-rendered content. The **source of truth remains the repo at the commit being worked
on**; Pages is for external consumers and for the agent's cross-repo reading.

## Scope

In: what gets published, the index format, the build step, URL stability. Out: a human
documentation site with navigation and search (if wanted later, it is a second output
of the same build, never a replacement).

## Interfaces

### What is published

From `N3E-Realm`:

```
/                      index.md  (rendered as plain Markdown, not HTML — see Build)
/llms.txt              index for AI consumers (format below)
/llms-full.txt         concatenation of every published .md, in llms.txt order, with
                       `# File: <path>` separators; ≤ 2 MiB or the build fails
/specs/*.md            this folder
/architecture.md
/docs/**/*.md          operator and player docs
/runbooks/*.md         the runbook sections of spec 07, extracted (single source: spec 07)
/api/admin.md          generated from spec 03's route tables (or hand-kept — Q17)
/releases.md           generated: last 20 Releases with version, date, content hash
/status.json           generated at build: {release, commit, published_at}  — NOT live realm status
```

Nothing from `n3e` is republished (separate repo, its own docs).

### `llms.txt`

Follows the llms.txt convention:

```
# N3E Realm

> Operator, deployment and architecture documentation for the N3E Realm community game server.

## Architecture
- [Architecture](https://<pages>/architecture.md): decisions, flows, trade-offs
- [Roadmap](https://<pages>/specs/00-roadmap.md): build order

## Specs
- [01 Connection hardening](…/specs/01-connection-hardening.md): …
…

## Runbooks
- [R1 Fresh host](…/runbooks/r1-fresh-host.md): …

## Optional
- [Releases](…/releases.md): recent releases and content hashes
```

One line per document, with a one-sentence description taken from the document's first
paragraph (build step extracts it; a document may override with an HTML comment
`<!-- llms: … -->` on line 2).

## Build

- A script `tools/docs-build.py` (stdlib only) copies `.md` files verbatim into `site/`,
  generates `llms.txt`, `llms-full.txt`, `releases.md`, `status.json`, and
  `index.md`.
- **No static-site generator.** Pages serves `.md` files as `text/markdown`; that is the
  point. Add a `.nojekyll` file so GitHub does not try to render them.
- Links inside documents are kept **relative** so they work in the repo and on Pages.
  The build fails on a broken relative link (check every `](…)` target exists).
- Runs in the `publish` job of spec 06 after the Release exists, so `releases.md` can
  include it.

## Behaviour notes

- Pages URL is stable; documents are addressed by repo path. Renaming a document is a
  breaking change for consumers — add a one-line stub at the old path pointing to the
  new one for one release.
- Secrets check: the build greps the output for patterns of the tokens used in this
  project (base64url 43 chars, `ghp_`, `Bot ` tokens) and fails on any hit.

## Acceptance tests

1. After a CD run, `curl https://<pages>/llms.txt` lists every `.md` under `specs/`,
   `docs/`, and `architecture.md`.
2. `llms-full.txt` contains every listed document exactly once, in order.
3. Introduce a broken relative link → build fails with the file and line.
4. `releases.md` shows the just-published release at the top.
5. Response headers for a `.md` are `text/markdown` (or at worst `text/plain`), never
   `text/html`.

## Open questions

Q17.
