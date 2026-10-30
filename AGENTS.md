# Instructions for AI coding agents (ChatGPT, Codex, and others)

STOP. Before ANY change that involves the database, tables, data, migrations, deploy, backups, login, customers, orders, payments or loyalty:

1. Read `docs/DATABASE_CHANGE_RULES.md` completely, and the safety section of `README.md`.
2. Begin your first reply with: "I have read docs/DATABASE_CHANGE_RULES.md" and name the section numbers you are relying on. If you cannot read it, stop and tell the owner.

The following restrictions apply unless the owner explicitly approves the exact scoped change in the pull request. You must NOT write or edit:
- anything in `backend/schema/`
- `backend/schema_required.txt`
- `backend/scripts/apply_schema.sh` or any backup, migration or deploy script
- SQL that changes structure or existing data

Claude writes all of that. If you need such a change, fill in the "Database Change Request" from section 9 of the rules file and hand it to the owner.

You may write application code (backend and frontend) and tests, on a new branch from `main`, with a pull request. Never push to `main`. Never deploy to test. Never claim a test, build or deploy passed unless you ran it and saw the result. If you are missing information, ask the owner instead of guessing.