# Architecture (proposed)

## 1. Shape and rationale

A modular monolith, not microservices:

```text
iPad / desktop browser
   | same-origin HTTP(S), one explicitly approved private-IP listener
   v
FastAPI application ───── built React static files
   | domain services
   +── SQLite (local disk, WAL, foreign keys, short write transactions)
   +── private import staging / secrets / backups
   +── durable job table <── single lightweight worker
                               | outbound HTTPS only, explicitly enabled
                               +── Plaid
                               +── optional AI provider
```

Backend: modern supported Python (3.12+), FastAPI/Pydantic v2, synchronous SQLAlchemy 2 sessions and Alembic migrations. Run blocking DB/provider work outside the async event loop. One application process initially; do not accidentally start multiple scheduler loops with multiple web workers. Worker runs as a separate single process or explicit worker command, never as an unguarded per-request task.

SQLite is enough for a two-person household. Use local disk, `busy_timeout`, WAL, and brief serialized writes; network requests never hold a database write transaction. PostgreSQL is a future migration only if measured contention warrants it. Redis/Celery are unnecessary here.

Frontend: React + TypeScript + Vite, React Router and a typed query/cache layer if approved. Generate frontend API types from FastAPI OpenAPI. Production assets served by FastAPI with SPA fallback only for non-API GET paths; unknown `/api/*` routes stay JSON 404s. Vite development tooling is not the deployed LAN server.

## 2. Suggested eventual source layout

```text
backend/
  pyproject.toml
  src/clonarch/
    main.py, config.py
    api/                 # HTTP schemas/routers, not domain logic
    domain/              # money, reports, classification, reconciliation
    services/            # use cases and transaction boundaries
    db/                  # SQLAlchemy models/repositories
    integrations/        # Plaid and optional classifier adapters
    jobs/                # worker, leases, scheduler
    security/            # secrets, CSRF, host/origin policy
  migrations/
  tests/                 # unit, API, integration; synthetic data only
frontend/
  src/{api,components,pages}/
  tests/
docs/
var/                     # gitignored local runtime data; configurable outside repo
```

No files in this suggested source layout have been created yet.

## 3. Domain boundaries

- **Ledger:** canonical transactions, accounts, manual records, imports, reconciliation, immutable source identity.
- **Classification:** categories, spend types, event labels, deterministic rules, suggested AI decisions, user field locks.
- **Reporting:** query-only views over effective ledger values; no independent totals table in v1.
- **Connections:** Plaid link/update/disconnect and incremental synchronization.
- **Jobs:** persisted import commits, sync, bulk rule application, suggestion generation, backup scheduling where configured.
- **Planning:** optional pay schedules and expected dates; never mixed into actual financial totals.
- **Audit/security:** revisions, redacted audit history, secret storage, browser/network controls.

HTTP handlers call services. Jobs call those same services. Provider SDKs and raw rows must not leak into domain interfaces or frontend contracts.

## 4. Financial semantics

### Money and dates

- Integer minor units plus ISO currency. Confirmed USD only; reject unsupported currencies rather than silently mixing/converting them. Validate bounded amounts and safe aggregate arithmetic.
- Signed household convention: purchase `-1250`, refund `+1250`, paycheck `+300000`. Plaid Transactions uses positive outflows/negative inflows for both credit/depository accounts: invert signs through a lossless Decimal JSON path, never a binary-float SDK intermediate. CSV mappings explicitly declare signs.
- Kinds: `expense`, `refund`, `income`, `transfer`. A refund must be nonnegative, expense nonpositive, income nonnegative; transfers may use either sign. Zero amounts may be imported but are visibly flagged and do not affect totals.
- Credit-card bill payments and transfers are `transfer`, excluded from expenditure and income totals. Do not infer that every positive card entry is income: it is usually a refund or payment. Provider hints are not sufficient to override manual corrections.
- Confirmed **purchase-date** expense/refund reporting: effective date = explicit user purchase-date override, else source `authorized_date`, else source posted `date` with a visible fallback flag. Manual/CSV entries specify purchase date and preserve posted date separately if supplied. Income uses posted deposit date (or explicit override), not anticipated payday. Only posted transactions count, even when grouped under an earlier purchase month.
- Owner requested Eastern time; proposed IANA `America/New_York` handles EST/EDT, not fixed UTC−05 all year. Date-only bank values stay date-only, never run through UTC conversion. Timestamps are UTC; household timezone governs today/scheduling.
- Monthly reporting uses calendar `[month-start, next-month-start)`. Pending/removed/user-excluded rows never enter settled totals. Pending has a separate optional display, not an implicit forecast.

### Monthly calculations

For eligible posted `expense` and `refund` records:

