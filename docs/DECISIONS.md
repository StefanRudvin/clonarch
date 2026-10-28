# Decision log

Status: **Required/Confirmed** = owner instruction/answer; **Proposed** = recommendation, not approval; **Verified docs** = official public behavior, not a tested account integration; **Unresolved** = do not assume.

## Current decisions — updated 2026-10-27

| ID | Status | Decision / rationale |
|---|---|---|
| D01 | Required | App Clonarch; Python backend, browser UI, project-local plans for future agents. |
| D02 | Required | Shared household cards, CSV/manual expenses, persistent rules and monthly focus. |
| D03 | Required | Normal vs exceptional spending separate; no initial password. |
| D04 | Confirmed | Deploy on current VM; owner permits web listener/port selection. Preserve no-public-ingress/router-forwarding constraint. Observed private IP 192.168.105.10; app listening on port 8787. |
| D05 | Confirmed | Owner's income via Chase checking transactions, roughly 15th/month-end; spouse no income. Checking additional to four credit accounts. |
| D06 | Proposed | Modular monolith FastAPI/Pydantic v2/SQLAlchemy 2/Alembic/SQLite WAL, React/TypeScript/Vite. Python 3.12 project-local runtime installed with owner approval. |
| D07 | Proposed | Backend serves built frontend on same origin; one worker/durable jobs. No Redis, Celery, Docker, public webhook or reverse proxy required for MVP. |
| D08 | Confirmed | USD, purchase-date calendar months, Eastern timezone. Use authorization date when available and visibly marked posted-date fallback otherwise; income uses deposit posting date. Proposed America/New_York including DST. |
| D09 | Confirmed | Default regular until changed by owner; category and spend type independent. Unreviewed/default provenance remains visible. |
| D10 | Proposed | Negative minor units = outflow; positive = inflow/refund. Transfers/card payments excluded from expenditure and income, including both checking/card sides. |
| D11 | Proposed | Deterministic ordered per-field rules with previews; manual locks first, rules before accepted AI suggestions. |
| D12 | Confirmed / proposed details | Annual bills can be averaged over a chosen timeframe. Implement separate normalized month allocations without altering actual ledger; calendar-month periods/cent rounding in architecture/API. Splits/FX/net-worth/full accrual remain deferred. |
| D13 | Confirmed | Plaid Trial plan intended, authorization to be supplied later. One-year target; request 365 days on initial Link. CSV/manual remains available, not dependent on live Plaid success. |
| D14 | Verified docs / proposed | Trial allows 10 lifetime Production Items, deletion doesn't recover slots. Use Sandbox for development; persist tokens, reuse login Items and update mode. Outbound sync polling with update status; no public webhook. |
| D15 | Confirmed / gated | Classification piece named JEX; remote allowed; prefer owner's Codex subscription. Official Codex CLI installed locally; owner accepts resetting subscription limits if JEX reaches them. Still requires dedicated owner login and isolation validation. No general API entitlement or existing-agent-token reuse assumed; suggestions only proposed. |
| D16 | Proposed | Expected paydays are planning overlays, never actual income/bank balance. |
| D17 | Confirmed / unresolved details | Latest four distinct cards: two Chase + two Amex, replacing original inventory. Ownership/login grouping picked during Link; actual Trial/Safari/account availability still needs testing. |
| D18 | Unresolved | Secure credential setup, CLI isolation/limits, exact CSV headers, annual allocation default periods, backups and unverified network routing. |
| D19 | Verified docs / proposed | Standard desktop/mobile web OAuth supports popup flow without redirect_uri. Try standalone Safari first; supplied production redirect URI must be HTTPS. No public callback workaround. |

## Revision notes

2026-10-27 owner follow-up supersedes these initial assumptions: target VM unknown → current VM; three Chase/one Amex → latest two Chase/two Amex; posted-date default → purchase date with explicit fallback; manual-only income → owner's Chase checking; amortization deferred → limited explicit expense spreading in v1; JEV undefined → JEX module using remote/Codex preference. Full account grouping and bank availability are not inferred from the word “account.”

Public integration documentation was researched on 2026-10-27; citations and limitations are in [INTEGRATIONS.md](INTEGRATIONS.md). Project-local installation and local server startup have occurred with owner approval. No credentials/login, actual connections, inference, router/firewall/boot configuration changes have occurred. Approval scope does not extend to network or startup changes.

Change process: update affected architecture/data/API/plan/operations files with each material change, and preserve which choices are owner requirements versus implementation recommendations.
