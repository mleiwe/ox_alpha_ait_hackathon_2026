---
description: Disarm the compliance middleware (no interception until armed again)
---
Read `compliance/config.json` and set `"armed": false` (edit the file, keep
everything else unchanged). Confirm to the user that the middleware is
disarmed: no writes will be intercepted, and the ledger keeps its history.
The `compliance_review` and `compliance_override` tools stay available on
demand.
