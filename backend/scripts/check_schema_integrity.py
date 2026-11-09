#!/usr/bin/env python3
"""Reject repeated CREATE TABLE targets across the ordered SQL migration set.

This is a deliberately conservative guard for this repository's plain SQL
migration style. It strips SQL comments, recognises optional IF NOT EXISTS and
schema-qualified identifiers, and treats unqualified names as public (the
application migration search_path). It does not attempt to parse arbitrary
dynamic SQL; migrations must not construct DDL dynamically.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

CREATE_TABLE = re.compile(
    r"""\bCREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+
        (?:IF\s+NOT\s+EXISTS\s+)?
        (?:(?P<schema>"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)\s*\.\s*)?
        (?P<table>"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)""",
    re.IGNORECASE | re.VERBOSE,
)


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\r\n]*", " ", sql)


def main() -> int:
    schema_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/schema")
    files = sorted(schema_dir.glob("*.sql"))
    targets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in files:
        sql = strip_comments(path.read_text(encoding="utf-8"))
        for match in CREATE_TABLE.finditer(sql):
            schema = (match.group("schema") or "public").strip('"').lower()
            table = match.group("table").strip('"').lower()
            targets[(schema, table)].append(path.name)

    duplicates = {key: names for key, names in targets.items() if len(names) > 1}
    if duplicates:
        print("ERROR: a table may be declared by CREATE TABLE only once across migrations.")
        for (schema, table), names in sorted(duplicates.items()):
            print(f"  {schema}.{table}: {', '.join(names)}")
        return 1
    print(f"OK: {len(files)} SQL files scanned; no repeated CREATE TABLE targets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
