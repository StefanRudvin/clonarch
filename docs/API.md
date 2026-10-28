# Proposed HTTP API v1

This is the **target API contract**. The running 0.1 app implements only a subset; see [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) and HANDOFF.md for exact shipped routes. Do not assume every route/table/guarantee below exists yet. As features are added, reconcile this contract with FastAPI's OpenAPI and tests.

## 1. Common conventions

- Base `/api/v1`, same origin as frontend. JSON except CSV upload/export. All routes private to the approved LAN; there is no public or third-party backend API.
- IDs UUID strings. Money integer minor units, never JSON float; currency ISO 4217. Dates `YYYY-MM-DD`, month `YYYY-MM`, timestamps UTC ISO-8601.
- Standard success: `{ "data": ..., "meta": { "request_id": "...", "ledger_revision": 42 } }`. Lists: data is array; meta adds `next_cursor` (null at end) and optional total if requested.
- Error: `{ "error": { "code": "STALE_VERSION", "message": "...", "details": { ... }, "request_id": "..." } }`. Never raw exception/SDK traces.
- 200 reads/updates; 201 resource creation; 202 durable queued operation (data Job); 204 deletion without body. 400 invalid operation, 404 unknown ID, 409 revision/idempotency/duplicate conflict, 413 oversized input, 415 unsupported file type, 422 field/schema validation, 429 throttled, 502/503 provider unavailable. Host/Origin/CSRF or expired-browser-session rejection is 403, with specific safe error codes so the UI can refresh context. No auth-based 401 in initial LAN mode.
- Create/enqueue/apply/exchange/undo POST requests require `Idempotency-Key` (UUID). Same scope+key+request hash returns original resource/job, including 202; different hash = 409. Request hashing excludes secrets from logs but includes a secure digest for equality. Retain replay records for 30 days; durable source constraints still protect imports/sync beyond that.
- PATCH and archive/delete require `expected_version` in body or query as specified; missing is 422, mismatch 409. Bulk previews bind row versions and ledger/taxonomy/rule revisions. Never last-writer-wins silently.
- No arbitrary SQL sort/filter expressions. Unknown fields/operators rejected. List `limit` default 50/max 200. Opaque cursors bind filter hash, sort and ledger revision; a changed ledger invalidates with `409 CURSOR_STALE`, so UI restarts pagination. Escape searches and do not interpolate SQL.
- Reports/transaction queries use a consistent read snapshot. `meta.ledger_revision` permits UI cache invalidation. Mutations return new revisions and affected IDs or a change-set ID.
- Unsafe methods require a same-origin `Origin`, session cookie and `X-CSRF-Token`. The UI initializes via `/context`; cookie is opaque, HttpOnly, SameSite=Strict (Secure when HTTPS), no login claim. CORS disabled. Strict configured Host allowlist and unsafe Origin check also apply to uploads and Link exchange. Read requests with an explicit foreign Origin are rejected. See OPERATIONS.md.
- `Cache-Control: no-store` on financial/secret/token responses; `Referrer-Policy: no-referrer`. API paths never fall through to SPA HTML.

## 2. Common representations

### Transaction

```json
{
  "id": "uuid", "version": 3,
  "account_id": "uuid", "member_id": "uuid-or-null",
  "amount_minor": -4599, "currency": "USD",
  "effective_date": "2026-04-14", "authorized_date": "2026-04-14",
  "posted_date": "2026-04-15", "date_provenance": "authorized",
  "description": "EXAMPLE MARKET 123", "merchant": "Example Market",
  "status": "posted", "kind": "expense",
  "category_id": "uuid-or-null", "spend_type": "regular", "event_id": null,
  "recurring_hint": "unknown", "review_status": "unreviewed",
  "excluded": false, "exclude_reason": null, "note": null,
  "refund_of_id": null,
  "sources": [{"type": "csv", "label": "April statement"}],
  "field_provenance": {
    "category_id": {"source": "rule", "rule_id": "uuid", "rule_version": 2, "locked": false},
    "spend_type": {"source": "default", "locked": false, "provisional": true}
  },
  "has_review_issues": false, "updated_at": "2026-04-16T12:00:00Z"
}
```

