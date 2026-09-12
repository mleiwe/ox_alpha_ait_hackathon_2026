# compliance middleware

EU AI Act compliance review embedded in the development harness. One binary,
several entry points; the same CLI serves the OpenCode plugin, Hermes hooks,
and CI.

## Components

| Piece | Role |
|---|---|
| `compliance-check` | The middleware CLI. The only writer (ledger + reports). Callers only invoke. |
| `config.json` | KB path, ledger/report paths, stage globs, LLM adjudicator hook. |
| `rules.json` | Tier 1 deterministic rules: pattern groups, severities, article citations. Seed set; Marcus's KB output supersedes. |
| `.opencode/plugins/compliance-gate.ts` | OpenCode adapter: gate, ambient toasts, `compliance_review` tool. |
| `.opencode/package.json` | Pins `@opencode-ai/plugin` 1.18.29 (bun installs at OpenCode startup). |

## The CLI contract

```
compliance/compliance-check --fast --file <p> [--content <s>] [--session <id>]
    Tier 1 scan. stdout: short verdict (~300 chars). exit 0 clean / 1 warn / 2 block.
    Used by the OpenCode gate (throw on exit 2 = write refused) and Hermes pre_tool_call.

compliance/compliance-check --llm --file <p> [--json]
    Tier 1 + KB excerpts from data/eu-ai-act/articles/ (+ LLM adjudication when
    config.llm_command is set). Used by background review and the compliance_review tool.

compliance/compliance-check --report --session <id>
    Aggregate one session's ledger entries. Fired on OpenCode session.idle.

compliance/compliance-check --scan [--base origin/main | --files a,b,c]
    Repo-scale drift net; writes .compliance/scan-report.md. CI step.

compliance/compliance-check --ledger [--tail N]
    Render the ledger table (ts, stage, mode, verdict, rules, citations).
```

## Design invariants

1. **The CLI is the only writer.** Ledger `.compliance/ledger.jsonl` and all
   reports are written by `compliance-check`; the plugin, Hermes hooks, and CI
   only invoke it. One writer means the audit trail cannot fork.
2. **Stage is config, never inference.** `config.json` `stage_globs` map
   artifact path to lifecycle stage (first match wins, case-insensitive).
   Gate decisions stay reproducible and auditable.
3. **Verdicts are short; detail lives on disk.** The conversation/TUI sees
   ~300 characters with article citations; full reports go to `.compliance/`.
4. **Scope: the product, not the developer.** Gates fire on writes to
   product-surface files (planning/implementation stages per config). Tool
   calls, READMEs, and business code pass untouched.

## Verification state

- `compliance-check` verified end to end: block/warn/clean exits, PRD +
  product-file catches, disclosure gap, ledger, session report, scan mode.
- Plugin parsed via bun; hook payload field names (`filePath` vs `path`,
  presence of `content`) still need a live smoke test in an OpenCode session
  (log `JSON.stringify({tool: input.tool, args: output.args})` once).
- KB excerpts empty until PR #1 (`ml_eu-ai-act-markdown`) merges and populates
  `data/eu-ai-act/`; until then citations come from `rules.json`.
- Adjudicator LLM (Tier 2 deep review) is a config slot (`llm_command`), not
  wired yet.

## Rules format

Tier 1 rules are line-scoped: every regex in a pattern group must match
within the same line (case-insensitive). A rule fires if any group matches.
`severity: block|warn` maps to exit 2/1. `stage` limits the rule to those
lifecycle stages. Disclosure rules check UI-surface files for AI mentions
without a required disclosure string (Art. 50). Article citations are
verifiable against `data/eu-ai-act/articles/` once the corpus lands.
