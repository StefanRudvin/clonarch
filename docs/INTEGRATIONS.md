# Integration research — Plaid and Codex/JEX

Public-source research checked **2026-10-27** without authenticated APIs, real accounts, credentials or classification calls. It was done before the project-local tool installation/server startup. Public documentation is evidence of API behavior, not verification of the owner's dashboard entitlement or actual bank responses.

## 1. Plaid Trial findings

Official sources:
- [Pricing and billing / Trial plans](https://plaid.com/docs/account/billing/)
- [OAuth, including Chase requirements](https://plaid.com/docs/link/oauth/)
- [Transactions overview](https://plaid.com/docs/transactions/)
- [Transactions API reference](https://plaid.com/docs/api/products/transactions/)
- [Link API reference](https://plaid.com/docs/api/link/)
- [Pending and posted transaction states](https://plaid.com/docs/transactions/transactions-data/)

Current billing docs state:
- Trial is free for eligible new US/Canada teams created on/after April 15, 2026; the owner intends to use it and will provide authorization later.
- Limit **10 Production Items ever created**. Removing an Item does **not** replenish this allowance. Preserve access tokens securely; develop with Sandbox, not repeated Production relinking.
- Trial includes Transactions (and Transactions Refresh), along with several other listed products. Clonarch needs only Transactions; do not enable Auth, Balance, Income, recurring add-ons or Refresh unnecessarily.
- One Item generally represents an authenticated institution/login relationship, not one card. Multiple Chase cards and checking may share an Item if available under the same login/consent.
- On paid-plan upgrade, existing Transactions Items begin incurring subscription charges. Do not upgrade plans or add products silently.
- Chase's Security Questionnaire requirement is waived for Trial according to current OAuth docs; this does not prove the owner's specific account is approved.

Caveat: the public [marketing pricing page](https://plaid.com/pricing/) still mentions legacy Limited Production / 200 calls. Use the explicit current Trial billing documentation and actual Dashboard agreement, not an invented blended limit. No fixed trial expiry was established in the reviewed Trial section; do not invent one or promise permanently unchanged terms.

## 2. Requested household and accounts

The owner's latest description is **four distinct cards: two Chase and two Amex**, superseding the original three-Chase/one-Amex description. Ownership and bank-login grouping will be assigned during Link/account selection; do not prefill the original ownership assumptions. Owner's Chase **checking** is an additional account for actual paycheck deposits; spouse has no income.

Discover accounts via `/accounts/get` after token exchange, including credit and depository/checking types. Select the four desired credit accounts plus checking. Keep checking debit expenses visible/reviewable; transfers and payments between checking and cards must not count as new expenses or income. There is no need for Plaid's separate Income verification product merely to read paycheck deposits in Transactions.

## 3. Initial Link and history request

Example **server-side** request (illustrative placeholders, not credentials):

```json
{
  "client_name": "Clonarch",
  "user": {"client_user_id": "stable-household-member-id"},
  "products": ["transactions"],
  "country_codes": ["US"],
  "language": "en",
  "transactions": {"days_requested": 365}
}
```

- Set `transactions.days_requested=365` at **initial** `/link/token/create` when initializing Transactions. Default is only 90; documented maximum 730. Actual history is institution-dependent and may be shorter.
- After Transactions initialization, changing `days_requested` on sync does not expand the initial history request. Recreating Items consumes Trial slots and can disrupt existing Chase Items. Use CSV for missing history rather than casually relinking.
- Exchange `public_token` via `/item/public_token/exchange`, encrypt/persist the resulting access token, discover/map accounts, then begin `/transactions/sync` with no cursor.
- There is no public webhook in this app. Omit the webhook parameter; poll sync/update status instead. Link API field optionality supports this design.
- Keep one **Item-wide** cursor, no `options.account_id` filter in v1. Account-specific streams require separate cursors; do not accidentally reuse an Item cursor for one account. Discard unselected accounts from local ingestion while maintaining the Item-wide cursor; newly selected accounts need a deliberate full replay/reconciliation from null cursor (same Item, not a new Item), using source uniqueness to avoid duplication.
- `count=500` can reduce pagination calls. Request original description if needed for regex; explicitly choose supported PFC taxonomy version (new integrations use v2), retaining returned primary/detailed/confidence hints.

## 4. What Transactions actually returns

Illustrative **synthetic, shortened** `/transactions/sync` response; real responses contain additional fields and nullable values:

```json
{
  "accounts": [
    {"account_id": "example-chase-card", "name": "Chase Card", "mask": "1234", "type": "credit", "subtype": "credit card"},
    {"account_id": "example-chase-checking", "name": "Chase Checking", "mask": "5678", "type": "depository", "subtype": "checking"}
  ],
  "added": [
    {
      "transaction_id": "example-purchase", "account_id": "example-chase-card",
      "amount": 45.99, "iso_currency_code": "USD",
      "name": "EXAMPLE MARKET 123", "merchant_name": "Example Market",
      "date": "2026-10-03", "authorized_date": "2026-09-30",
      "pending": false, "pending_transaction_id": "example-pending-purchase",
      "personal_finance_category": {
        "primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_GROCERIES", "confidence_level": "HIGH"
      }
    },
    {
      "transaction_id": "example-paycheck", "account_id": "example-chase-checking",
      "amount": -3000.00, "iso_currency_code": "USD",
      "name": "EXAMPLE EMPLOYER PAYROLL", "merchant_name": null,
      "date": "2026-09-30", "authorized_date": null,
      "pending": false, "pending_transaction_id": null,
      "personal_finance_category": {
        "primary": "INCOME", "detailed": "INCOME_WAGES", "confidence_level": "HIGH"
      }
    }
  ],
  "modified": [],
  "removed": [{"account_id": "example-chase-card", "transaction_id": "example-pending-purchase"}],
  "next_cursor": "opaque-example-cursor", "has_more": false,
  "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE", "request_id": "example-request"
}
```

The category names are illustrative; use the actually returned selected taxonomy, not these strings as permanent hard-coded assumptions.

| Plaid field | Clonarch treatment |
|---|---|
| `transaction_id`, `account_id` | Stable source keys within mapped Item/account identity; IDs can change on reconnect, so do not assume identity across relinks. |
| `amount` | Positive = outflow; negative = inflow, including deposits/refunds/card payments. Parse raw JSON numerics as Decimal before conversion; internal amount = `-amount * 100`, checked for exact cents. SDKs that parse through float must not be trusted for money; use a lossless JSON path. |
| `iso_currency_code` / unofficial currency | Accept USD only; null/non-USD becomes explicit review/rejection, never assumed USD silently. |
| `authorized_date` | Preferred purchase date when present for expenses/refunds. Purchase date is not guaranteed for every institution/transaction. |
| `date` | Pending occurrence date or posted settlement date. For posted expense/refund with missing authorized date, use this fallback and show its provenance; income uses posted deposit date. |
| `name`, `merchant_name`, optional `original_description` | Preserve source descriptions, normalize separately for matching. Merchant can be null, especially payroll/transfers. |
| `personal_finance_category` | Starting hints only; includes primary/detailed/confidence. Does not know household-specific regular/exceptional intent. Rules/manual edits prevail. |
| `pending`, `pending_transaction_id` | Pending displayed separately; posted ID can replace removed pending ID across different pages in the same overall update. Reconcile the entire staged update before marking canonical rows removed. |
| `modified`, `removed` | Posted records can change/disappear. Apply idempotently, retaining overrides/audit and source aliases. |
| `next_cursor`, `has_more` | Page all updates; commit data+cursor atomically. Restart full page loop from original cursor on pagination mutation/failure. |
| `transactions_update_status` | Poll `NOT_READY`, `INITIAL_UPDATE_COMPLETE`, `HISTORICAL_UPDATE_COMPLETE` without a public webhook. Empty first sync is not proof that history is empty or complete. |

Institution history and optional fields must be validated after first real Link. Never make a complete coverage claim just because historical fetch finished.

## 5. LAN-only OAuth feasibility

Official OAuth docs establish a useful path that the first plan did not yet know:

- Normal desktop/mobile **web** OAuth can work **without setting `redirect_uri`**, using a popup/new tab. First implementation should test this in standalone iPad Safari (not an embedded browser launched inside another app), with popups allowed and the original tab retained.
- If a redirect URI is supplied, it **must use HTTPS**; HTTP localhost exception is Sandbox-only. Do not register a private `http://192.168.105.10:...` callback as if production accepts it.
- Embedded webviews need redirect/resume support; do not promise that Termius's embedded browser or every bank-app return flow works with popup-only Link.
- No-redirect web flow removes a presumed public-callback requirement, but actual private-IP HTTP origin, Safari cross-tab behavior and institution consent still need a real test. An HTTPS callback, if later needed, requires a separate LAN-compatible certificate/URI decision; do not expose a public listener/tunnel.
- SameSite=Strict session cookies may not be sent on a cross-site OAuth return navigation. A redirect-mode landing GET must be nonmutating, render the SPA without requiring that cookie on the initial navigation, and bind the stored Link session once the same-origin app resumes. Never weaken mutation CSRF checks or put access tokens in URLs to fix return behavior.

## 6. JEX classification using the owner's Codex account

Owner calls the classification piece **JEX** and permits remote classification via the existing Codex account. Treat JEX as the module name unless a separate product is later specified; do not install an unrelated package named JEX.

Official sources checked:
- [Codex authentication](https://developers.openai.com/codex/auth/) (currently redirects to OpenAI's learn.chatgpt.com documentation).
- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive/) (same official documentation redirect).

Findings and proposed adapter:
- Official CLI supports ChatGPT subscription sign-in and `codex exec` automation with saved authentication; structured outputs via `--output-schema`, ephemeral runs via `--ephemeral`. Documentation describes ChatGPT-managed automation as advanced; API keys are the simpler general automation default.
- A Codex subscription is **not** a general OpenAI API key or included API billing balance. Do not extract this agent's OAuth/session tokens or call undocumented subscription backend endpoints from Clonarch.
- Codex CLI 0.165.0 is installed project-locally under `.tools/codex`; its PATH is not changed. Owner login is still separate and has not occurred; any auth must use a dedicated private directory. Installed version flags/permissions and subscription eligibility/limits must be verified before implementing the adapter.
- Subscription usage consumes the same plan limits as the owner's coding work. Batch repeated merchants, cache by source/taxonomy/prompt fingerprint, enforce bounded batches/timeouts, and pause on quota/reauth errors. Never fall back silently to billable API usage.
- Do **not** run a general coding agent with access to the financial database, Plaid secrets, home directory, shell/network tools or repository plugins just to classify merchant text. Read-only mode alone is insufficient (it can still read secrets).
- Gate enablement on demonstrated **tool-free** CLI configuration (if supported by installed version) plus OS-enforced isolated scratch filesystem/process environment. No mounted project/home/ledger/Plaid config, no MCP/plugins, no exec/web tools; only approved minimized stdin payload and existing category IDs. Isolate the one CLI auth store needed for outbound inference. If effective isolation/tool disabling cannot be established with approved installed tooling, keep adapter blocked and offer manual/rules or an explicitly approved separate API-key adapter instead. No container runtime gets installed without approval.
- Prompt injection is possible in transaction text. Validate schema/taxonomy/confidence server-side and accept only suggestions; model output can never invoke commands or change rules automatically.
- Treat the CLI's own login cache as a secret with filesystem permissions; it is not a Clonarch DB encryption field and is never returned by browser APIs or copied into source control. No auth secrets in this chat.

## 7. Environment observed (read-only)

Current VM interface `ens18`: **192.168.105.10/24**; no global IPv6 address observed, only loopback/link-local. This does not verify router/proxy/firewall exposure. Existing listeners were inspected but not altered. Proposed Clonarch port **8787**, apparently unused at inspection; recheck immediately before startup.

Initial inspection: system Python **3.11.2**, Node **22.23.3**, npm **10.9.9**, curl. System/path uv and Codex CLI were absent; Python pip/ensurepip and app packages absent. Since owner approved, project-local uv and managed Python 3.12.16 now live under `.tools`, backend apps under `backend/.venv`, frontend packages under `frontend/node_modules`, Codex CLI 0.165.0 under `.tools/codex`. System runtimes and shell startup unchanged; no Codex auth/login or Plaid credentials.
