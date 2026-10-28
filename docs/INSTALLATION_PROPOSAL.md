# Installation proposal — awaiting explicit confirmation

**Approved by owner 2026-10-27, installed project-locally.** Scope below records the approval and actual install paths.

## Proposed scope

Everything below is project-local under **`/home/rudi/clonarch`**, using existing Node 22/npm and downloadable official/package-registry distributions. Resolve tested compatible versions and write lockfiles; ordinary required transitive package dependencies are included. Do not update global/system tooling.

| Software | Proposed location | Purpose |
|---|---|---|
| uv executable | `.tools/bin/uv` | Local Python runtime/dependency management (not currently installed). |
| Managed Python 3.12 | `.tools/python/` | Modern supported project runtime; do not replace system Python 3.11. |
| FastAPI, Uvicorn, Pydantic v2 + pydantic-settings, SQLAlchemy 2, Alembic | `backend/.venv/` | HTTP API, validation, local SQLite persistence/migrations. SQLite itself comes with Python; no DB server installation. |
| httpx, python-multipart, cryptography, google-re2 | `backend/.venv/` | Lossless Plaid HTTP adapter, uploads, token encryption, safe regex. |
| pytest and pytest test-support packages as required by this stack | `backend/.venv/` | Unit/API/integration tests using synthetic data. |
| React, React DOM, React Router, TanStack Query | `frontend/node_modules/` | Responsive browser application. |
| TypeScript, Vite, React Vite plugin, OpenAPI TypeScript generator, Vitest, jsdom, Testing Library/react/user-event packages | `frontend/node_modules/` | Build, typed API client and frontend tests. No separate browser download included. |
| Official `@openai/codex` CLI | `.tools/codex/` (npm prefix) | Optional JEX subscription-inference feasibility check. If not approved, defer JEX; app/rules still work. |

Caches/download staging: `.cache/uv/`, `.cache/npm/`, `.cache/downloads/` with environment flags set per command, not shell startup changes. If packaging needs an unlisted OS/compiler/runtime package, stop and request additional approval; do not hide it in an install script. Do not download arbitrary remote shell installers into an execution pipe.

## Configuration and startup implications

- **No changes** to shell startup, PATH profiles, system Python/Node, apt packages, router, firewall, Proxmox, existing services, global npm installs or boot startup configuration.
- New project-local placeholders/config, lockfiles and gitignore only. App data proposed in `var/`, real secrets in private `.secrets/` (0700/0600); exclude tools, cache, auth and financial files from git.
- Codex login, if/when approved to use, is a separate owner-performed sign-in using a dedicated `CODEX_HOME=/home/rudi/clonarch/.secrets/codex`; creates local CLI authentication/config only, no shell startup changes. Never copy this agent's session tokens or request login tokens in chat. Installing the CLI does not authorize running classification or exposing its execution.
- Owner already requests app execution on this VM. After build/tests, start an ordinary process bound to **`192.168.105.10:8787`** (recheck port free), no wildcard/IPv6 bind or public forwarding. Report actual process/URL only after verified running. No automatic boot unit unless separately approved.
- No real Plaid credentials, bank access, paid API use or financial data transmission during dependency installation/testing. Plaid authorization and JEX data/limits setup happen later.
- Do not expose a general Codex terminal/command execution API. JEX enablement remains blocked until supported tool-free configuration and OS-enforced isolation are verified; any new isolation software requires another scoped approval.

## Approval and actual installation

Owner approved the listed scope on 2026-10-27, including optional Codex CLI. Installed under `/home/rudi/clonarch`: uv `.tools/bin`, Python 3.12.16 `.tools/python`, Python packages `backend/.venv`, Node packages `frontend/node_modules`, official Codex CLI `.tools/codex` (version 0.165.0). npm/Python lockfiles created. No system Python/Node, shell startup, global packages, firewall/router, boot service, or service manager changed. No Codex login, Plaid credentials or inference/data calls were made. The owner separately requested app execution on this VM; process is running as described in IMPLEMENTATION_STATUS.md.