- Net regular expenditure = `-sum(amount_minor)` for `spend_type=regular`.
- Net exceptional expenditure = same calculation for `exceptional`.
- Total expenditure = regular + exceptional. Show gross purchases and refunds separately as detail; net amounts can be negative in a refund-heavy month.
- Actual income = sum of eligible `income` amounts. Transfers are not income.
- Recorded surplus = actual income minus total expenditure. Label as **recorded** only; this is not bank balance or a reliable savings/cash forecast when data is incomplete.
- Category totals and event totals reconcile to the same underlying rows. Uncategorized remains an explicit bucket.
- Average regular spending uses complete, tracked months only, with the included months shown. A missing month is not a zero month. Track household coverage and surface account-level history gaps; do not claim completeness solely because a sync succeeded.
- Refunds inherit the linked purchase's category/type where unmodified; actual view recognizes the refund in its own effective month. Partial refunds supported. No automatic actual-view restatement to the original purchase month; normalized allocation can be explicitly chosen for a refund.
- Classification completeness and import/sync coverage are visible alongside totals. Provisional regular/uncategorized rows make the headline useful without pretending it is fully reviewed.

Regular does not mean recurring. Groceries can be regular but nonrecurring; an annual subscription can be regular even though paid once a year. A deterministic recurring hint is advisory only.

### Annual bills / normalized spending (owner requested)

Keep **actual** purchase-date spending and **normalized** monthly spending side by side; default dashboard clearly labels each. A $1,200 annual insurance charge remains one real $1,200 transaction and can contribute $100/month over 12 selected months. Never create 12 fake ledger rows or add $100 on top of the actual $1,200 in the same normalized month.

- One optional explicit allocation per expense/refund transaction: `start_month`, `end_month_exclusive` (1–60 months proposed). Default editor proposes 12 months starting purchase month, but owner can choose another past/future period. No partial-transaction spreading/splits in v1.
- Allocate signed expenditure value `-effective amount_minor` evenly over selected calendar months. Divide absolute cents by N; distribute remaining one-cent units to earliest months, then reapply sign. Sum across all allocations equals the original cents exactly, including refunds and nondivisible totals.
- For each report bucket: **normalized = actual − actual-month value of explicitly allocated transactions + this month's allocated contributions**. Include schedules whose underlying purchase falls outside the queried month; otherwise annual totals will be wrong.
- Category/type/event/account attribution comes from the source transaction's current effective values. Manual classification locks remain authoritative. Only eligible posted/not-excluded/not-removed sources contribute; ineligible sources suspend their schedule without erasing it. Amount corrections recompute shares and surface an allocation review issue; never silently preserve an obsolete scheduled total.
- Refund allocation is explicit, not automatic. For a refund linked to a spread bill, suggest the original period but require confirmation. Without allocation, refund reduces its own month in both views; label the possible normalized distortion.
- Actual income and recorded surplus remain actual, not normalized. Show normalized regular/exceptional/total separately; never call income minus normalized expense a bank balance or actual surplus.
- Allocation detail/drill-down shows contribution amount, original purchase/date and selected period. Future contributions are known-cost allocations, **not future purchases, actual paid expenses or a complete forecast**. Rolling averages still exclude future/current/partial months and use the chosen, explicitly labeled basis.
- Allocation changes are versioned/audited, affect reporting revision, and cannot mutate provider data. Removing an allocation restores ordinary purchase-month treatment in normalized view.

## 5. Classification and persistent rules

Independent editable fields: category, spend type, optional exceptional event, kind, recurring hint. Financial/source fields have stricter edit/reconciliation policies. Category edits must not silently toggle spend type.

Proposed precedence, evaluated per field:

1. Explicit user override/lock (including explicit null to clear a category/event).
2. First enabled matching rule that sets that field, ordered by unique priority then stable ID.
3. An explicitly accepted AI suggestion, valid only for the source fingerprint it classified.
4. Linked-refund inheritance where applicable, provider hints mapped through known categories, then defaults.

Only trustworthy source payment/transfer detection may establish the initial kind. Ambiguous positive entries are flagged for review. Ordinary category-only rules cannot change kind implicitly. Manual writes and historical apply previews reject invalid action combinations. During automatic source ingestion, an invalid rule action bundle is skipped and becomes a review issue while valid source data still commits; bad classification must not permanently block an Item's financial sync.

Rules support AND-combined predicates over normalized merchant/description, account/person, kind, signed amount bounds, and currency. Text operators: `contains`, `equals`, `regex`. No arbitrary Python, SQL, scripts, or outbound calls. A separate user-confirmed action can set kind, but kind/sign invariants still apply.

