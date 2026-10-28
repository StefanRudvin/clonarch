# Clonarch agent instructions

## Context and boundaries

- This directory is the project root. A first MVP is implemented and running; read docs/IMPLEMENTATION_STATUS.md for feature parity/gaps and do not mistake target-contract documentation for finished endpoints.
- Read README.md, docs/QUESTIONS.md, docs/DECISIONS.md, docs/PLAN.md, and docs/HANDOFF.md before implementation. Read relevant design contracts before changing them.
- Do not mistake proposed defaults for confirmed requirements. Record owner answers and explicit design changes.
- Keep all project plans, including Claude-related plans and handoff notes, inside this directory. Do not depend on an external conversation for project context.
- The owner uses an iPad over SSH and wants a LAN-only web UI.

## Approval and deployment

- Ask for separate, explicit confirmation before installing/upgrading any software, dependencies, plugins, or tools. State what, where, and whether configuration/startup changes. A request to implement or set up is not installation approval.
- Owner confirmed current VM, local app startup/port and explicitly approved the listed project-local dependency installation. Current listener 192.168.105.10:8787. No public ingress. Boot services, firewall/router edits or other VMs are not authorized.
- Never enable public ingress, tunnels, router forwarding, UPnP, publicly exposed webhooks, or public DNS exposure to satisfy an integration.
- Do not silently bind to `0.0.0.0`, open firewall ports, enable a boot service, or start dev servers accessible on the LAN.
- No live Plaid calls, paid services, LLM data transmission, credential collection, or imported real statements without explicit authorization and an agreed secret-handling path.
- The 2026-10-27 approval applies only to docs/INSTALLATION_PROPOSAL.md: uv + managed Python under `.tools`, listed app/test packages in backend `.venv` and frontend `node_modules`, and official Codex CLI under `.tools/codex`. No shell startup/system package changes. Ask again for additional tools/dependencies.

## Engineering invariants

- Monetary values are integer minor units plus currency; never binary floating point.
- Category, spend type (`regular` / `exceptional`), transaction kind, and recurring hints are separate concepts. USD, purchase dates with explicit fallback, Eastern time; annual allocations are a separate normalized report, never duplicate ledger transactions.
- Income, credit-card payments, and transfers must never inflate expenses. Pending/removed transactions do not enter settled monthly totals.
- Deterministic manual edits beat rules; rules beat optional model suggestions. Source refreshes cannot overwrite user decisions.
- Target design preserves source data separately and makes bulk changes auditable/previewable. Current 0.1 implementation does not yet meet that full target; do not use it to imply Plaid-grade source reconciliation or bank CSV deduplication.
- Do not merge similar purchases across accounts automatically. Imports must be idempotent and review ambiguous duplicates.
- Tokens and provider keys stay server-side, encrypted at rest; never return them to frontend APIs or logs. Trial Items are lifetime-limited (10 per current docs); do not consume Production slots during tests. For JEX use an explicitly authorized official Codex integration, never extract this agent's subscription tokens; CLI auth caches stay private outside git.
- Same-origin frontend/backend, strict Host/Origin validation, CSRF protection, and no permissive CORS even without login.
- Every implemented backend route must be documented in docs/API.md; docs/IMPLEMENTATION_STATUS.md distinguishes shipped from target-contract routes. Keep contract and tests aligned.
- Use synthetic fixtures in source control; never commit tokens, real transactions, database files, statements, or backups.

## Handoff

After every substantial session, update docs/HANDOFF.md with changed files, verified tests, unresolved issues, next step, and approvals (including scope). Never claim verification that was not performed.
