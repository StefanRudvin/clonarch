# Running implementation status — 0.1.0

Updated 2026-10-27. Running in-process on the current VM at `http://192.168.105.10:8787`. Only app listener is the specifically bound private IPv4 address/port; no router, firewall, DNS, tunnel, service manager, shell startup or boot changes made. Server is an ordinary background process; restarting the VM stops it.

## Usable now

- Responsive React single-page UI with actual/smoothed toggle, month picker and USD totals.
- Header theme selector: System (default), Light, or Dark. Preference is saved in this browser; System follows device appearance changes. Same-origin pre-paint script avoids a light flash without weakening CSP. Dark styling covers forms, transactions, notices and allocation dialog.
- FastAPI same-origin JSON endpoints on SQLite; basic CSRF token + exact Origin/Host validation; SQLite data in project-local private `var/` directory.
- Synthetic account placeholders (four card labels with generic household ownership plus Chase Checking/Owner). They are **not linked bank accounts**; account editor is not implemented.
- Manual transaction input (expense/income/refund/transfer), user can change categories and regular/exceptional classification in list.
- Persistent RE2 categorization rules, applied to future manual/import entries; “Apply rules” re-evaluates history. No bulk preview yet.
- Explicit expense/refund month spreading with exact-cent arithmetic; actual vs smoothed totals separate.
- CSV initial preview and explicit commit. CSV must have recognized ISO-style date, signed amount and description headers; negative outflow, positive inflow/refund. Checking positive rows are inferred as income only when payroll-like description is present; other checking inflows and card-payment-like descriptions are transfers; other card positive rows are refunds. Review before commit; overlapping-file periods are **not deduplicated**, and bank-specific debit/credit CSV mapping waits for provided headers.
- React production bundle is served by FastAPI on same origin; no third-party font CDN.

## Not implemented/enabled yet

- Plaid Link/exchange and manual per-connection `/transactions/sync` endpoints are implemented but **not configured or used** yet. Credentials must be entered locally; actual Chase/Amex/checking links, periodic scheduler, pending UI reconciliation, durable sync jobs, Trial quota accounting, bank-history coverage and real 365-day fill remain incomplete.
- JEX/Codex classification adapter, Codex login, classification subprocess or external transaction-data transmission.
- Owner-specific Chase/Amex CSV mapping; generic import is not a full duplicate-safe production importer. Plaid API calls should first be tested with one login and reconciled against a statement.
- Actual date fallback semantics are incomplete: UI labels posted fallback but backend currently accepts one effective date. Income classification in manual UI selects `purchase_date` plus `posted_date`; report uses posted date.
- Historical transactions are currently returned/filtered by purchase date. Monthly report logic covers expenses/refunds and actual vs normalized basics, but needs further integration/edge-case tests. No coverage-completeness model.
- Expected pay schedule, trend/averages, account management/editor, named exceptional events, refunds matching and audit/change history.
- The extensive docs/API.md is the **target contract**; many listed routes/contracts do not yet exist in 0.1. Do not treat documentation breadth as implementation parity.
- No login: any device that can reach the local listener can view/change the data. Do not expose beyond the trusted LAN.

## Verification performed

- `uv sync` installed backend/test dependencies into `backend/.venv`; Node deps in `frontend/node_modules`; Python 3.12.16 at `.tools/python`; uv and Codex CLI at `.tools` (see INSTALLATION_PROPOSAL.md).
- `npm run build --prefix frontend`: passes.
- `cd backend && ../.tools/bin/uv run --python ../.tools/python/cpython-3.12.16-linux-x86_64-gnu/bin/python3.12 pytest -q`: 5 tests pass, including mocked Plaid sync and the disabled-without-credentials guard. Frontend Vitest: 10 tests pass; production build succeeds.
- Production app GET `/`, `/api/v1/health/ready`, `/api/v1/accounts`, `/api/v1/reports/monthly` verified from the VM.
- Listener verified as `192.168.105.10:8787`, not wildcard. Host router/firewall/WAN/VLAN exposure cannot be verified from this inspection.
- Runtime DB directory mode 0700, database/WAL/SHM/log mode 0600; server process runs under the current user.
- No real financial records/provider credentials were used. Live app database contains only five generic account placeholders and zero transactions. Plaid local setup script has not been run.

## Operations

```sh
/home/rudi/clonarch/scripts/start.sh
/home/rudi/clonarch/scripts/stop.sh
```

These do not install software or configure startup at boot. Check actual status with:

```sh
ss -ltn | grep 192.168.105.10:8787
curl -fsS http://192.168.105.10:8787/api/v1/health/ready
```

Data file: `/home/rudi/clonarch/var/clonarch.sqlite3`. Do not copy while running; no backups have been configured. The app currently has no DB migration framework wired in despite Alembic being installed.
