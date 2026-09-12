// compliance-gate — OpenCode plugin adapter for the compliance middleware.
//
// Thin by design: every substantive decision lives in compliance/compliance-check.
// This file only intercepts, invokes, and toasts. See compliance/README.md.
//
// Hook types verified against @opencode-ai/plugin 1.18.29 (dist/index.d.ts):
//   "tool.execute.before" (input: {tool, sessionID, callID}, output: {args: any})
//   event: (input: {event: Event}) => Promise<void>   — EventFileEdited {file},
//     EventSessionIdle {sessionID} (sdk dist/gen/types.gen.d.ts)
//   tool: { [name]: ToolDefinition }                  — custom tools
//   client.tui.showToast({message, variant})          — TUI toast
import type { Plugin } from "@opencode-ai/plugin"
import { tool } from "@opencode-ai/plugin"
import { readFileSync } from "node:fs"
import { join, isAbsolute, relative } from "node:path"

const CLI_FALLBACK = join(process.env.HOME || "~", ".config/compliance/compliance-check")
const CLI = "compliance/compliance-check"
const GATED_TOOLS = ["write", "edit", "patch"]
const GATED_STAGES = new Set(["planning", "implementation"])
const DEBOUNCE_MS = 30_000

function loadConfig(directory: string): any {
  try {
    const cfg = JSON.parse(readFileSync(join(directory, "compliance/config.json"), "utf-8"))
    return { ...cfg, _source: "repo" }
  } catch {
    // not a compliance repo: fall back to the global install so any
    // workspace gets the middleware
    try {
      const cfg = JSON.parse(readFileSync(CLI_FALLBACK.replace("compliance-check", "config.json"), "utf-8"))
      return { ...cfg, _source: "global" }
    } catch {
      return null
    }
  }
}

// Repo has its own CLI copy; a bare workspace uses the global install.
const cliPath = (cfg: any) => (cfg._source === "global" ? CLI_FALLBACK : CLI)

function stageOf(relPath: string, cfg: any): string {
  const p = relPath.toLowerCase()
  for (const [stage, globs] of Object.entries(cfg.stage_globs) as [string, string[]][]) {
    for (const g of globs) {
      const gl = g.toLowerCase()
      if (new Bun.Glob(gl).match(p) || new Bun.Glob(gl.replace(/\/$/, "") + "/*").match(p)) {
        return stage
      }
    }
  }
  return cfg.default_stage || "other"
}

export const ComplianceGate: Plugin = async ({ client, $, directory, worktree }) => {
  const cfg = loadConfig(worktree || directory)
  if (!cfg) return {} // no config in this worktree: middleware off

  const root = worktree || directory
  const lastReview = new Map<string, number>()
  const rel = (p: string) => (isAbsolute(p) ? relative(root, p) : p)
  const resolve = (p: string) => (isAbsolute(p) ? p : join(root, p))

  // Candidate content for the edit BEFORE it lands: write->content,
  // edit/patch->oldString replaced by newString in the on-disk file.
  function candidateContent(args: any): string | null {
    const p = args?.filePath ?? args?.path ?? args?.file
    if (!p) return null
    if (typeof args?.content === "string") return args.content
    try {
      const current = readFileSync(resolve(p), "utf-8")
      if (typeof args?.oldString === "string" && typeof args?.newString === "string") {
        return current.replace(args.oldString, args.newString)
      }
      return current
    } catch {
      return typeof args?.newString === "string" ? args.newString : null
    }
  }

  return {
    // ── 1. Gate: synchronous Tier 1 on product-surface writes. Exit 2 aborts the call. ──
    "tool.execute.before": async (input, output) => {
      if (!GATED_TOOLS.includes(input.tool)) return
      const p = output.args?.filePath ?? output.args?.path ?? output.args?.file
      if (!p) return
      const stage = stageOf(rel(p), cfg)
      if (!GATED_STAGES.has(stage)) return // README/tests/business code pass untouched
      const content = candidateContent(output.args)
      const cli = cliPath(cfg)
      const cmd = [cli, "--fast", "--file", resolve(p), "--session", input.sessionID]
      if (content !== null) cmd.push("--content", content)
      const proc = await $`python3 ${cmd}`.quiet().nothrow()
      if (proc.exitCode === 2) {
        // The thrown error becomes the failed tool result the model sees.
        throw new Error(
          `COMPLIANCE_BLOCKED — write refused by compliance middleware\n${proc.text().trim()}`,
        )
      }
      // exit 1 (warn): do not block; the background Tier 2 review toasts findings.
    },

    // ── 2. Ambient channel: Tier 2 after edits (debounced), session summary on idle. ──
    event: async ({ event }) => {
      if (event.type === "file.edited") {
        const file = (event.properties as any).file as string
        if (!file) return
        const stage = stageOf(rel(file), cfg)
        if (!GATED_STAGES.has(stage)) return
        const last = lastReview.get(file) ?? 0
        if (Date.now() - last < DEBOUNCE_MS) return
        lastReview.set(file, Date.now())
        $`python3 ${[cliPath(cfg), "--llm", "--file", resolve(file)]}`.quiet().nothrow().then((proc: any) => {
          const out = proc.text().trim()
          if (proc.exitCode !== 0 && out) {
            client.tui.showToast({ message: `⚖ ${out.slice(0, 400)}`, variant: "warning" })
          }
        })
      }
      if (event.type === "session.idle") {
        const sid = (event.properties as any).sessionID as string
        if (!sid) return
        const proc = await $`python3 ${[cliPath(cfg), "--report", "--session", sid]}`.quiet().nothrow()
        const out = proc.text().trim()
        if (out && !out.startsWith("No ")) {
          client.tui.showToast({ message: `⚖ ${out.slice(0, 400)}`, variant: "info" })
        }
      }
    },

    // ── 3. On-demand deep review: agent-invocable via natural language / AGENTS.md. ──
    tool: {
      compliance_review: tool({
        description:
          "Full EU AI Act compliance review of a file (Tier 1 patterns + KB excerpts). " +
          "Returns a verdict with article citations. Use before committing PRDs or product AI-surface code.",
        args: { path: tool.schema.string().describe("File to review") },
        async execute(args) {
          const proc = await $`python3 ${[cliPath(cfg), "--llm", "--file", resolve(args.path)]}`
            .quiet().nothrow()
          return proc.text() || `compliance-check exit ${proc.exitCode}`
        },
      }),
    },
  }
}
