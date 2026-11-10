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


---

## Post-verification operational recheck — 10 November 2026, 13:04 UTC

The earlier successful migration and restore-test results above are historical verification results. A later live EC2 recheck found that the currently installed automation services are **not healthy**. This addendum supersedes the earlier statement that the current timer/service configuration is verified and healthy.

### Current observations from EC2

| Component | Observed result |
|---|---|
| `superbajaar-schema.timer` | Enabled and active; scheduled every 2 minutes |
| `superbajaar-github-sync.timer` | Enabled and active |
| Schema service | Fails with exit code 20 |
| GitHub sync service | Fails with exit code 1 |
| Schema database connectivity | Successful queries against `superbajaar` |
| Schema runner report | `missing_required=000_baseline_schema.sql` |
| Git fetch | Fails because the service cannot write to `.git/objects` |

### Schema service configuration drift

The base unit contains an `ExecStart` ending in `--status`, but the active drop-in at `/etc/systemd/system/superbajaar-schema.service.d/override.conf` clears and replaces that command without `--status`. The effective service therefore invokes the runner in its default apply mode. The runner currently reports no new files to apply, then blocks with exit code 20 because the required baseline is not considered applied.

Restore the status-only argument in the effective systemd command before treating the timer as a read-only monitor. Do not execute the runner in apply mode as a workaround.

### Baseline ledger discrepancy

The required manifest includes `000_baseline_schema.sql`. The runner's current output says that this required migration is not applied. The earlier production record states that 30 migrations were successfully applied, including the baseline. The cause of this discrepancy has **not yet been established**: the live ledger row, its stored SHA-256, the current file SHA-256 and the preserved baseline backup must be compared. Do not replay the baseline, fabricate a ledger entry, or overwrite its checksum until the database owner has reconciled the historical file and actual schema.

### GitHub sync filesystem failure

The sync service fails during `git fetch` with:

```text
error: insufficient permission for adding an object to repository database .git/objects
fatal: failed to write object
fatal: unpack-objects failed
```

This establishes a repository filesystem write-permission problem for the service execution identity. The exact ownership/permission correction must be based on the unit's configured user and the repository's current ownership; do not apply broad recursive permission changes blindly.

### Current disposition

- Timers are scheduled and active, but both triggered services are failing.
- No claim is made that current GitHub synchronization or schema status automation is healthy.
- The baseline discrepancy remains unresolved pending read-only ledger/checksum inspection.
- No production migration replay, ledger mutation, or broad ownership change is authorized by this record.
- Re-verify both services and the database status after corrections before marking automation operational.
