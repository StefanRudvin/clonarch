# Clonarch

A private, LAN-only household spending app, inspired by Monarch.

**Status: first local-only MVP is running at [http://192.168.105.10:8787](http://192.168.105.10:8787).** See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for features and limitations. No public exposure, router/firewall/startup changes or bank connections are configured.

## Start here

1. Read [AGENTS.md](AGENTS.md) (agent constraints) and [docs/PLAN.md](docs/PLAN.md) (implementation sequence).
2. Read confirmed owner answers and remaining gates in [docs/QUESTIONS.md](docs/QUESTIONS.md); implementation details remain proposals until agreed.
3. Use [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DATA_MODEL.md](docs/DATA_MODEL.md), and [docs/API.md](docs/API.md) as the coordinated design contract.
4. Read [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) for researched Plaid responses/Trial limits and Codex/JEX feasibility; see [implementation status](docs/IMPLEMENTATION_STATUS.md).
5. Follow [docs/OPERATIONS.md](docs/OPERATIONS.md) for LAN boundaries/backups. Keep [docs/DECISIONS.md](docs/DECISIONS.md) and [docs/HANDOFF.md](docs/HANDOFF.md) current.

`CLAUDE.md` points Claude-based agents to the same instructions. All project planning and handoff files live here.

## Product goal

Answer: **“How much does our household normally spend each month, separately from holidays, major maintenance, and other exceptional spending?”**

Core workflow: connect cards or import transactions → review the monthly transaction list → correct category/spend type → optionally save a persistent rule → see updated monthly totals.

Scope:
- Latest owner inventory: four distinct cards, two Chase and two Amex; map ownership/logins during Link. Connect owner's Chase checking for actual paycheck deposits; spouse has no income.
- Plaid Trial intended; official docs confirm 10 lifetime Production Items. Request 365 days initially. Actual dashboard entitlement, bank history and Safari Link remain to test; see [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md).
- CSV imports and manual expenses, independent of live connectivity. USD-only purchase-date reporting, Eastern time (`America/New_York` proposed).
- Monthly regular versus exceptional spending; independent merchant categories and recurring-payment hints.
- Persistent, previewable categorization rules. Optional remote JEX classification using the owner's Codex subscription through a separately authenticated official CLI adapter, gated on installation/isolation/usage verification.
- Annual bills can be spread over chosen calendar-month periods in a normalized view, without changing actual transaction amounts/dates or double-counting.
- Two usual paydays: around the 15th and month-end. Actual recorded income and expected income must remain distinct.
- No login initially. Owner confirmed this VM; app currently binds `192.168.105.10:8787`. No public ingress, tunnels, router forwarding or UPnP.

## Implemented stack

Project-local Python 3.12.16 + FastAPI/Pydantic + SQLAlchemy + SQLite, with a React/TypeScript/Vite bundle served by the same backend origin. Project-local uv, npm dependencies and Codex CLI are under this directory; system Python/Node and shell startup were not changed.

Plaid and Codex are **not logged in or connected**. The current UI supports manual records, basic rules, CSV preview/commit, and explicit actual-vs-smoothed monthly spending. See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md), [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md), and [docs/HANDOFF.md](docs/HANDOFF.md).
