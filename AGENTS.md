# Instructions for AI coding agents (ChatGPT, Claude, Copilot, Codex and others)

STOP. Before ANY change that involves the database, tables, data, migrations, deploy, backups, login, customers, orders, payments or loyalty:

1. Read `docs/DATABASE_CHANGE_RULES.md` completely, and the safety section of `README.md`.
2. Begin your first reply with: "I have read docs/DATABASE_CHANGE_RULES.md" and name the section numbers you are relying on. If you cannot read it, stop and tell the owner.

## Database Governance

**Repository Owner:** Repository Owner  
**Database Owner:** Repository Owner

**Primary Reviewer:** Claude (when available)  
**Secondary Reviewer:** ChatGPT

The Database Owner retains final authority over:
- schema design
- migration numbering
- migration approval
- production database changes
- release approval

Reviewers provide implementation guidance and safety review but do not replace owner approval.

Unless the owner explicitly approves otherwise, database-impacting work must be reviewed before merge.

The following restrictions apply unless the owner explicitly approves the exact scoped change in the pull request.

Protected assets:
- `backend/schema/`
- `backend/schema_required.txt`
- `backend/scripts/apply_schema.sh`
- migration runner, backup and deployment scripts

Never push directly to `main`.
Never deploy to production.
Never claim a build, migration, deployment or test passed unless it was actually executed and verified.

You may write application code (backend and frontend) and tests on a new branch from `main`, with a pull request. If you are not the Database Owner and a database change is needed, do not write SQL or modify protected assets. Complete the "Database Change Request" in section 9 of the rules file and give it to the owner for approval and assignment.

If you are missing information, ask the owner instead of guessing.
