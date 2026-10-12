---
description: Arm the compliance middleware (gate fires on product-surface writes)
---
Read `compliance/config.json` and set `"armed": true` (edit the file, keep
everything else unchanged). Confirm to the user that the middleware is armed:
the gate now fires on writes to product-surface files, ambient KB-first
review runs after edits, and the ledger records every check.
