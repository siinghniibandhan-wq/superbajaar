## Verification record: 2026-11-10 (append to SQL_SCHEMA_AUTOMATOR_FINDINGS.md)

Server: EC2 `i-08814a9225c19ee91` (t3.small, Ubuntu 26.04, PostgreSQL 18.6), us-east-1.
Production database: `superbajaar`, owner `superbajaar_app`. `sb_app` does not exist on this server.
Every command below sets `SB_DB=superbajaar` explicitly. The runner default (`sb_app`) is never used.

### COMPLETED AND VERIFIED

| Item | Evidence |
|---|---|
| Database was empty before migration | 0 tables in `public`, only the `public` schema |
| Baseline applies on PostgreSQL 18 | 29 tables, no extensions, no DROP/TRUNCATE/DELETE |
| Baseline statement count | 29 real `CREATE TABLE` statements, 29 unique names. The 4 other grep matches are comments |
| All 30 files rehearsed on a throwaway database | exit 0, 30 applied, 0 failures, 118 tables |
| Production migration | exit 0, 30 applied, 0 failures, 118 tables |
| Table ownership | all 118 tables owned by `superbajaar_app` (see Ownership fix below) |
| Pre-migration backup | `superbajaar-pre-migration-20261110T104754Z.dump` in `/var/lib/superbajaar/backups` |
| Backup integrity | `pg_restore --list` reads the dump (1,146 entries) |
| Restore test | restored into a temporary database: exit 0, 118 tables. Temporary database removed |
| No-pending run is harmless | exit 0, "no new files to apply", no new backup |
| Failure handling | bad file rolled back and logged in `schema_migration_failures`; earlier file stayed applied; exit 10 |
| Required-file blocking | manifest requiring a failed file: exit 20, "deploy blocked" |
| Required files applied, other file failed | exit 11 |
| Concurrency lock | second run while one was active: exit 60 (hit twice, by accident, against the timer) |
| Setup error reporting | database owned by `postgres` instead of `superbajaar_app`: exit 50, nothing applied |
| Timer fires on its own | fired at 10:49:22 and 10:50:06 without manual action; `systemctl --failed` showed 0 units |
| Backend stayed healthy | `superbajaar-backend` active, HTTP 200 on `127.0.0.1:8001/` after migration |

### Ownership fix (important)

The runner defaults to `sudo -n -u postgres psql`, so tables were created owned by `postgres` and `superbajaar_app` had no access (`has_table_privilege` returned false).

Fix, with no change to the runner script: `/usr/local/bin/sb-psql` (mode 755):

```bash
#!/bin/bash
exec sudo -n -u postgres env PGOPTIONS="-c role=superbajaar_app" psql "$@"
```

Pass it with `SB_PSQL=/usr/local/bin/sb-psql`. Re-test result: 118 tables owned by `superbajaar_app`, `has_table_privilege` true. This wrapper lives only on the server, not in the repository.

### Paths and identity

| Setting | Value |
|---|---|
| Backup directory | `/var/lib/superbajaar/backups` (ubuntu:ubuntu, 750) |
| Log file | `/var/log/superbajaar/schema.log` (directory ubuntu:ubuntu, 750) |
| Schema directory | `/opt/superbajaar/source/backend/schema` |
| Manifest | `/opt/superbajaar/source/backend/schema_required.txt` |
| Service | `superbajaar-schema.service` (oneshot, user `ubuntu`, no `Restart=`) |
| Timer | `superbajaar-schema.timer`, `OnCalendar=*:0/2` (every 2 minutes) |
| Mode | `--status` only. The timer reports state and applies nothing |

The runner's default paths (`/home/ec2-user/...`) do not exist on this server, so they are overridden with `SB_BACKUP_DIR` and `SB_LOG`. The runner script was not edited.

### Operational commands

Status (read-only, exit 10 = pending, 0 = all applied):

```bash
cd /opt/superbajaar/source/backend
SB_PSQL=/usr/local/bin/sb-psql SB_DB=superbajaar SB_BACKUP_DIR=/var/lib/superbajaar/backups \
SB_LOG=/var/log/superbajaar/schema.log bash scripts/apply_schema.sh \
/opt/superbajaar/source/backend/schema --status
```

Apply (manual, after review; takes a verified backup first): same command without `--status`.

Timer: `systemctl list-timers superbajaar-schema.timer`, `journalctl -u superbajaar-schema.service -n 50`, `systemctl --failed`.

Locking note: the lock is shared across all databases. A manual run that starts while the timer is running gets exit 60. Wait a few seconds and retry.

### Exit codes seen in testing

0 applied, nothing pending | 10 problem or pending | 11 required applied, other problem |
20 required file missing (release blocked) | 50 setup problem | 60 another run in progress.
Exit 30 (backup failure) was not triggered in testing.

### IMPLEMENTED BUT NOT VERIFIED

- Whether the backend's `DATABASE_URL` connects successfully to the new tables. The HTTP 200 may not touch the database. Run a real login or data request to confirm.
- The exact contents of each of the 30 files were not reviewed line by line. Only their ordered application on PostgreSQL 18 was tested. The baseline's `app_users.role` check does not list `super_admin`; confirm whether a later file or the application needs it.
- Restore was tested on a structure-only dump. Repeat once real data exists.

### NOT DONE

- Automatic application of new migrations by the timer (deliberately left manual).
- GitHub commit of this record and the findings update.
- `sb-psql` wrapper and the systemd units are not stored in the repository.
- Exit 30 (backup failure) simulation.

### Other changes made to the server during this work

`apt upgrade` and one reboot; swap file already present (1 GB); packages git, python3-venv, nginx, postgresql-client installed. After the reboot nginx, PostgreSQL and the backend all came back up.