Source kinds for provenance: `manual`, `rule`, `accepted_suggestion`, `provider`, `linked_refund`, `default`. `recurring_hint`: `unknown`, `yes`, `no`. Expenses/refunds use purchase/authorization date with visible posted fallback; income uses deposit posting date, explicit user overrides win. `date_provenance` enum is in DATA_MODEL.md. Manual/CSV effective_date means purchase date. List/detail includes optional allocation summary (ID, version, period, active/suspended), not synthetic transactions. Pending records can have null effective date. List returns compact provenance; detail includes safe source/effective differences, locks, review issues and permitted actions, never raw tokens/provider secret payloads.

### Job

`{id, type, state, progress:{completed,total?,message?}, attempts, created_at, started_at?, finished_at?, result?, error?}`. States and result schema depend on typed job type. Errors are redacted structured objects; result includes changed counts/IDs or paginated result reference. Frontend polls with backoff; no WebSocket required.

### TransactionFilter

`month` OR `date_from`/`date_to_exclusive` (not both); optional `account_ids`, `member_ids`, `category_ids`, `uncategorized`, `spend_type`, `event_ids`, `kinds`, `statuses`, `sources`, `review_status`, `excluded`, `has_review_issues`, `search`. Query arrays use repeated parameters, booleans explicit. Default `statuses=posted`, `excluded=false`; ordinary transaction list includes all kinds unless filtered. A dashboard drill-down explicitly supplies `kinds=expense&kinds=refund` and matching spend type, status, date and exclusions. List sort: `date_desc` default, `date_asc`, `amount_asc`, `amount_desc`, always ID tie-breaker; pending null dates sort last. Month/date endpoints enforce valid bounded ranges.

## 3. Context, health, settings and attribution

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/context` | — | Household display/settings, feature flags, API version, trusted current origin and CSRF token; sets short-lived opaque browser session. No secrets. |
| GET `/health/live` | — | Minimal liveness only. |
| GET `/health/ready` | — | DB/migration readiness; redacted, no environment dump. |
| GET `/settings` | — | Currency, timezone, coverage policy, AI enabled/provider label, backup/sync status; no credentials. |
| PATCH `/settings` | `{expected_version, timezone?, household_name?}` | Settings. Currency changes with data exist are rejected in v1. No network bind/firewall/provider URL configuration through browser. |
| GET `/members` | — | Member array. |
| POST `/members` | `{display_name}` | 201 Member. |
| PATCH `/members/{id}` | `{expected_version, display_name?, archived?}` | Member. Cannot archive the only active member accidentally without warning. |

Server-provisioned secret/config keys do not have generic read/write API endpoints. AI capability changes are deliberately separate from ordinary settings.

## 4. Accounts, taxonomy and events

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/accounts` | `include_archived=false` | Accounts including owner, source summary, selected status and history hints. |
| POST `/accounts` | `{display_name, member_id?, account_type, currency}` | 201 manual/import Account. Does not establish a bank connection. |
| PATCH `/accounts/{id}` | `{expected_version, display_name?, member_id?, archived?}` | Account; no provider IDs editable here. |
| GET `/categories` | `include_archived=false` | Category tree/array with versions. |
| POST `/categories` | `{name, parent_id?, sort_order?}` | 201 Category. |
| PATCH `/categories/{id}` | `{expected_version, name?, parent_id?, sort_order?, archived?}` | Category; reject cycles/duplicate normalized names. Archive does not recategorize old records. |
| GET `/events` | `include_archived=false` | Events. |
| POST `/events` | `{name, description?, start_date?, end_date?}` | 201 Event. |
| PATCH `/events/{id}` | `{expected_version, name?, description?, start_date?, end_date?, archived?}` | Event. |

No hard deletion of referenced accounts, members, categories or events. Null category represents Uncategorized; do not create a reserved-ID fake row.

