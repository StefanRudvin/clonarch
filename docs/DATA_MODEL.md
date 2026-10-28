# Data model (proposed v1)

## Conventions

- UUID identifiers serialized as strings; timestamps UTC ISO-8601, date-only financial fields `YYYY-MM-DD`.
- Monetary columns signed 64-bit integer minor units, currency ISO 4217. Enforce configured v1 currency and safe JSON integer bounds, including totals; reject unsupported currencies with a clear issue. Do not truncate fractions or silently coerce foreign currency.
- Every mutable aggregate has `version` (integer), `created_at`, `updated_at`. A monotonic household `ledger_revision` advances on changes affecting reporting/classification; settings and taxonomy revisions are tracked too.
- All foreign keys enabled; archived taxonomy/account rows remain addressable by historical records. Foreign-key indexes and declared uniqueness constraints are required.
- SQLite on local disk, migrations through Alembic only, WAL with busy timeout. JSON is validated through typed models before writing; query-heavy fields have ordinary indexed columns.

## Core tables

### household_settings (one household)

`id`, `name`, `timezone`, `currency`, `ledger_revision`, `taxonomy_revision`, `version`.

Confirmed currency USD; proposed Eastern IANA timezone America/New_York; expense date basis purchase/authorization with visible posted fallback, income basis posted deposit. No multitenancy/user authentication machinery in v1. Two household members are attribution, not access controls; spouse has no income.

### members

`id`, `display_name`, `archived_at`, `version`. Start with owner and spouse only after names are provided. Nullable owner means shared/unspecified.

### accounts

`id`, `member_id?`, `display_name`, `institution_name?`, `account_type` (`credit_card`, `checking`, `cash`, `other`), `currency`, `masked_last4?`, `archived_at?`, `version`.

Only masked digits, never full account/card numbers. Accounts can have manual/import records before a Plaid connection. Archiving hides selection but preserves history. Ownership is editable attribution; reports use current attribution in v1, not a historical ownership ledger.

### connections

`id`, `provider` (`plaid`), `institution_id?`, `institution_name?`, `provider_item_id` unique, `environment`, `access_token_ciphertext?`, `key_version?`, `sync_cursor?`, `state`, `requested_history_days` (365 at first Link), `transactions_update_status?`, `history_replay_required`, `last_attempt_at?`, `last_success_at?`, `last_safe_error?`, `sync_generation`, `version`.

Cursor is Item-wide, never reused for an account-filtered stream. Newly selected accounts set history_replay_required and require a safe full replay from null cursor on the existing Item; stage/commit atomically and deduplicate by source IDs. Persist a redacted count/history of Production Item creation where known because Trial slots are lifetime-limited; actual remaining quota is confirmed via dashboard, not a guessed local counter.

State: `linking`, `active`, `needs_reauth`, `error`, `disconnecting`, `disconnected`. Secrets are not part of response serialization or normal object repr/logging. Preserve revocation-pending state until confirmed. Initial Link sessions are separate short-lived records bound to browser session and intended operation.

### account_sources

`id`, `account_id`, `provider`, `connection_id?`, `external_account_id?`, `selected`, `history_from?`, `history_to?`.

Unique `(connection_id, external_account_id)` for Plaid. Allows a manual/import account to be explicitly matched to a later connected account, without duplicating ledger history. Verified same-underlying-account views can point to one canonical account; this reconciliation must be explicit, not a last-four match.

### categories

`id`, `name`, `normalized_name` unique, `parent_id?`, `sort_order`, `archived_at?`, `version`.

One level of optional nesting initially; no cycles. No category implies a spend type. Uncategorized is a null `category_id`, represented explicitly in APIs/reports. A category with history is archived, not hard-deleted.

### events

`id`, `name`, `description?`, `start_date?`, `end_date?`, `archived_at?`, `version`. For named exceptional events, not budget envelopes. Event assignment requires `spend_type=exceptional`; changing to regular requires clearing the event explicitly or returning validation error.

### transactions

Canonical identity independent of source:

- `id`, `account_id`, `currency`.
- `source_amount_minor`, `source_posted_date?`, `source_authorized_date?`, `source_description`, `source_merchant?`, `source_status` (`pending`, `posted`, `removed`), `source_kind_hint?`.
- `source_fingerprint` (hash of normalized classifiable fields), `source_revision`.
- `user_overrides_json`: typed field map; absent key = unlocked, present key (even null) = explicit user decision. Allowed keys: amount/date/description, kind, category, spend type, event, recurring hint. Amount/date overrides do not erase source fields.
- `classification_json`: assignments and provenance per unlocked field, rule/model versions and source fingerprint. Rebuildable, but keep audit of previous assignments.
- Effective indexed projection: `amount_minor`, `effective_date?`, `date_provenance` (`user`, `authorized`, `posted_fallback`, `posted_income`, `manual_purchase`, `import_purchase`), `description`, `merchant?`, `status`, `kind`, `category_id?`, `spend_type`, `event_id?`, `recurring_hint`, `review_status`, `excluded`.
- `refund_of_id?`, `note?`, `exclude_reason?`, `deleted_at?`, `version`, timestamps.

