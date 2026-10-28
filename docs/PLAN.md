# Implementation plan

## Status and ordering

A first synthetic/manual 0.1 UI is implemented and running at 192.168.105.10:8787; scoped project-local installation was approved/completed. `docs/IMPLEMENTATION_STATUS.md` lists shipped scope and gaps. Phases below remain the target, **not claims of completion**. No firewall/router/boot changes, Plaid calls, Codex login/inference or real financial data. See QUESTIONS.md and INTEGRATIONS.md.

Continue incrementally from the MVP. Plaid Trial is a core follow-on; generic CSV remains provisional until owner headers arrive. Keep each phase independently testable.

## Phase 0 — Confirm scope and feasibility

Tasks:
- Completed owner answers: current VM, USD/Eastern/purchase dates, default regular, annual spreading, owner's Chase checking income, spouse no income, latest 2 Chase+2 Amex cards, one-year history and remote JEX/Codex preference. No need to re-ask all eight questions.
- Public docs researched 2026-10-27: Trial's 10 lifetime Items, Transactions/history/sign/date fields and standard web popup OAuth. Sources/caveats in INTEGRATIONS.md; actual dashboard/Safari/bank availability remains untested.
- Bind/start completed: 192.168.105.10:8787 private IPv4 interface; no wildcard, public listener, router/firewall changes or boot service.
- Set timezone America/New_York (DST-aware Eastern) unless owner corrects literal fixed-EST interpretation; preserve bank date-only values.
- Determine card ownership/login grouping at Link rather than guessing. Credentials provided securely later, not in chat.
- Scoped installation was explicitly approved and completed: project-local uv/Python 3.12, backend/frontend/test packages and Codex CLI. No system Python upgrade or shell changes.
- JEX is a module name; Codex CLI is installed. Gate its adapter on separate owner login plus tool-free/OS-isolation verification. Do not extract agent credentials or assume API billing included.
- Use editable category/event defaults. Annual spreading is a v1 feature in a separate normalized basis, not full accounting accrual.

Exit (largely complete): owner decisions documented, install scope/owner approval recorded, and local MVP running. Plaid/Codex feasibility remains pending; CSV/manual path works without them.

## Phase 1 — Skeleton, contracts and security foundation

Tasks:
- Create backend/frontend source layout, package manifests, tests, gitignore, secret/config example with placeholder values only.
- Done: pinned ranges/resolved lockfiles and dependencies in project-local backend venv/frontend node_modules. No global tools or startup modifications.
- Implement typed configuration: fail closed for missing/invalid bind address, allowed Hosts/Origins, currency/timezone and encryption-key settings. Loopback-only in development unless explicitly approved otherwise.
- Build FastAPI app, standardized errors, request IDs, validation, context/CSRF/browser sessions, safe response/logging policy, same-origin SPA serving.
- Add migrations for core tables plus job/idempotency/audit scaffolding. Document schema migration procedure.
- Generate OpenAPI and frontend types. Implement a minimal responsive navigation shell and good error/loading states.

Exit/tests:
- Health/context endpoints work on loopback; API unknown paths are JSON 404, SPA routes work.
- Invalid Host, cross-origin mutation, missing CSRF, permissive CORS and path traversal cases fail closed.
- Blank database migrates correctly; FK/WAL settings verified; migrations are repeatable.
- No real secrets/data committed; no listener beyond approved scope; checks/test commands recorded in HANDOFF.md.

## Phase 2 — Correct ledger, manual entry and monthly reporting

Tasks:
- Implement Money/date enums/validators and one projection builder for effective transactions.
- Accounts/members, categories, exceptional events, manual transaction creation, editing/locking/reset, review/exclusion and audit.
- Refund links and transfer/card-payment treatment, including both checking/card sides. No split-transaction workflow.
- Implement consistent purchase-date monthly/trend queries with visible authorized-date fallbacks, coverage warnings and complete-month averages.
- Annual-bill allocation metadata/preview/editor and separate actual vs normalized reports/contribution drill-down. Preserve real transactions, exact cents and chosen past/future month period; actual income/surplus unaffected.
- Frontend dashboard, filterable list, detail/editor, category/type controls and manual entry.
- Optional twice-monthly schedule as a distinct planning overlay; synthetic/manual income until Chase checking is linked. Actual deposit classification, not expected schedule, determines recorded income.