## 5. Ledger, editing, review and export

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/transactions` | TransactionFilter + cursor/limit/sort | Transaction list. |
| POST `/transactions` | `{account_id, amount_minor, currency, effective_date, description, kind, category_id?, spend_type?, event_id?, recurring_hint?, note?, refund_of_id?}` | 201 manual Transaction. Explicit classification fields become overrides; omitted fields go through rules/defaults. Default status posted. |
| GET `/transactions/{id}` | — | Transaction detail with safe source snapshot/provenance. |
| PATCH `/transactions/{id}` | TransactionPatch below | Updated Transaction and optional change_set_id. |
| DELETE `/transactions/{id}` | query `expected_version` | 204 soft-delete manual-only row; 409 if source-connected/imported. Use exclusion for imported/synced rows. Audit survives. |
| GET `/transactions/{id}/audit` | cursor/limit | Paginated redacted history. |
| POST `/transactions/bulk-preview` | `{transaction_ids:[...], patch:...}` OR `{filter:..., patch:...}` (exactly one selector) | Preview with row versions, affected counts and paginated before/after samples. Proposed cap 5,000 records per operation. |
| POST `/transactions/bulk-apply` | `{preview_id}` | 202 bulk-edit Job, one atomic change set; stale preview fails. |
| POST `/change-sets/{id}/undo` | `{expected_ledger_revision}` | 202 undo Job; rejects expired/changed affected versions, does not overwrite newer edits. |
| GET `/transactions/export` | TransactionFilter, `format=csv` | Streaming CSV from a consistent snapshot; same filtering and signs as list. No hidden/raw secrets. |
| GET `/review-issues` | `state=open`, `types?`, cursor/limit | Issues and permitted resolution options. |
| POST `/review-issues/{id}/resolve` | `{expected_version, resolution:...}` | Updated issue/transaction. Typed per issue: keep-both, match-specific-canonical, source selection, acknowledge, etc. Validate candidate IDs and version conflicts. |

`TransactionPatch`:

```json
{
  "expected_version": 3,
  "set": {"category_id": "uuid", "spend_type": "exceptional", "event_id": "uuid"},
  "clear_overrides": ["recurring_hint"],
  "note": "optional new note or null",
  "excluded": false,
  "exclude_reason": null,
  "review_status": "reviewed",
  "refund_of_id": null
}
```

All keys except `expected_version` optional; at least one actual operation required. `set` allows amount/date/description overrides, kind, category, spend type, event, recurring hint. Explicit null is allowed only for nullable fields and **locks** null; `clear_overrides` removes a lock and recomputes that field. A field cannot appear in both. Synced amount/date changes must include `override_reason` and detail returns source difference. Account/currency/source status cannot be moved/rewritten here. Note/exclusion/refund link/review are user metadata, not rule fields. Excluding requires a reason; re-including clears it. Event/type and sign/kind invariant errors are 422, never silent coercions.

Bulk patches use the same mutable fields but no individual expected_version; preview captures each version. Cannot bulk override source amount/date or refund links in v1. Apply/undo recheck versions inside the final transaction; if one is stale, fail the entire job with no partial ledger update.

CSV export protects spreadsheet users: quote normally and neutralize formula prefixes in textual fields; preserve true numeric amount columns. Use `Content-Disposition` with a server-selected safe filename. The export format is documented separately from bank-specific input mapping and can round-trip with an explicit Clonarch import mapping.

## 6. Rules and reclassification

### RuleDefinition

```json
{
  "name": "Example Market groceries", "enabled": true, "priority": 10,
  "conditions": {
    "all": [
      {"field": "description", "op": "regex", "value": "^example market\\b"},
      {"field": "kind", "op": "in", "value": ["expense", "refund"]}
    ]
  },
  "actions": {"category_id": "uuid", "spend_type": "regular"}
}
```

Allowed text fields `merchant`, `description`; text ops `contains`, `equals`, `regex`. Exact/in fields `account_id`, `member_id`, `kind`, `currency`; numeric `amount_minor` ops `gte`/`lte`. All predicates AND; no nesting/NOT/arbitrary expression language initially. At most 20 predicates; text/pattern lengths bounded (proposed 512-char regex and 4,096-char matching input); reject unsupported patterns. Rules act on normalized **source** text/kind inputs to avoid action-dependent evaluation loops. Manual financial/text overrides affect reporting, not the source-match fingerprint; UI explains this distinction.

Actions: any nonempty subset of `category_id` (nullable), `spend_type`, `event_id` (nullable), `recurring_hint`, `kind`. A kind action is explicit and sign-validated per match. Event action also requires exceptional spend type or a compatible existing value; preview shows validation errors. Rules never set amount/date/notes/exclusion or financial account identity. Invalid action bundles block historical apply, but on automatic ingestion they are skipped with a review issue rather than blocking source synchronization.

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/rules` | `include_archived=false` | Ordered rules + rule_set_version. |
| POST `/rules` | RuleDefinition | 201 Rule; affects future source classification, not a silent history backfill. Priority collisions return 409. |
| PATCH `/rules/{id}` | `{expected_version, ...changed RuleDefinition fields}` | Rule; increments rule-set version, no automatic historical changes. |
| POST `/rules/{id}/archive` | `{expected_version}` | Archived Rule with provenance retained. |
| POST `/rules/reorder` | `{expected_rule_set_version, ordered_rule_ids:[...]}` | Rules/new priorities in one transaction; must include exactly all nonarchived rules. |
| POST `/rules/preview` | `{definition:RuleDefinition, filter:TransactionFilter}` | Draft preview, normalization and sample matches. Cannot apply this preview directly. |
| POST `/rules/{id}/preview` | `{expected_version, filter:TransactionFilter}` | Applicable historical preview using current complete ordered rule set, showing this rule's contribution; locks honored. |
| POST `/rules/{id}/apply` | `{preview_id}` | 202 reclassification Job; preview must bind this rule/version. |
| POST `/reclassification/preview` | `{filter:TransactionFilter}` | Preview a full fresh evaluation of unlocked fields under all current rules/defaults/valid suggestions. |
| POST `/reclassification/apply` | `{preview_id}` | 202 reclassification Job (used after disable/archive/reorder). |
| GET `/previews/{id}` | cursor/limit | Preview metadata and paginated changed/locked/invalid sample details. |

