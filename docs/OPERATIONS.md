# Operations, privacy and deployment boundaries

## 1. Current state and approvals

Owner confirmed **this VM** and approved project-local installations plus startup. The running app is at `http://192.168.105.10:8787`; current code/dependencies/data are in this project. Installed scope and paths are recorded in [INSTALLATION_PROPOSAL.md](INSTALLATION_PROPOSAL.md). No system Python/Node/global package or shell startup changes. No firewall edits, boot units, router changes or public listeners.

Still separate approvals/conditions:
1. **Added installations/upgrades:** ask before adding tools/dependencies outside the exact approved project-local list. A later Codex login is performed by the owner; no token collection in chat.
2. **Execution/integration:** live Plaid/Codex calls and sending real merchant data need integration readiness/secure config; owner intends Plaid authorization later. No actual provider calls have been made.
3. **Additional deployment/network changes:** reboot-persistent service, firewall/router, and access changes beyond the present explicitly bound listener require scoped authorization.
4. **Backup:** destination, schedule/retention and encryption-key recovery location. No backups configured.

The ordinary Clonarch process is running as user rudi, bound explicitly to `192.168.105.10:8787`. Start/stop commands are in IMPLEMENTATION_STATUS.md.

## 2. What LAN-only means

Owner accepts choosing a web listening port on this VM. The unprivileged private-interface listener is `http://192.168.105.10:8787`, verified locally, with **no public ingress/forwarding configured by this change**. Keep no-public-exposure constraint; do not keep re-asking about ordinary local port selection. Actual LAN/VLAN/VPN routing and existing proxy/forwarding exposure remain unverified, so do not claim the private address alone guarantees isolation.

- Never bind to wildcard `0.0.0.0` or `[::]` silently. Default dev configuration is loopback only; production requires explicit private bind IP and Host/Origin allowlist.
- No router port forwarding, NAT changes, UPnP, tunnels, Cloudflare/Tailscale Funnel, public reverse proxies, publicly reachable webhooks or public DNS dependence.
- No “temporary” public dev server. Any approved frontend dev server remains loopback-only, never the household deployment.
- Verify IPv6 independently. A private IPv4 listener and lack of NAT forwarding do not prove no exposure through other interfaces, globally routed IPv6 or an existing proxy.
- Confirm trusted subnet: guest/IoT VLANs should not reach this app. A VPN route may grant access even though the IP is private; decide explicitly.
- Host firewall allowlisting is recommended defense in depth but any edit requires approval and must not disrupt SSH. Preserve a rollback path; no blanket flushes.
- Do not automatically touch Proxmox, home router, Home Assistant, ARR or other VMs/services.

Plaid and any enabled remote LLM need **outbound HTTPS internet access**; LAN-only means no public inbound access, not an air gap. Browser Plaid Link may load third-party scripts and bank pages. Confirm the owner accepts those outbound flows. There is no general outbound internet or public content fetcher exposed in the API.

## 3. No initial login: residual risks and protections

Anyone who can reach the approved listener can read/change data. CSRF protection does not authenticate household members or stop a malicious LAN client. No-password mode is appropriate only on a genuinely trusted network; add authentication before broadening network access.

Even a public website opened in a trusted browser must not be able to drive local mutations:

- Exact server Host allowlist including configured IP/port; no arbitrary forwarded-host trust. Avoid DNS rebinding.
- Exact current-origin allowlist; no wildcard CORS, foreign-origin mutations, or permissive credentialed cross-origin access.
- Opaque browser session cookie (HttpOnly, SameSite=Strict, narrow path, Secure when HTTPS), synchronizer CSRF token in `X-CSRF-Token`, JSON content type for non-upload mutations, and exact Origin check on every unsafe method. Tokens/session state expire and are rotated; strict Origin still applies if a token is valid.
- Reject explicit cross-site fetches where appropriate, but do not rely only on browser Private Network Access behavior.
- Financial reads and `/context` use `Cache-Control: no-store`; reject foreign Origin when supplied. No scriptable JSONP or credential values in URLs.
- Safe CSV uploads; input/output length bounds; no user-supplied executable filters, arbitrary provider URLs or local paths.
- Content Security Policy, clickjacking protection, no-referrer and MIME protections; Plaid's required script/frame/network allowances must be based on current official documentation and explicitly enumerated, not wildcarded until it works.
- No external analytics, crash reporter or browser persistent storage of financial datasets/tokens. Query-cache memory only; clear on reload/session expiry.

Direct-IP HTTP sends financial data unencrypted over the LAN. Private HTTPS is preferable if feasible; a local CA introduces iPad trust work and separate tooling approval. Current official Plaid docs allow ordinary web popup OAuth without redirect_uri: test standalone Safari first rather than assume a public HTTPS callback is required. If supplying a production redirect URI, HTTPS is mandatory (HTTP localhost exception only Sandbox); never register the private HTTP URL as a valid production redirect. Actual private-origin Safari flow still needs testing. Redirect-mode cross-site landing GET must not assume a SameSite=Strict cookie is sent; resume server-bound state only after same-origin app navigation without weakening CSRF. No public endpoint/domain/tunnel workaround. See INTEGRATIONS.md.

## 4. Secret and data storage

Proposed runtime layout (configurable, outside publicly served directories):

