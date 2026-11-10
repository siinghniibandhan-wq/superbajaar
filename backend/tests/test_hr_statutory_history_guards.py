"""Database-level regression tests for HR statutory history guards.

These tests run only against the disposable SB_TEST_DATABASE_URL database
after the checked-in schema migrations have been applied by CI.
"""
import os
import uuid

import psycopg
import pytest

TEST_DB = os.environ.get("SB_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="SB_TEST_DATABASE_URL is not set")

if TEST_DB and ("sb_app" in TEST_DB or "amazonaws" in TEST_DB):
    raise RuntimeError("Refusing to run HR history guard tests against a production-like database")


def _expect_guard_rejection(conn, statement, params):
    # Nested transaction creates a savepoint so the expected trigger exception
    # does not abort the outer fixture transaction.
    with pytest.raises(psycopg.Error):
        with conn.transaction():
            conn.execute(statement, params)


def test_hr_statutory_history_guards_preserve_supported_workflows():
    suffix = uuid.uuid4().hex
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("BEGIN")
        try:
            actor_id = conn.execute(
                "INSERT INTO app_users(email,full_name,password_hash,role) "
                "VALUES(%s,%s,%s,'super_admin') RETURNING id",
                (f"hr-history-{suffix}@test.local", "HR History Test", "test-hash"),
            ).fetchone()[0]

            employee_id = conn.execute(
                "INSERT INTO hr_employees(employee_code,first_name,last_name,email,designation,joining_date) "
                "VALUES(%s,'History','Guard',%s,'Tester',DATE '2026-01-01') RETURNING id",
                (f"HR-HISTORY-{suffix}", f"hr-history-employee-{suffix}@test.local"),
            ).fetchone()[0]

            establishment_id = conn.execute(
                "INSERT INTO hr_establishments(code,legal_name,display_name,state_code) "
                "VALUES(%s,%s,%s,'KA') RETURNING id",
                (f"HR-HISTORY-{suffix}", "HR History Test Entity", "HR History Test"),
            ).fetchone()[0]

            policy_id = conn.execute(
                "INSERT INTO hr_statutory_policy_versions("
                "establishment_id,component,version_label,effective_from,policy_config,created_by_user_id"
                ") VALUES(%s,'pf','History guard test',DATE '2026-01-01','{}'::jsonb,%s) RETURNING id",
                (establishment_id, actor_id),
            ).fetchone()[0]

            run_ids = {}
            periods = {
                "draft": ("2026-01-01", "2026-01-31"),
                "calculated": ("2026-02-01", "2026-02-28"),
                "approved": ("2026-03-01", "2026-03-31"),
                "paid": ("2026-04-01", "2026-04-30"),
                "void": ("2026-05-01", "2026-05-31"),
            }
            for status, (start, end) in periods.items():
                run_ids[status] = conn.execute(
                    "INSERT INTO hr_payroll_runs(period_start,period_end,status,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s) RETURNING id",
                    (start, end, status, actor_id),
                ).fetchone()[0]

            snapshot_ids = {}
            for status, run_id in run_ids.items():
                snapshot_ids[status] = conn.execute(
                    "INSERT INTO hr_payroll_statutory_snapshots("
                    "payroll_run_id,employee_id,establishment_id,component,policy_version_id,"
                    "policy_snapshot,input_snapshot"
                    ") VALUES(%s,%s,%s,'pf',%s,'{}'::jsonb,'{}'::jsonb) RETURNING id",
                    (run_id, employee_id, establishment_id, policy_id),
                ).fetchone()[0]

            audit_id = conn.execute(
                "INSERT INTO hr_statutory_audit_events("
                "establishment_id,employee_id,event_type,reason,actor_user_id"
                ") VALUES(%s,%s,'history_guard_test','Original reason',%s) RETURNING id",
                (establishment_id, employee_id, actor_id),
            ).fetchone()[0]

            _expect_guard_rejection(
                conn,
                "UPDATE hr_payroll_statutory_snapshots SET employee_amount=1 WHERE id=%s",
                (snapshot_ids["draft"],),
            )
            _expect_guard_rejection(
                conn,
                "UPDATE hr_statutory_audit_events SET reason='tampered' WHERE id=%s",
                (audit_id,),
            )
            _expect_guard_rejection(
                conn,
                "DELETE FROM hr_statutory_audit_events WHERE id=%s",
                (audit_id,),
            )

            # Recalculation must still be able to replace snapshots for both
            # mutable payroll states.
            for status in ("draft", "calculated"):
                conn.execute(
                    "DELETE FROM hr_payroll_statutory_snapshots WHERE id=%s",
                    (snapshot_ids[status],),
                )
                assert conn.execute(
                    "SELECT count(*) FROM hr_payroll_statutory_snapshots WHERE id=%s",
                    (snapshot_ids[status],),
                ).fetchone()[0] == 0

            # Finalized/void snapshots are immutable and cannot be removed.
            for status in ("approved", "paid", "void"):
                _expect_guard_rejection(
                    conn,
                    "DELETE FROM hr_payroll_statutory_snapshots WHERE id=%s",
                    (snapshot_ids[status],),
                )
                assert conn.execute(
                    "SELECT count(*) FROM hr_payroll_statutory_snapshots WHERE id=%s",
                    (snapshot_ids[status],),
                ).fetchone()[0] == 1

            # Preserve the existing FK ON DELETE SET NULL actor-anonymisation
            # behaviour; only actor_user_id may be cleared by that FK action.
            conn.execute("DELETE FROM app_users WHERE id=%s", (actor_id,))
            assert conn.execute(
                "SELECT actor_user_id FROM hr_statutory_audit_events WHERE id=%s",
                (audit_id,),
            ).fetchone()[0] is None

        finally:
            # The fixture transaction is always rolled back; no rows survive.
            conn.execute("ROLLBACK")