Exit/tests:
- Synthetic April fixture: $4,100 regular charges, $100 regular refunds, $1,800 exceptional charges, $6,000 income, plus a $5,000 card payment and pending charge yields regular $4,000, exceptional $1,800, total $5,800, recorded surplus $200. Payment/pending rows never inflate totals.
- Category/event totals and filtered transaction list reconcile exactly to dashboard at same revision.
- Month-end/year/leap-year dates and Eastern DST scheduling correct; authorized Sept 30 / posted Oct 3 counts in September once posted; missing authorized date explicitly falls back to October. Income follows posted deposit date. Never shift bank date-only values through UTC.
- $1,200 annual bill over 12 months contributes $100/month normalized, once only; actual stays $1,200 in purchase month. $100/3 months distributes 3334/3333/3333 cents; signed refund distribution, cross-year/out-of-purchase-range periods, suspended sources, edits and removal reconcile exactly. No fake transactions, future actual spending or normalized actual-surplus claim.
- Refunds can make a month net-negative; missing income does not masquerade as accurate savings.
- Regular/exceptional independent from category/recurring; unclassified is visible and provisionally regular.
- Concurrent edits return 409; stale cursors refresh safely; manual field locks/reset-to-default work.
- iPad-sized viewport handles month selection, list, edits and form without hover-only controls.

## Phase 3 — Safe CSV imports, source reconciliation and export

Tasks:
- Redacted Chase/Amex format fixtures and an explicit generic mapper; bounded uploads/staging with expiry.
- Preview/validation, sign/date mapping, row-level decisions, exact duplicate detection and ambiguous candidate review.
- Source references and authoritative-source matching; preserve two genuine identical purchases and multi-account separation.
- Durable job worker/leases, transactional import commit, idempotency and restart behavior.
- Import UI with preview, decisions, counts, progress and failure recovery; CSV export with formula protection.

Exit/tests:
- Same import replay cannot add money twice, including retry after HTTP timeout/worker restart.
- Overlapping statement periods flag duplicates but do not erase legitimate repeated transactions.
- BOM/quoted delimiters/refunds/debit+credit columns/invalid dates/decimal precision/unsupported currency covered.
- CSV-to-existing-source match preserves canonical ID, edits and audit; stale match rejects before any ledger write.
- Partial parse/commit errors do not leave partial ledger writes or orphaned jobs; oversized uploads rejected; staging paths never exposed.
- No secret/formula injection/path traversal; staged retention cleanup does not remove durable import identities.

## Phase 4 — Deterministic persistent rules

Tasks:
- Safe regex engine (approval before adding dependency), normalized source matching, condition/action validation.
- Ordered per-field evaluation and provenance; manual locks first; explicit kind actions/sign safety.
- Rule CRUD/reorder/archive, draft/historical previews, full reclassification, bulk edit and conflict-safe undo.
- Frontend “create rule from this transaction,” preview samples/counts, apply history and job progress.
- Advisory recurring hint if useful; no hidden change to expenditure semantics.

Exit/tests:
- Regex match/no-match, Unicode/case/whitespace, rejected unsupported/dangerous patterns, bounded matching inputs.
- Priority collision/reorder, first matching setter per field, null locks and partial field actions behave deterministically.
- Editing/importing/syncing source fields never overwrites a manual lock; source changes recompute unlocked classifications.
- Rule save/archive/reorder does not silently rewrite history; preview/apply shows exact effects and conflicts.
- Queue-time and commit-time stale preview both fail safely; undo never overwrites newer changes.
- Large synthetic history preview is bounded/paginated and UI remains responsive.

## Phase 5 — Plaid (conditional, sandbox before real accounts)

Prerequisites: owner activates documented Trial entitlement and securely provides authorization; sandbox/mock tests first. Popup/no-redirect LAN-IP Safari Link needs actual testing; not a public callback requirement by assumption. Preserve 10 lifetime Production Item slots.

Tasks:
- Thin httpx adapter using documented API and Decimal JSON parsing (avoid SDK float money conversion); secrets encrypted at rest, fixture tests by default.
- Link session/update/resume: Transactions only, **365 days at initial Link**; no public webhook. Standard Safari popup/no redirect first, optional verified HTTPS redirect only if needed.
- Backend exchange, `/accounts/get`, selection/ownership/canonical mapping for 2 Chase+2 Amex cards and owner's Chase checking. Avoid duplicate Items per login; checking payroll via Transactions, not separate Income product.
- Item-wide cursor sync staging with per-Item leases/generation, stable paging and atomic final apply/cursor advance. Poll transactions_update_status until history complete; newly selected accounts trigger idempotent null-cursor replay on same Item, no Item recreation.
- Pending→posted reconciliation preserving identity/edits; modified/removed events, retry/backoff, safe status UI.
- Outbound scheduler and coalesced “sync now,” no public webhook or chargeable refresh calls.
- Disconnect/revocation workflow and recoverable credential-update errors.
- After separate real-connection approval, connect one login first, validate against a statement, then remaining logins/accounts. Check actual Amex/Chase overlap and history.

Exit/tests:
- Mocked page failures and pagination mutations never advance cursor partially; full restart from original cursor is safe.
- Repeated pages/jobs/events do not duplicate transactions; ambiguous pending/authorized-user duplicates are flagged rather than guessed.
- Canonical pending identity, category locks, notes and audit survive posted replacement and CSV overlap.
- Removal stops counting; provider changes cannot un-exclude or un-review user metadata silently.
- In-flight sync cannot commit after disconnect/account generation change; token never reaches UI/log/audit.
- Link/update works on actual iPad LAN-IP URL without public ingress, or remains explicitly blocked with CSV fallback.
- Real card/checking totals reconciled manually, payroll rules reviewed, both sides of credit-card payments excluded; last successful sync/history status visible. No promise all 365 days returned. Reauth/update doesn't consume unnecessary Trial slots; free constraints reflect actual dashboard entitlement.

