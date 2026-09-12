# Plan — 2-minute submission video

One HTML animation (same pattern as `eu-ai-act-presentation/promo/shoes-deepfake.html`:
fixed stage, `data-scene` timeline, `?record` mode) recorded to MP4 with Playwright + ffmpeg.
Captions carry the story so it works silent; VO optional after picture lock.

**Branch:** `ml_video` (from `main` @ e6de54c — all PRs merged).

## Pipeline (reuse, don't rebuild)
- Copy `promo/record_promo.py` pattern into this repo → `promo/record_video.py`.
- Deps: `pip install playwright imageio-ffmpeg` + `playwright install chromium` (not currently
  installed anywhere on this machine — needs a fresh install).
- Format: **1920×1080 landscape** (hackathon submission; the 4:5 promo was LinkedIn-specific).
- Playwright also drives the demos: it can screen-record the agent CLI, and drive the vis-network
  camera for the graph scene.

## Beats → scenes (120s)

| # | Time | Beat | Visual |
|---|------|------|--------|
| 1 | 0:00–0:15 | Great plan — but does it fit your market's regs? | Mock PRD on screen, red compliance flags appearing inline on clauses |
| 2 | 0:15–0:35 | Build compliance in from the start, not retrofit. **But most of us aren't lawyers.** | Split screen: two build timelines (compliant-from-day-1 vs bolt-on-later + rework); punchline lands on the skills gap |
| 3 | 0:35–0:50 | So: agents where you already work | **Real** `compliance/` demo — OpenCode plugin gate/toast or CLI run on a PRD snippet; quick cut to browser/Docs mock |
| 4 | 0:50–1:10 | We built a KB of the EU AI Act — biggest, most comprehensive act | **Real** `viz/graph-interactive.html` camera moves (see above); overlay: 308 files → 2,347 nodes / 6,135 edges |
| 5 | 1:10–1:25 | How should an agent traverse it? | Strategy ladder animates rung by rung: substring → BM25 → dense → GraphRAG → agentic |
| 6 | 1:25–1:45 | Benchmark says **GraphRAG** | Animated bar chart of MRR@5 (BM25 0.456 / GraphRAG 0.418 / TF-IDF 0.344 / substring 0.000) + the tiebreak story: chain recall **0.60 vs 0.20** — 3× the multi-hop chains delivered at 9ms latency |
| 7 | 1:45–2:00 | Agent powered by **GraphRAG on NetworkX** — live | Real demo clip: PRD snippet → flags with hop-by-hop citations (Art 6(2) → Annex III → Art 113). End card + repo link |

## Resolved TBDs (from merged `bench/REPORT.md`)
- Beat 6 winner: **GraphRAG (strategy 4)** — BM25 seeds + typed-edge expansion. BM25 led overall
  MRR (0.456 vs 0.418, Δ0.038 < 0.05) → composition tiebreak: GraphRAG wins hop coverage
  (0.300 vs 0.233) AND multi-hop outright (chain recall 0.60 vs 0.20).
- Beat 7 stack: **GraphRAG on NetworkX** (llmwiki preserves rankings but −0.2 MRR).
- Latency flex: 9ms mean / 17ms p95 — 50× under the 1s IDE budget.

## What we demo (real, not mocked, wherever possible)
1. **The agent** — `compliance/compliance-check` CLI + OpenCode plugin (merged on main,
   `compliance/DEMO.md`). Most screen time (scenes 3 + 7) — it's the core-requirement criterion.
2. **The graph** — `graph-interactive.html` camera moves (scene 4).
3. **The benchmark** — `bench/REPORT.md` numbers as an animated chart (scene 6); `viz/bench-*.png`
   as fallback/cameo.
4. **Visible thinking** — hop-by-hop citation trace (scene 7) = the reasoning tier made visible.

## Open decisions
- VO vs silent — captions work either way; VO adds ~1 day, decide after picture lock.
- Music: silent or licensed track.
- Branding on end card (repo URL / team names).

## Build order
1. Install deps (`playwright`, `imageio-ffmpeg`, chromium), copy recording pipeline, smoke-test
   with a 5s stub.
2. Animation skeleton: stage + scene timeline + caption system (1920×1080).
3. Scenes 1–2 (story only, no data deps).
4. Record demo clips via Playwright: agent CLI run (scene 3/7), graph camera moves (scene 4 —
   pre-stabilize, then drive `network.focus()`).
5. Scenes 5–6 (ladder + benchmark chart — numbers are final).
6. Scene 7 end card → picture lock → optional VO → export MP4.