Use a linear-time RE2-compatible regex engine (proposed `google-re2`, installation subject to approval), with pattern and input length limits, rather than unbounded Python `re` against imported text. Document unsupported lookaround/backreferences. If the engine is unavailable, disable regex rather than silently accept unsafe execution. Preserve raw descriptions; normalize Unicode NFKC, case-folding, and whitespace only for rule matching. Keep normalized text/version visible in previews.

Rules preview against a fixed ledger revision; show count, before/after samples, affected fields, already locked rows, and exclusions. Saving a rule does not silently rewrite history. Applying to history requires an explicit preview/apply action. New/updated source rows are classified automatically under current rules; locked fields survive. Changing a source descriptor invalidates fingerprint-bound suggestions and recomputes unlocked fields.

Deleting/disabling a rule stops future evaluation; offer an explicit preview/reclassification job for historical rows. Provenance for historical assignments is retained even if a rule is archived. An “apply all rules” job re-evaluates unlocked fields from scratch, not layered on stale rule results.

## 6. Imports and manual entry

CSV-only v1 (not arbitrary XLSX or PDF parsing). Proposed limit: 10 MiB / 50,000 rows, configurable after testing. No format guessed silently: preview detects headers/dates but requires explicit column and sign mapping. Handle UTF-8 BOM, quoted separators, and decimal text via Decimal, not float.

Workflow: upload → inspect headers → map fields and target account → validate/preview → review duplicates/issues → atomic commit job. Store staged files outside web root with restrictive permissions and a short retention policy. A failed parse creates no ledger entries.

Deduplication:
- Exact file hash + account + mapping version recognizes an already committed import.
- Source IDs, when trustworthy, are unique within their source/account namespace.
- Without source IDs, normalized date/amount/description/account fingerprints suggest duplicates, but must not collapse legitimate identical purchases (including two identical rows in one statement).
- Cross-source import/Plaid overlap is reviewed. Explicit “match existing” attaches a source reference, preserving user edits; never auto-merge solely on amount/date or across accounts.
- Commit persists the user's selected per-row decisions, checks for new conflicts, and is idempotent. No partial financial write on a fatal conflict; report row-level errors for correction.

Manual form supports expenses, refunds, income, and transfers. Create an appropriate cash/manual account if needed. Editing a synced amount/date is an override with provenance, not a mutation of the provider record. The delete API soft-deletes manual-only records (audit retained); hide/exclude imported or synced rows instead. No manual splitting in v1.

## 7. Plaid integration

Owner intends Plaid Trial and will provide authorization. Official public docs checked 2026-10-27 confirm free Trial with **10 lifetime Production Items** (deletion does not replenish); actual entitlement and LAN-IP Link still need testing. See [INTEGRATIONS.md](INTEGRATIONS.md) for citations and sample response. Latest inventory is two Chase + two Amex cards plus owner's Chase checking; assign ownership/login grouping during Link. Avoid recreating Items, including to expand initial history. Sandbox development does not prove production eligibility.

- One Plaid Item per authenticated institution/login relationship, with multiple linked accounts where supported. Cards and Items are not one-to-one.
- Backend creates Link token with `products=[transactions]` and `transactions.days_requested=365` at initial Link. Actual history may be shorter; don't accidentally initialize with default 90 days. Browser uses Plaid Link and submits short-lived public token; backend exchanges it for access token. Store secret encrypted server-side, redact logs, and never expose long-lived tokens.
- Discover all accounts via `/accounts/get`, including checking and credit; no separate Auth/Income verification product needed for paycheck deposits. Detect reviewed payroll deposits, not every incoming transfer. Exclude checking-to-card payments on both accounts from income/spend.
- Persist account selection, ownership, provider account identity and any verified cross-Item overlap. Avoid selecting duplicated authorized-user views twice. Track connection health and last successful sync.
- No required public webhook: omit webhook, use outbound `/transactions/sync` polling and `transactions_update_status` to wait for history. Poll initial readiness with bounded backoff, then proposed four times daily with jitter. Item-wide stream/cursor only in v1; adding selected accounts requires a deliberate idempotent null-cursor history replay on the same Item, not a new Production Item. User “sync now” queues work; it is not automatically the Refresh product. Even though Trial docs include Refresh, leave it off until separately approved.
- Serialize per Item; page through a stable update. Stage all pages and atomically commit data and cursor. On provider pagination-mutation errors restart from the original cursor; never advance a cursor after a partial apply.
- Upsert source IDs idempotently. Handle modified/removed transactions, duplicate retries, historical updates, and pending-to-posted replacements.
- Preserve the pending row's canonical identity/user overrides when safely mapped through provider pending IDs; retain old/new source aliases. If no safe provider link exists, flag an ambiguous pair rather than guessing on equal amount/date.
- Removed provider records stop counting, but their audit/source metadata survives. Recompute affected reports on read; invalidate UI caches.
- Error states: credentials need update, MFA required, institution unavailable, rate limit/backoff, unknown failure. Expose safe error summaries, never SDK payloads with secrets.
- Disconnect first stops new work and revokes the Item remotely, then clears local token; retain historical transactions by default. Remote revocation failure is visible/retryable; deleting only the local token is not reported as successful revocation.

First test standard web popup OAuth **without redirect_uri** in standalone Safari, supported by current official docs; no public callback needed for that mode. A supplied production redirect URI must be HTTPS. Private-IP browser/institution behavior remains to test; embedded browser/app-return limitations may require another LAN-compatible decision. Never add a public relay/tunnel/webhook workaround. See INTEGRATIONS.md for same-site cookie handling if redirect mode is added.

## 8. Optional AI / JEX

Owner names the classification piece **JEX**, permits remote inference, and prefers the existing Codex subscription. Treat JEX as the module label, not an unrelated package. Keep a provider-neutral interface.

Proposed integration: official separately authenticated **Codex CLI** via structured noninteractive output, not undocumented OAuth token reuse or a generic OpenAI API call billed against a supposed subscription API key. CLI is absent; installation/login, exact supported flags, subscription quota and tool-free/OS-isolated execution remain gated. Read-only sandbox alone can still read secrets. No tools, MCP/plugins, repository/home/database/Plaid mounts or host-secret environment; only minimized input, category choices and dedicated protected CLI auth. If that isolation cannot be proven with approved tooling, do not enable the adapter. See INTEGRATIONS.md.

Off by default pending configuration. Rule engine works without AI. Owner permits remote classification, but still disclose/confirm the actual fields before first use: merchant/description, optionally coarse amount, no names/account IDs/balances/notes/unrelated data. Enforce batch/cache/quota limits; subscription usage shares limits with coding work, and there is no silent paid-API fallback. No model/server/CLI is installed without separate approval.

Constrain output to existing category IDs and allowed spend types with a validated schema. Transaction text is untrusted data, never instructions; model has no tools, credentials, or arbitrary URL access. Record model/prompt version, confidence, source fingerprint and cost where available. Suggestions require acceptance initially and never override locks. Timeouts/errors do not interrupt imports/sync. Do not call models during GET/report requests.

## 9. Frontend views

1. **Month dashboard (landing):** month selector; actual regular, exceptional, total, actual income and recorded surplus; clearly separate normalized regular/exceptional/total toggle or cards with annual allocation detail; prior month comparison; 3/6/12-complete-month regular average labeled by basis; coverage/unreviewed/fallback-date warnings. Category breakdown and optional exceptional events. Actual totals drill down to matching transactions; normalized totals drill down to contributions, not an incorrect purchase-month filter.
2. **Transaction list:** filters (month/date, account/person, category, spend type, event, source, kind, status, review); search; stable pagination; amounts, dates, merchant, account, category/type, source/provenance icons. Separate pending toggle. Inline edits and bulk edit with preview; “Create rule from this transaction” opens a populated preview, never silently applies history.
3. **Transaction detail/form:** source and effective/purchase/posting dates, fallback provenance, revision/audit, field locks/reset-to-rules, refund link, exclusion reason, and “Spread across months” editor with exact monthly preview. Manual entry works well with iPad touch controls; optimistic concurrency conflicts are explicit.
4. **Rules:** priority, enabled state, predicates/actions, preview, apply/reclassify history; normal users do not write executable code.
5. **Imports:** upload, column/sign/date mapping, sample preview, duplicate resolution, progress and commit summary.
6. **Connections/accounts:** card owner/display names, Plaid health/last sync, Link/update/disconnect, account selection, duplicate-account warnings.
7. **Settings/planning:** household timezone/currency, categories/events, month coverage, optional income schedule, AI controls and backups status (no secret values).

Responsive list/table with mobile detail drawer, accessible labels, numeric/date keyboard hints, and a usable no-color-only distinction between regular/exceptional. Prefer simple charts over a dashboard framework. Error/empty/offline states and stale data timestamp are part of each view.

## 10. Security and correctness summary

No password is not a security boundary: anyone able to reach this listener can read/change household finances and initiate configured operations. Confirm the trusted subnet. Defense in depth and concrete deployment checks are in OPERATIONS.md.

Use exact host/origin allowlists, CSRF token + strict mutation origin checks, same-origin JSON APIs, no permissive CORS, file/path protections, CSP compatible with documented Plaid Link requirements, and scrubbed logging. Never expose generic command execution, arbitrary provider base URLs from the UI, SQL consoles, or raw filesystem paths.

Every write uses an explicit transaction and revision; job leases/retries and mutation idempotency are persisted. Sensitive writes have redacted audit events. Backups must include a securely stored encryption key recovery path separately from the data. Financial invariants and source-reconciliation behavior are tested before a real household connects.
