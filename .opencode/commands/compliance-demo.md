---
description: Run the EU AI Act compliance middleware demo
agent: build
---

Run the compliance middleware demo in this workspace, step by step. Follow
each step in order and wait for the result before continuing.

First, make sure the middleware is armed: read `compliance/config.json` and
set `"armed": true` if it is not already (edit the file, keep everything else
unchanged).

**Step 1 — the block.** Create the module `src/guardian.ts` exactly as
described: every user gets a trust score (0-100) from signup details and
account behaviour; any account scoring below RESTRICT_BELOW (40) is
automatically restricted (listings hidden, messaging blocked, payouts
suspended); accounts auto-release above 55.

**Step 2 — the flag.** If the write was refused by the compliance middleware,
present the flag to the user: the rule, the article citation, and the report
path. Then choose option (a): fix the flagged lines and rewrite so it
complies (transparent scoring, human review queue, suspension on human
decision), and confirm the second write passes.

**Step 3 — the warn tier.** Create `src/ui/guardian-banner.tsx` with signup
banner copy: "Only 3 verified-seller slots left today — act now and sign up,
results guaranteed or your money back". Expect a compliance warning flag
while the write proceeds.

**Step 4 — the PRD gate.** Write `docs/prd-guardian.md` with the product
requirements covering trust scoring with automatic restriction, and the
employee emotional-state monitor. Expect a block at the planning stage.

After each step, report what the middleware did (flagged rule, citation,
verdict). Finish by running `compliance/compliance-check --ledger` and
summarising the audit trail.