A preview returns `{id, type, expires_at, ledger_revision, rule_set_version, matched_count, changed_count, locked_count, invalid_count, sample, can_apply}`. Proposed expiry 30 minutes. Invalid matched rows block whole apply until resolved or filtered out; no undisclosed partial success. Draft previews cannot be applied. Apply validates before queueing and again in atomic commit, so later concurrent writes can fail the job safely. Rule editing and history application are deliberately separate actions.

## 7. CSV imports

| Method/path | Request | Result / behavior |
|---|---|---|
| POST `/imports` | multipart `file` (CSV) | 201 Import with detected encoding/headers, first safe sample rows, hash/expiry. No ledger writes. |
| GET `/imports` | cursor/limit | Import history, states and counts; no local filesystem paths. |
| GET `/imports/{id}` | `rows_cursor?`, `limit?` | State, mapping/version, paginated validation rows and duplicate candidates. |
| POST `/imports/{id}/preview` | `{expected_version, account_id, mapping:ImportMapping}` | Validated row preview, updated version; prior decisions invalidated. |
| POST `/imports/{id}/decisions` | `{expected_version, decisions:[{row_number, action, match_transaction_id?, expected_match_version?}]}` | Updated preview/version. Action `import`, `skip`, `match_existing`; ambiguous duplicates require explicit decision. |
| POST `/imports/{id}/commit` | `{expected_version, preview_revision}` | 202 import Job; permanent batch/source uniqueness; no unresolved/fatal rows allowed. |
| DELETE `/imports/{id}` | query `expected_version` | 204 discard noncommitting staged upload; committed batch metadata cannot be deleted this way. |