```text
<private-data-dir>/
  clonarch.sqlite3
  staging/
  backups/          # only if local destination approved; private mode
<private-config-dir>/
  config.env        # placeholders in source control, real file not tracked
  encryption.key    # separate from DB/backups; restrictive permissions
```

- Process runs as an unprivileged account; data dirs mode 0700 and secret files 0600. Do not recursively change ownership/permissions on unrelated directories.
- Encrypt Plaid access tokens and provider secrets using a reviewed authenticated-encryption library (proposed cryptography/Fernet); never custom crypto. Key provisioned outside git/DB, with key version and rotation procedure. Encryption protects stolen DB files, not a fully compromised running host.
- Provider keys/credentials are server provisioned. No frontend readback. Plaid public/link tokens are short-lived and redacted too. Owner will provide authorization later; do not solicit secrets in chat.
- JEX uses a proposed official Codex CLI subscription adapter, not agent-token extraction or generic API billing. CLI auth directory is a dedicated protected secret store, outside git and inaccessible to browser APIs. Classification subprocess must have demonstrated tool-free configuration plus OS-enforced filesystem/environment isolation from ledger/home/Plaid; otherwise adapter stays off. No automatic inference on install/login.
- Full card numbers, bank passwords and account routing details are not needed and must not be collected.
- Raw source payloads retain only needed transaction fields. Real statements, CSVs, database/WAL/SHM, exports, backups, `.env`, keys and logs are gitignored.
- Logs include request/job IDs, counts/timing and safe error codes, not transaction descriptions, filenames, notes, tokens, complete provider responses or amounts by default. Disable framework request-body logging.
- No deletion/retention policy runs without documented scope. Proposed staging expiry 7 days (uncommitted work), previews 30 minutes, idempotency 30 days; audit/source identity retained for financial reproducibility, with explicit owner data-erasure process later. A successful import can delete its staged CSV earlier once durable rows/provenance are safe.

## 5. Worker and scheduling

- One worker initially, durable DB queue, lease-based claims with renewal and expiry. External calls are outside write transactions.
- Per-Item sync lease plus generation check. Retry only safe operations; atomically apply data/cursor. A killed process resumes/retries without duplicate financial writes.
- Scheduler runs once, generates deduplicated jobs, and handles clock skew/restarts. Poll initial transactions_update_status with bounded backoff, then proposed sync every six hours with jitter after dashboard/quotas reviewed; omit public webhook. Trial currently includes Refresh, but no Refresh/add-on calls until explicitly enabled.
- Protect Trial's 10 lifetime Production Item slots: Sandbox development only; never delete/recreate Items casually. Set initial history=365 days, reuse update mode and safe null-cursor same-Item replays for newly selected accounts.
- Failed jobs surface in UI; terminal errors do not retry forever. Manual requeue is an explicit new idempotent operation where supported, not a direct DB edit.
- Disconnect prevents new sync immediately; remote revoke is visible/retryable. Backups must not re-enable a revoked Item automatically on restore.

## 6. Backups and restoration

Proposed after approval: daily encrypted consistent backups, seven daily plus four weekly copies, to a confirmed private destination outside the VM's single failure domain when available. Final retention is owner's decision.

- Use SQLite online backup API or a coordinated snapshot procedure. Do not copy just the active `.sqlite3` while ignoring its WAL.
- Backup data and config necessary for recovery; retain the encryption key separately with a secure recovery path. Encrypt whole backups as well as token fields. No key in the same uploaded archive as the backup.
- Record schema/application version and checksum. Check backup completion and retention; report failures.
- Restore test to isolated path with scheduler and all provider calls disabled. Verify migrations, row counts and known monthly totals.
- Before resuming sync after a real restore, reconcile cursor/source identities and inspect connection revocation state; restored tokens might be obsolete. Make no automatic external calls merely because a restored DB contains an active Item.
- Document actual restore commands only after tooling/paths exist. Do not claim recovery without testing.

## 7. Updates and rollout

- Dependency upgrades require new explicit approval; lock versions and record changes.
- Validate against synthetic data and a safe restored copy; take a consistent backup before migration. Stop writes/worker for schema changes as appropriate.
- Backward-compatibility or backup restore is the rollback plan; never blindly downgrade a database after irreversible migration.
- Keep API and frontend assets version aligned. Do not overwrite runtime data during deployment.
- Running automatic external package updates or provisioning a new system service is not part of this plan's authorization.

## 8. Deployment acceptance record to fill in later

- Target: owner confirmed current VM. Observed ens18 192.168.105.10/24; loopback/link-local IPv6 only at inspection; routing/firewall still unverified.
- Listener: owner permits port selection; proposed HTTP 192.168.105.10:8787. Not started. No wildcard/IPv6/public listener or network config changes.
- Relevant existing proxies/port forwards verified:
- Software install approval (packages, paths, date):
- Service/startup/firewall approval and rollback:
- Plaid environment / production entitlement / cost verification date:
- AI provider/data/budget approval (if any):
- Data/config/key paths and permissions verified:
- Backup destination / retention / separate key recovery:
- Allowed-client and denied-segment reachability results:
- WAN/IPv6 exposure checks and any limits on verification:
- Last backup restore / migration / household-flow tests:
