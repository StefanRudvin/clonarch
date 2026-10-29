#!/usr/bin/env python3
"""Export rules and their category definitions privately; never uploads data."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.umask(0o077)
    destination = ROOT / 'var' / 'backups'
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(f'{(ROOT / "var/clonarch.sqlite3").as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        rules = [dict(row) for row in db.execute('SELECT * FROM rules ORDER BY priority, id')]
        categories = [dict(row) for row in db.execute(
            'SELECT * FROM categories WHERE id IN (SELECT category_id FROM rules) ORDER BY id')]
    now = datetime.now(timezone.utc)
    payload = {'format': 'clonarch-rules', 'version': 1, 'exported_at': now.isoformat(),
               'rules': rules, 'categories': categories}
    path = destination / f'rules-{now.strftime("%Y%m%dT%H%M%S%fZ")}.json'
    with path.open('x', encoding='utf-8') as output:
        json.dump(payload, output, indent=2, ensure_ascii=False)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    restored = json.loads(path.read_text())
    assert restored == payload, 'Backup verification failed'
    print(f'Verified {len(rules)} rules and {len(categories)} referenced categories: {path}')


if __name__ == '__main__':
    main()