## Phase 6 — Optional classification assistance

Prerequisites: remote JEX/Codex preference confirmed, but separate CLI install/login and minimized-data field confirmation pending. Demonstrate supported tool-free invocation and OS-enforced isolation using approved tooling; otherwise keep blocked. This phase cannot block core app.

Tasks:
- Provider-neutral adapter/capabilities, official `codex_cli_subscription` provider, disabled until ready; no undocumented account-token reuse/general API entitlement, arbitrary endpoint proxy or automatic API-billing fallback.
- Dedicated owner CLI login/private auth store, ephemeral structured output if supported, no tools/MCP/plugins/home/project/ledger/Plaid access. Read-only sandbox alone is insufficient; isolation is an enablement gate, not just a prompt.
- Minimized prompt payload, constrained taxonomy output, repeated-merchant batching/cache, bounded jobs/timeouts/subscription quota budget and safe reauth/rate-limit states.
- Suggested decisions with confidence/model/prompt/fingerprint provenance; UI accept/reject with conflict warning.
- No model tools, arbitrary code, rule auto-creation or auto-accept initially.

Exit/tests:
- Disabled mode performs zero inference calls; error/timeout never fails source imports.
- No names/account IDs/secrets/notes sent; untrusted merchant prompt injection cannot change schema or trigger tools.
- Stale fingerprint/taxonomy suggestions rejected; manual locks/rules remain authoritative.
- Repeat jobs avoid repeated model work where supported; shared subscription quota/reauth states enforced and visible. No secrets/external tools reachable from malicious merchant input; if this cannot be proven, adapter remains off.

## Phase 7 — Deployment, recovery and household acceptance

Current VM/app startup requested by owner; proposed private IP 192.168.105.10:8787. Dependency installation must first be separately approved. Persistent boot service/firewall/router changes and backups still need their own scoped approval. Basic server start need not wait for optional Plaid/JEX/CSV-specific polish: expose a working synthetic/manual MVP after phase 2, clearly label unavailable features, continue remaining phases incrementally.

Tasks:
- Run frontend production build and backend/worker using confirmed tooling; service unit or existing container environment only if approved. Never assume Docker exists or should be installed.
- Bind exactly approved private interface; restrict firewall to approved trusted subnet if needed and approved. No router changes, public ingress, tunnels, public webhook or public dev server.
- Validate IPv4/IPv6 listeners, interfaces, firewall and reachability from allowed/denied segments using authorized tests. Do not claim internet isolation from a localhost check alone.
- Document operational commands, configuration paths, listener/port, log redaction, schedule and update/rollback procedure.
- Configure encrypted backups with key recovery; exercise restore to an isolated path using SQLite backup API, not a live DB file copy.
- Retain CSV import/export as escape hatch. Do not store real data or secrets in git.

Exit/tests:
- Household can access production UI by approved LAN IP from iPad, review a month, edit category/type and save/apply a rule.
- Network boundary verified as far as available vantage points allow; any unverified WAN/IPv6 claim recorded.
- Worker/web restart and crash recovery tested; no import/sync money duplication; no permanently stuck leases.
- Backup restored and totals match; keys absent from git/logs; failure/status visible.
- Owner can answer “normal household spending this month vs one-time spending” and sees data coverage/income limitations clearly.

## Cross-cutting test strategy

- Unit: Money/date arithmetic; projection/locks; rules/regex; source identity/refunds; report math and coverage averages.
- Integration: temporary migrated SQLite DB; HTTP schema/errors/CSRF; import replay; job crash/retry; Plaid fixtures with paging mutations; concurrency/version conflicts.
- Contract: OpenAPI snapshot/type-generation checks; every documented route and schema implemented or explicitly marked deferred before release.
- UI/end-to-end: synthetic household flow (manual → import → classify → save/apply rule → dashboard), responsive iPad viewport, empty/loading/provider-error states.
- Security: network binding validation; Host/Origin/CSRF; secret redaction; path/upload/formula injection; forbidden arbitrary regex/code/URL execution; no analytics.
- Operational: migration on fixture copy, backup/restore, restart leases, scoped listener/firewall checks.

## Deliberately not in v1

Multi-household SaaS; public hosting; authentication/remote access; investment/net worth tracking; bill payment; envelope budgets; complex cash forecasting; automated bank statement scraping; split transactions; cross-currency conversion; full accrual accounting/automatic amortization (limited explicit annual-bill spreading is included); automatic actual-ledger refund restatement; model-driven automatic financial edits. Revisit only when a concrete household need warrants complexity.
