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
    KB-FIRST review. Queries the knowledge graph (kb.query --search/--unit via
    the kb/ layer, DOMAIN_SIGNALS per stage) for the obligations relevant to
    the artifact, then fetches each unit's text and assesses applicability
    against it. Reports include a "Relevant obligations" section. Seed rules
    (rules.json) are triggers, not the assessment. Falls back to raw article
    markdown when the kb/ layer is absent. (+ LLM adjudication when
    config.llm_command is set.) Used by background review and the compliance_review tool.

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
- Gate block path verified live in a real OpenCode session (2026-09-12):
  a violating write to `src/` was refused (exit 2, rules MANIP-01 + SOC-01,
  ~2.6ms), the file never landed, the ledger recorded the block. Fixed in
  the process: `short_verdict` zipped the rules set against the deduped
  citation set, mispairing SOC-01 with Art. 5(1)(b); it now maps rule →
  citations from the findings. All three verdict paths re-verified after
  the fix (block/warn/clean).
- Plugin verified live in an OpenCode 1.18.30 session (2026-09-12):
  `tool.execute.before` payload field is `filePath` for write/edit/read/bash;
  `write` carries `content`, `edit` carries `oldString`/`newString` (no content —
  candidate reconstruction needed, as implemented). `file.edited` properties
  carry `file` (absolute path). Gate + background review confirmed end to end:
  two `fast` gate entries and one `llm` review entry for `src/smoke-demo.ts`
  in the ledger, correct session ID, ~2ms latency.
- KB-first review verified against the real graph in a `ml_kb-layer` worktree:
  relevance search returns node ids; clean-doc review retrieves Art. 11/13/18
  units with no rules fired; reports carry the "Relevant obligations" section.
- Adjudicator (Tier 2) wired and verified: built-in OpenAI-compatible call to
  the local vLLM endpoint (config `llm` block, key via `api_key_env` name,
  never stored in config), judged each retrieved obligation's applicability
  concretely and quoted the artifact. External `llm_command` script overrides
  when set.
- CI workflow `.github/workflows/compliance-scan.yml`: scan on PR/push, report
  to `$GITHUB_STEP_SUMMARY` + artifact, PR fails only on block verdicts
  (warn passes). Verified locally via `--scan`; remote run pending push.

## Rules format

Tier 1 rules are line-scoped: every regex in a pattern group must match
within the same line (case-insensitive). A rule fires if any group matches.
`severity: block|warn` maps to exit 2/1. `stage` limits the rule to those
lifecycle stages. Disclosure rules check UI-surface files for AI mentions
without a required disclosure string (Art. 50). Article citations are
verifiable against `data/eu-ai-act/articles/` once the corpus lands.
