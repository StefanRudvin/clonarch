# Rules recovery snapshot

`rules.json` contains all rules (including disabled rules) and their referenced category definitions, exported from a consistent read-only database snapshot. It does not include transactions, accounts, or provider credentials. Rule names and patterns may contain merchant/description text; the owner explicitly approved storing these in this private GitHub repository on 2026-10-29.

Snapshot: **260 rules, 25 categories**, exported 2026-10-29. This is a manual point-in-time backup, not continuous protection. Subsequent rule changes are not automatically uploaded.

## Refresh

From the project root, using existing installed tools:

```sh
backend/.venv/bin/python scripts/backup-rules.py
```

The command writes a new mode-0600 JSON snapshot under ignored `var/backups/`, verifies JSON round-trip equality, and prints the path/counts. Review that snapshot and copy it to `backups/rules.json`, then commit/push only the intended backup changes. Do not add the live database, secrets, or the whole `var/` directory to git.

## Recovery

Keep this repository accessible independently of the VM. After a VM/database failure, clone or retrieve the repository and recover `backups/rules.json`. Older committed snapshots are also available through Git history.

The JSON format (`clonarch-rules`, version 1) preserves rule IDs, names, patterns, category IDs, spend types, kinds, priorities, enabled flags, and referenced category definitions. Recovery must map or recreate categories before inserting rules and preserve priorities and enabled flags. Take a consistent backup of any existing database and stop the app before direct database restoration. Do not blindly replace populated category/rule tables or overwrite existing IDs.

There is not yet an automated restore command. JSON integrity and category references have been checked; an end-to-end restore has not been tested. This snapshot cannot restore transaction history or Plaid credentials.