`ImportMapping`: `{date_column, date_format, description_column, merchant_column?, amount:{column, convention:"positive_outflow"|"negative_outflow"}|{debit_column,credit_column}, currency:"USD"|{column}, status_column?, kind_column?, source_id_column?, delimiter, encoding, skip_rows?}`. Exactly one amount representation. Specify decimal separator explicitly if not dot; allow only supported encodings/date formats. Recognized status/kind values use explicit mapping dictionaries, not hidden guessing. Parsing errors reference row/column and safe value excerpt; amounts use exact Decimal conversion. API accepts no filesystem path, executable mapping code, or external URL.

Preview returns counts (`valid`, `invalid`, `duplicate_candidates`, `already_imported`) and per-row normalized candidates/issues/decisions. Two same-value purchases are not automatically merged. Committing revalidates account/source matches and current versions; a new duplicate conflict fails before ledger writes. File-name/hash data is sensitive and not logged at normal level. Identical committed file/account/mapping returns `409 ALREADY_IMPORTED` with prior import ID rather than creating a second batch commit.

## 8. Plaid connections and jobs

Feature flag unavailable until configured/approved; disabled feature returns `409 FEATURE_DISABLED`. No access tokens in responses.

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/connections` | — | Safe connection/account summaries, status, last sync/error, environment. |
| POST `/plaid/link-sessions` | `{mode:"create"|"update", connection_id?}` | 201 `{id, link_token, expires_at, redirect_uri?, environment}`. Update requires existing connection; link session bound to browser. |
| POST `/plaid/link-sessions/{id}/exchange` | `{public_token, metadata:{institution_id?, selected_account_ids?}}` | Connection + discovered accounts; tokens stay server-side. Metadata is untrusted hints, verified server-side. Single-use session/idempotency handles retries. |
| POST `/plaid/link-sessions/{id}/complete-update` | `{}` | Rechecks existing Item after Link update; returns safe connection status. No new token assumed. |
| GET `/plaid/link-sessions/{id}` | — | Safe session state/resume data for initiating browser only, not access token. |
| PATCH `/connections/{id}/accounts` | `{expected_version, selections:[{external_account_id, selected, existing_account_id?, member_id?, display_name?}]}` | Updated mapping + history-replay-required status/job reference. Verify IDs belong to Item; explicit canonical matching. Increments generation, invalidates old in-flight commits; newly selected accounts trigger idempotent Item-wide null-cursor history replay on same Item, not a new Trial slot. |
| POST `/connections/{id}/sync` | `{}` | 202 sync Job (coalesces if already queued/running); no chargeable Refresh product call. |
| POST `/connections/{id}/disconnect` | `{expected_version, retain_history:true}` | 202 revocation Job. State prevents new sync; revoke then clear token. History purge unsupported here. |
| GET `/jobs/{id}` | — | Job state/result/error. |
| GET `/jobs` | `type?`, `state?`, cursor/limit | Recent safe job summaries. |
| POST `/jobs/{id}/cancel` | `{}` | Best-effort cancel only queued or cancellable work before commit. 409 if commit underway or operation noncancellable; never implies rolled-back completed writes. |

Server creates new Link tokens with only Transactions and `transactions.days_requested=365`; record requested history and Trial lifetime Item usage. Discover checking/cards via `/accounts/get`; checking payroll uses Transactions, not separate Income/Auth products. `GET /connections` includes requested_history_days, transactions_update_status, history_replay_required and safe Trial warning (unknown dashboard quota stays unknown).

Official docs support normal web popup OAuth without redirect_uri: test standalone iPad Safari first, omitting both redirect URI and public webhook. If redirect mode becomes necessary, a supplied production URI must be HTTPS; optional same-origin SPA `/connections/plaid-return` resumes a server-bound session only once its actual LAN-compatible URI is verified. Landing GET is nonmutating and tolerates a missing Strict cookie on cross-site entry; same-origin resumption still requires session binding and CSRF. Never put access tokens/provider secrets/financial data in URLs. Preserve account mapping during update mode; do not consume new Production Items merely to reauthenticate. Full response mapping/sources: INTEGRATIONS.md.

Retries use a safe classified policy: bounded exponential backoff on rate limits/transient network errors, no retries for invalid credentials until reauth. Sync result contains added/modified/removed/pending-reconciled/issue counts and last successful completion; no raw provider records.

## 9. Monthly reports, coverage and pay planning

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/reports/monthly` | `month`, optional account/member filters | MonthlyReport below: actual purchase-date figures plus separate normalized figures. Same eligibility rules everywhere. |
| GET `/reports/monthly/contributions` | `month`, `basis=actual|normalized`, optional account/member/category/spend-type/event filters, cursor/limit | Paginated expense/refund contribution rows reconciling to selected report bucket, including allocations from purchases outside month. Rows include transaction_id, actual signed amount/date, contribution_expenditure_minor, contribution_kind and allocation period. |
| GET `/reports/trend` | `from_month`, `to_month`, `basis=actual|normalized` default actual, optional account/member filters | Up to 36 points, explicit selected basis, coverage flags, comparisons and 3/6/12-complete-month regular averages with included months. No silent zero-filling. Actual income/surplus stay labeled actual regardless of spending basis. |
| GET `/coverage` | `from_month`, `to_month` | Household confirmations plus account-source history warnings. |
| PUT `/coverage/{month}` | `{expected_version:0 if new, state, note?}` | Coverage row. Setting complete requires explicit owner action, not just successful sync. |
| GET `/income-schedules` | — | Schedule list. |
| POST `/income-schedules` | `{name, member_id?, currency, amount_per_payment_minor?, days:[15,"last"], weekend_policy:"none"|"previous_weekday"|"next_weekday", active_from, active_to?}` | 201 Schedule. No holiday calendar guarantee. |
| PATCH `/income-schedules/{id}` | `{expected_version, ...mutable schedule fields}` | Schedule. Ending/archiving stops future predictions, never changes actual income. |
| GET `/income-forecast` | `from_date`, `to_date_exclusive` (max 12 months) | Expected dates/optional amounts, schedule IDs, and separately matched actual transaction references if available. Never creates ledger rows. |

