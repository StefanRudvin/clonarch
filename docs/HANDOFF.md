# Handoff — updated 2026-10-27

## Dark mode session — 2026-10-27

- Added header **Theme** selector (System/Light/Dark), defaulting to device appearance and persisting explicit selection in browser localStorage. System tracks device changes; blocked storage is tolerated for the current page.
- Changed `frontend/src/main.tsx`, `frontend/index.html`; added `frontend/src/theme.ts`, `frontend/src/theme.css`, `frontend/src/theme.test.ts`, and `frontend/public/theme-init.js`. Updated `docs/IMPLEMENTATION_STATUS.md` and this handoff. External blocking initialization script resolves appearance before paint and respects existing `script-src 'self'` CSP.
- Verified: `npm test --prefix frontend` **10 tests pass** (preference storage, system/explicit resolution, blocked storage, theme metadata). `npm run build --prefix frontend` passes. Live GET `/` and `/theme-init.js` succeed, and GET headers retain existing CSP. HEAD `/` returns 405 (existing GET-only SPA route); use GET for smoke checks.
- Rebuilt production assets served by the existing process; no restart, dependency installation, backend/data/API changes, or listener/configuration changes. User authorized dark-mode implementation only.
- Not verified: actual browser/iPad visual appearance, native control rendering, or end-to-end theme selector interaction. Next: refresh on iPad and check all three themes, forms and the spread-bill dialog. Earlier integration next steps remain unchanged.

## Dark palette follow-up — 2026-10-27

- Owner requested grey rather than green dark mode. Reworked `frontend/src/theme.css` to neutral charcoal backgrounds, grey borders/text and neutral active controls/buttons. Amber warnings and red errors remain distinct; positive transaction amounts retain a muted green hint. Light mode is unchanged.
- Updated dark browser theme color to `#18181b` in `frontend/src/theme.ts`, `frontend/public/theme-init.js`, and `frontend/src/theme.test.ts`.
- Verified: `npm test --prefix frontend` (10 pass) and `npm run build --prefix frontend` pass; production bundle rebuilt. Browser/iPad visual review still pending. No dependencies, backend/data, listener or startup changes. Next: refresh the UI and confirm the neutral palette with the owner.

## Running application

A first Clonarch 0.1 MVP is implemented and currently running on the confirmed VM at **http://192.168.105.10:8787**. The explicit listener is `192.168.105.10:8787`, not a wildcard. No boot service, firewall/router rule, public ingress, tunnel, DNS, or other VM changes were made. Ordinary background process; VM reboot will stop it. Start/stop scripts are in `scripts/`.

Read `docs/IMPLEMENTATION_STATUS.md` before claiming features. This is an early MVP, not the full API/architecture design: no Plaid connection, JEX calls, account sync, historical-source reconciliation or owner CSV mapping. No live financial rows were imported. UI starts blank with generic account labels.

## Owner requirements

- Current VM; private IP 192.168.105.10, selected port 8787.
- USD, Eastern (`America/New_York` proposed), purchase-date spending.
- Latest inventory two Chase + two Amex credit cards; ownership/login grouping remains TBD. Additional owner Chase checking for real paychecks; spouse has no income.
- Plaid Trial planned, owner will authorize later. Request one year initial history; preserve lifetime Item limit.
- Spending defaults regular; owner marks exceptional. Explicit annual-bill spreading over selected period in separate normalized report; actual purchase/income remains actual.
- Remote JEX permitted, preference Codex subscription. Use official Codex CLI only; installed but not logged in. No agent OAuth-token reuse and no JEX data calls without a safe isolated adapter.
- CSV headers to be provided later.

## Installed scope (approved)

Owner approved `docs/INSTALLATION_PROPOSAL.md` 2026-10-27. Project local:
- `.tools/bin/uv`, `.tools/python` CPython 3.12.16.
- `backend/.venv` FastAPI, Pydantic, SQLAlchemy, Alembic, RE2, cryptography, multipart, pytest/httpx.
- `frontend/node_modules` React, Vite, TypeScript, test/types packages.
- `.tools/codex` official Codex CLI 0.165.0.

