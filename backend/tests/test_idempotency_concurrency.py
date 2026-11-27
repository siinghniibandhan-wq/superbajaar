import os
import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from app.api.orders import _lock_checkout_idempotency_key


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not configured")
def test_postgres_serializes_concurrent_order_retries_for_the_same_key():
    dsn = os.environ["TEST_DATABASE_URL"]
    key = "integration-concurrent-checkout-key-001"
    with psycopg.connect(dsn) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_idempotency_concurrency_test (
                id bigserial PRIMARY KEY,
                idempotency_key text NOT NULL UNIQUE,
                payload_hash text NOT NULL
            )
            """
        )
        conn.execute(
            "DELETE FROM security_idempotency_concurrency_test WHERE idempotency_key=%s",
            (key,),
        )

    def attempt(payload_hash):
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                _lock_checkout_idempotency_key(conn, key)
                prior = conn.execute(
                    "SELECT payload_hash FROM security_idempotency_concurrency_test WHERE idempotency_key=%s",
                    (key,),
                ).fetchone()
                if prior:
                    return "replay" if prior[0] == payload_hash else "conflict"
                time.sleep(0.15)
                conn.execute(
                    "INSERT INTO security_idempotency_concurrency_test(idempotency_key,payload_hash) VALUES(%s,%s)",
                    (key, payload_hash),
                )
                return "created"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["same-payload", "same-payload"]))

    with psycopg.connect(dsn) as conn:
        count = conn.execute(
            "SELECT count(*) FROM security_idempotency_concurrency_test WHERE idempotency_key=%s",
            (key,),
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM security_idempotency_concurrency_test WHERE idempotency_key=%s",
            (key,),
        )

    assert sorted(results) == ["created", "replay"]
    assert count == 1
