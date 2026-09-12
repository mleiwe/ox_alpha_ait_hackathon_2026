# Project guidance for agents

## Compliance middleware (this repo's product)

This repo contains a compliance middleware that reviews AI-product surface
files against the EU AI Act. It is wired into OpenCode via
`.opencode/plugins/compliance-gate.ts`.

- Writes to product-surface files (per `compliance/config.json` stage globs:
  planning artifacts like PRDs, implementation files like `src/**`,
  `prompts/**`, agent code) are gated: a Tier 1 deterministic check runs
  before the write lands. Exit 2 = the write is refused with article
  citations. This is intentional; do not bypass it or re-apply the same
  content unchanged.
- On refusal: read the full report path in the refusal message, fix the
  flagged lines, or run the `compliance_review` tool on the file for the
  detailed verdict.
- `compliance_review` (custom tool): full review of any file with KB excerpts
  and article citations. Use it before committing PRDs or product AI-surface
  code, even when the gate did not fire.
- The ledger is `.compliance/ledger.jsonl`; render it with
  `compliance/compliance-check --ledger`. Never edit it by hand.

## Repo layout

- `compliance/` — middleware CLI, rules, config, contract doc (README.md).
- `data/eu-ai-act/` — markdown corpus (arrives via PR #1; KB excerpts read
  `data/eu-ai-act/articles/`).
- `.opencode/` — plugin adapter + package pin.

## Conventions

- The CLI (`compliance/compliance-check`) is the only writer of ledger and
  reports. Never write to `.compliance/` directly.
- Stage classification is config-driven (`compliance/config.json`
  `stage_globs`); keep it current when the repo layout changes.
- Commits stay local until the team says push.