No system/global packages, Python upgrade, shell startup, Codex login/auth, Plaid credentials, firewall/router/boot changes. Lockfiles are `backend/uv.lock`, `frontend/package-lock.json`. Runtime/credentials/dependencies/build assets are gitignored.

## Features that work now

- React production UI and FastAPI/SQLite same-origin.
- Seeded generic household labels for four card accounts plus owner's checking; account label/ownership editor not yet implemented.
- Manual transaction add, list, category/type edit; transfer excluded from report; actual income tracked.
- Basic persistent RE2 rules; new/manual/imported records use rules, optional historical apply action.
- CSV preview then explicit commit, strict signed Clonarch amount convention and generic ISO-date/amount/description headers. Overlapping statement periods are **not** deduplicated; do not claim bank-format production importer.
- Explicit month allocation for posted expenses/refunds, actual versus smoothed totals and exact-cent distribution.
- No login; same-origin CSRF + Origin check + Host allowlist. Runtime `var/` is mode 0700 and server uses explicit LAN IPv4.

Known implementation caveats: see IMPLEMENTATION_STATUS.md. Target API/architecture are ahead of shipped code. Avoid importing real bank CSVs until the CSV headers, signs, posted/purchase dates and mapping are verified. It is not yet a Plaid-quality financial source-of-truth.

## Verification actually run

- `npm run build --prefix /home/rudi/clonarch/frontend` passes (Vite production output).
- `cd /home/rudi/clonarch/backend && ../.tools/bin/uv run --python ../.tools/python/cpython-3.12.16-linux-x86_64-gnu/bin/python3.12 pytest -q`: **3 tests pass** covering cent allocation, manual expense/income+annual smoothing+CSRF, and CSV preview/commit/replay.
- VM smoke: app GET `/` serves Clonarch index and built assets; health ready, accounts and monthly report endpoints succeed.
- `ss` verified `192.168.105.10:8787` listener only for this app. Does not verify router, host firewall or remote/VLAN reachability.
- SQLite DB, WAL, SHM, logs mode 0600; data directory 0700. No backup configured.
- Codex CLI version command only; no authentication/subprocess inference.
- No Plaid calls, credentials, OAuth or user data.

## Integration research

Official public Plaid/ OpenAI documents checked 2026-10-27; URLs/findings recorded in `docs/INTEGRATIONS.md`. Plaid Trial docs: 10 lifetime Production Items, Transactions available; initial history supports requested 365 days (institution-dependent); positive amounts are outflow; purchase authorization date can be earlier than posted date; standard mobile/desktop web can use OAuth popup without supplied redirect URI; supplied production redirect must be HTTPS. Actual entitlement and standalone iPad Safari flow remain untested.

## Next steps

1. Verify user can load the UI by IP on iPad; let them explore manual entry, monthly actual/smoothed, category/type edits, regex rules and a **synthetic/test** CSV.
2. Keep process running unless user asks to stop. Ops scripts: `scripts/start.sh`, `scripts/stop.sh`. Port/log/db paths in IMPLEMENTATION_STATUS.md.
3. Add real integration incrementally: implement schema migrations, exact-date/source semantics, account editor/CSV mapping and more tests before real account data.
4. Plaid: owner supplies credentials via a secure local configuration path (never chat), sandbox first, initial 365d, Transactions only, item-wide cursor. Do not delete/recreate trial Items; don't use `/transactions/refresh` by default.
5. JEX: Codex CLI requires owner-managed login. Before transmitting descriptions, verify installed CLI's tool-free capability and OS-enforced isolation so it cannot read household DB/Plaid secrets or run tools. No credentials or more software install without explicit approval.
6. Check actual LAN reachability/exposure from owner's client; never bind wildcard/add firewall or router changes without separate scope.

## Exact current endpoints

Implemented: GET `/api/v1/context`, `/health/ready`, `/accounts`, `/categories`, `/transactions`, `/reports/monthly`, `/rules`; POST `/accounts`, `/transactions`, `/rules`, `/rules/apply`, `/imports/csv`, `/imports/{id}/commit`; PATCH `/transactions/{id}`; PUT/DELETE `/transactions/{id}/allocation`; SPA static routes. The rest of API.md is target design, not guaranteed implemented.