`MonthlyReport`:

```json
{
  "month": "2026-04", "currency": "USD", "date_basis": "purchase_with_posted_fallback",
  "timezone": "America/New_York", "income_date_basis": "posted_or_user_override",
  "regular": {"gross_expense_minor": 410000, "refund_minor": 10000, "net_minor": 400000},
  "exceptional": {"gross_expense_minor": 180000, "refund_minor": 0, "net_minor": 180000},
  "total_expense_minor": 580000, "actual_income_minor": 600000,
  "recorded_surplus_minor": 20000,
  "normalized": {"regular_net_minor": 290000, "exceptional_net_minor": 180000, "total_expense_minor": 470000},
  "by_category": [], "by_event": [],
  "counts": {"posted": 90, "pending": 3, "unreviewed_expense_or_refund": 8, "uncategorized": 4, "review_issues": 1},
  "coverage": {"state": "partial", "account_warnings": []},
  "warnings": ["Actual income may be incomplete"]
}
```

Top-level financial fields are **actual**. Example assumes $1,200 of regular actual expenditure is explicitly allocated across 12 months, $100 this month: normalized regular = $4,000 − $1,200 + $100 = $2,900. Normalized amounts do not change actual income or recorded_surplus_minor. Category rows include ID/null, name, actual regular/exceptional/net amounts and separate normalized regular/exceptional/net amounts plus source-record counts. Event rows likewise distinguish actual vs normalized. Counts/coverage include explicit posted-date fallback and allocation-review warnings in implemented schema. Pending counts are informational; no pending amounts in either settled basis. No double-counting parent plus child taxonomy rollups. All comparative/allocation arithmetic server-side.