`spend_type` always regular/exceptional on the record, but ignored in reports for income/transfers. `review_status`: `unreviewed` / `reviewed`; editing one field does not claim all fields were reviewed unless requested. API exposes which values are provisional and each field's provenance/lock.

The projection is updated in the same transaction as source/override/classification changes. It is not an independent source of truth. All entry paths share one projection builder and invariant validator.

A posted transaction must have an effective date. Expenses/refunds use user purchase-date override > authorized/purchase date > posted fallback; income uses user override > posted deposit date. Preserve both source dates. Pending rows may have an authorized date only (Plaid's pending date is occurrence, not settlement). Removed/deleted/excluded/pending rows do not count in settled reports. Only manual-only records can be soft-deleted through the manual delete route; provider records can be excluded or removed by provider sync.

Refund links must be same-currency expense records; no self-link/cycle. Amount of a single or aggregate refund can exceed purchase amount in real correction cases, so flag for review instead of silently capping. Changing the linked purchase's classification recomputes inherited unlocked refund fields, without changing refund date or manual locks.

### transaction_sources

`id`, `transaction_id`, `source_type` (`plaid`, `csv`, `manual`), `account_source_id?`, `external_transaction_id?`, `external_pending_id?`, `import_batch_id?`, `row_number?`, `source_payload_json`, `observed_at`, `is_current`.

Unique provider transaction key within provider/account-source namespace; unique committed `(import_batch_id, row_number)`. Retain aliases from pending-to-posted transitions and explicit CSV-to-Plaid reconciliation. Source payloads contain only needed financial fields; redact/remove tokens, full account numbers, and unrelated PII before storage. Retention is explicit; not arbitrary complete SDK responses forever.

A canonical transaction can have multiple source references. One authoritative current source supplies base fields (Plaid takes precedence over a matched CSV snapshot); others are provenance. Conflicting corrections require a review issue rather than oscillation on import/sync.

### review_issues

`id`, `transaction_id?`, `import_batch_id?`, `type`, `safe_details_json`, `state`, `resolution_json?`, timestamps.

Examples: uncertain transfer/refund kind, duplicate candidate, pending mapping ambiguity, source conflict, unsupported currency. Counts feed dashboard warnings. Resolving a duplicate chooses explicit keep-both/match/skip behavior and preserves audit.

## Rules and suggestions

### rules

`id`, `name`, `priority` unique among nonarchived rules (including disabled ones), `enabled`, `conditions_json`, `actions_json`, `version`, `archived_at?`, timestamps.

Typed/size-limited schema. Account/member/category/event references must exist. Condition grammar and action schema are in API.md. Unsupported regex is rejected at save/preview. Rule priority reorder is one transactional operation.

### previews

`id`, `type` (`rule`, `reclassify`, `bulk_edit`), `ledger_revision`, `taxonomy_revision`, `rule_set_version`, `input_hash`, `proposed_json`, `affected_rows_json_or_table`, `expires_at`, `created_at`.

Capture affected IDs and expected versions, not just a count. Cap preview size and paginate details. Apply is one-shot/idempotent, rejects stale revisions (409), and requires a fresh preview after concurrent changes. A job freezes the proposed patch and conditions; it does not read a now-changed rule silently.

### classification_suggestions

`id`, `transaction_id`, `source_fingerprint`, `provider`, `model`, `prompt_version`, `proposed_category_id?`, `proposed_spend_type?`, `confidence?`, `state` (`pending`, `accepted`, `rejected`, `stale`), `cost_metadata?`, timestamps.

Unique job/request identity prevents duplicate paid requests on retry where possible. An accepted suggestion is fingerprint-bound, lower precedence than rules, unless owner explicitly chooses a manual override. Never accept a suggestion after its transaction's source fingerprint or relevant taxonomy changes without revalidation.

## Import and sync state

### import_batches / import_rows

Batch: `id`, `file_hash`, `original_filename_sanitized`, `staged_path_internal`, `account_id?`, `mapping_json?`, `mapping_version`, `state`, `row_count`, `preview_revision`, `expires_at`, `committed_job_id?`, timestamps.

States: `uploaded` → `previewed` → `committing` → `committed`; `failed` / `expired` explicitly. Editing mapping invalidates preview/decisions. Persist canonical row candidates, row errors, duplicate candidates, user resolution, and final transaction ID in import_rows. Constraints prevent committing a batch twice. Imported source identities persist after staged file expiry.

CSV fingerprinting includes account, date, currency, signed amount, normalized descriptor and occurrence handling; it is a review hint, not a universal unique transaction key. File hash/mapping checks must not accidentally suppress legitimate repeated rows.

### sync_runs / sync_staging

Run: `id`, `connection_id`, `starting_cursor`, `next_cursor?`, `connection_generation`, `state`, `page_count`, `safe_error?`, timestamps. Stage added/modified/removed rows by run; cursor and canonical writes commit together after complete paging. Discard/restart invalidated pagination. Check generation/state again at commit so disconnect or account selection changes cannot be undone by an in-flight sync.

## Annual-bill normalization

### expense_allocations

`id`, `transaction_id` unique, `start_month`, `end_month_exclusive`, `note?`, `version`, timestamps.

One explicit whole-transaction schedule for an expense/refund, 1–60 calendar months proposed. No stored duplicate transactions, partial allocations or frozen copied amounts. Active/suspended status is derived from source eligibility; changes to amount/kind/status/exclusion invalidate reports and can raise allocation review issues. Schedule edits validate expected transaction and allocation versions. Allocation deletion is audited and removes only normalization metadata.

Read-time contribution is the current `-transaction.amount_minor`, divided exactly over N months: floor(abs(cents)/N), distribute remainder cents earliest first, reapply sign. Sum invariant equals original expenditure. Category/type/event/account come from current transaction, including manual locks. Refund spreading explicit, not automatic inheritance of the purchase's period.

Index `(start_month, end_month_exclusive)` for overlapping periods. Queries include source transactions outside report purchase-date window if their periods overlap; actual portion is removed once only in actual month before adding monthly contribution. See ARCHITECTURE.md for formulas, eligibility and distinction from income/actual surplus.

## Income and coverage

### income_schedules

`id`, `name`, `member_id?`, `currency`, `amount_per_payment_minor?`, `day_rules_json`, `weekend_policy`, `active_from`, `active_to?`, `version`.

Proposed day rules: 15th and last day of month, with `weekend_policy=none` until clarified. Actual income comes from owner's Chase checking via Transactions and reviewed payroll classification; spouse has no income. Holiday calendars and separate payroll verification products deferred. Amounts optional; missing amounts produce date-only reminders. Expected payments are derived values, never actual transactions. Optional matched transaction references only annotate an actual income entry; they never create income twice.

### month_coverage

`month` unique (`YYYY-MM`), `state` (`unknown`, `partial`, `complete`), `note?`, `confirmed_at?`, `version`.

Owner confirms complete coverage after considering manual and connected accounts. Account-source history boundaries provide warning hints, not proof of complete coverage. Complete-month averages exclude current month and any non-complete months; return the exact months/count used.

## Jobs, audit, idempotency

- `browser_sessions`: opaque random session ID hash, CSRF token secret/hash material, created/last-seen/expiry timestamps, and short-lived Link-session binding. No login identity or access-control claim. Proposed idle expiry 8 hours with rotation; expiry interrupts writes with a safe refresh response, never silently downgrades CSRF checks. Expired records are pruned.
- `jobs`: id, type, typed payload, state (`queued`, `running`, `succeeded`, `failed`, `cancelled`), progress, attempts, lease_owner, lease_until, next_attempt_at, result_json, safe_error, timestamps. Job writes/progress commits are separate from final atomic ledger writes. Persist work before returning 202.
- `audit_events`: id, timestamp, actor (`browser`, `worker`, `system`), browser_session_id? (not a user identity), action, entity type/id, before/after safe diff, request_id/job_id, change_set_id. No secrets/raw statements.
- `idempotency_records`: key + endpoint scope, request_hash, response/status or job_id, expiry. Same key+payload returns original outcome; different payload = 409. Proposed retention 30 days; permanent source/import uniqueness still prevents duplication after expiry.
- `change_sets`: id, operation, affected IDs/versions and typed old/new override values. Bulk undo restores only if affected current revisions still match; otherwise 409 with conflicts. No blind rollback over newer source/user changes. Retain at least the advertised undo window; show expiry in responses.

## Indexes and constraints to test

- Reporting: `(effective_date, status, kind, excluded)`, `(account_id, effective_date, id)`, category/type/date indexes as measured.
- Source uniqueness; provider Item/account identities; committed import row identity; lease claims and due jobs.
- Pagination stable on `(effective_date, id)`, with explicit pending null-date ordering.
- Integer amounts, USD-only, purchase-date preference/fallback provenance, posted date presence, kind/sign invariants, valid enums, parent-category acyclicity, refund validity, event/type compatibility.
- Allocation periods bounded/nonempty, single schedule per source transaction, exact signed-cent sum, correct actual-minus-original-plus-contribution math, including cross-month source dates/refunds/suspended sources.
- Per-connection sync lease/generation + atomic cursor advance; optimistic version checks on edits.
- All report-affecting mutations advance ledger revision once per atomic change set; all read totals use a consistent database snapshot.
