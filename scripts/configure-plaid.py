#!/usr/bin/env python3
"""Securely save the owner's Plaid Trial Production credentials on this VM."""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_DIR = ROOT / ".secrets"
CONFIG_PATH = SECRET_DIR / "plaid.json"
KEY_PATH = SECRET_DIR / "plaid-fernet.key"


def main() -> None:
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        command = ROOT / "backend" / ".venv" / "bin" / "python"
        raise SystemExit(f"Project dependencies were not found in this interpreter. Run: {command} {Path(__file__).resolve()}") from exc
    SECRET_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SECRET_DIR, 0o700)
    if CONFIG_PATH.exists():
        if input("Plaid credentials already exist. Replace them? Type REPLACE to continue: ").strip() != "REPLACE":
            raise SystemExit("No changes made.")
    print("Enter the Plaid Production keys for your active free Trial plan. Input is not echoed.")
    client_id = getpass.getpass("Plaid client ID: ").strip()
    secret = getpass.getpass("Plaid Production secret: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", client_id):
        raise SystemExit("Client ID format was not accepted; no credentials saved.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,512}", secret):
        raise SystemExit("Secret format was not accepted; no credentials saved.")
    if input("Confirm these are Production credentials for your Plaid Trial. Type PRODUCTION: ").strip() != "PRODUCTION":
        raise SystemExit("No changes made.")
    if not KEY_PATH.exists():
        key_tmp = KEY_PATH.with_suffix(".key.tmp")
        key_tmp.write_bytes(Fernet.generate_key())
        os.chmod(key_tmp, 0o600)
        os.replace(key_tmp, KEY_PATH)
    config = {"client_id": client_id, "secret": secret, "environment": "production"}
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, separators=(",", ":")) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG_PATH)
    print("Plaid Production credentials saved locally with mode 0600. Values were not displayed.")
    print("Reload Clonarch in your browser; the running server reads this private config on demand.")


if __name__ == "__main__":
    main()