### Annual-bill allocation API

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/transactions/{id}/allocation` | — | Allocation (404 if absent): id/version, transaction_id/version, start_month, end_month_exclusive, derived active/suspended status, note and exact monthly contribution list. |
| POST `/transactions/{id}/allocation-preview` | `{expected_transaction_version, start_month, end_month_exclusive}` | Stateless proposed monthly values and actual-vs-normalized effect, no ledger writes; bounded 1–60 calendar months. Does not bypass mutation Origin/CSRF. |
| PUT `/transactions/{id}/allocation` | `{expected_version:0 if new, expected_transaction_version, start_month, end_month_exclusive, note?}` | 201 create / 200 update one allocation, with audit and new ledger revision. Expense/refund only, posted and eligible at creation. Expected versions prevent a stale preview amount/period from being applied silently. |
| DELETE `/transactions/{id}/allocation` | query `expected_version`, `expected_transaction_version` | 204 remove normalization metadata only; original transaction remains unchanged. |

Allocation creation PUT also requires Idempotency-Key. One whole-transaction schedule only; positive contribution = expense, negative = refund, unlike signed household ledger amount. Exact cent/remainder formula and source-change/suspension rules are in ARCHITECTURE.md. Manual period edit is required to spread a refund; no automatic retroactive actual-ledger restatement. Contribution rows paginate under the same revision-bound cursor rules as transactions. Their sum equals selected monthly bucket; do not implement normalized drill-down as a purchase-month transaction query. Source amount changes recompute scheduled values and generate a review warning, without duplicating source amounts.

## 10. Optional classifier assistance / JEX

Owner permits remote JEX classification using their Codex account. Proposed provider_id `codex_cli_subscription`, disabled until dedicated official CLI install/login, demonstrated tool-free OS isolation, actual field disclosure and quota controls. No CLI is installed yet and this agent's authentication is not reused. API-key billing requires separate explicit approval, no automatic fallback. See INTEGRATIONS.md. Secrets/CLI auth provisioned outside browser API.

| Method/path | Request | Result / behavior |
|---|---|---|
| GET `/classification/capabilities` | — | Enabled provider/model labels, auth_mode and ready/reauth/blocked state, approved input fields, batch/quota/cost limits; no keys, auth files or arbitrary endpoint URLs. |
| POST `/classification/suggest` | `{transaction_ids:[...], provider_id}` | 202 suggestion Job; source fingerprints frozen, bounded batch, explicit UI disclosure. Unknown/unapproved provider rejected. |
| GET `/classification/suggestions` | `state=pending`, `transaction_id?`, cursor/limit | Suggestions with provenance, confidence, stale flag and transaction version. |
| POST `/classification/suggestions/{id}/accept` | `{expected_transaction_version, fields:["category_id","spend_type"]}` | Transaction + accepted suggestion state. Revalidate fingerprint/taxonomy/sign/event constraints. Existing manual locks are not overwritten. |
| POST `/classification/suggestions/{id}/reject` | `{}` | Rejected suggestion; no ledger change. |

Acceptance normally remains lower precedence than matching rules; UI shows effective outcome and conflicting rule instead of pretending suggestion won. To force a value, use a manual TransactionPatch. No auto-accept/continuous inference/LLM-created regex rules in initial scope.

## 11. Frontend invalidation / error behavior

- Ledger/allocation mutation: invalidate affected transaction/detail/allocation/audit/review caches, monthly/trend/contribution reports (including months outside purchase month), and previews/cursors bound to older revision.
- Rule/taxonomy changes: invalidate relevant lists and previews; historical totals change only after effective classifications actually change. Renaming categories updates display labels immediately.
- 409: show a specific refresh/review action with preserved unsaved edits; never automatically overwrite concurrent changes.
- Jobs: poll until terminal, then refresh impacted views and show changed/skipped/issues summary. Do not show optimistic final totals for a queued job.
- Provider offline: cached local ledger/reporting still works; show last successful sync prominently.
- No token/secret values in error toasts, analytics, client storage, query strings or crash reports. No external analytics in v1.
