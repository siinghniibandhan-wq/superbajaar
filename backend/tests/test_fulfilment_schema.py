from pathlib import Path


def test_fulfilment_operations_migration_defines_persisted_pick_pack_and_dispatch_evidence():
    migration = Path(__file__).parents[1] / "schema" / "031_warehouse_fulfilment_operations.sql"
    assert migration.exists(), "Warehouse/Fulfilment requires additive migration 031"

    sql = migration.read_text(encoding="utf-8").lower()
    required = (
        "create table if not exists public.fulfilment_pick_tasks",
        "create table if not exists public.fulfilment_pick_task_lines",
        "create table if not exists public.fulfilment_packages",
        "create table if not exists public.fulfilment_package_lines",
        "create table if not exists public.fulfilment_dispatch_events",
        "create table if not exists public.fulfilment_dispatch_event_lines",
        "unique(shipment_id,dispatch_id)",
        "payload_hash",
        "on delete restrict",
    )
    for fragment in required:
        assert fragment in sql, f"Migration 031 is missing required invariant: {fragment}"


def test_fulfilment_return_records_separate_inspection_from_inventory_disposition():
    migration = Path(__file__).parents[1] / "schema" / "031_warehouse_fulfilment_operations.sql"
    assert migration.exists(), "Returns need persistent evidence before stock can be reallocated"

    sql = migration.read_text(encoding="utf-8").lower()
    assert "create table if not exists public.fulfilment_returns" in sql
    assert "create table if not exists public.fulfilment_return_lines" in sql
    assert "inspection_status" in sql
    assert "disposition" in sql
    assert "restock" in sql
    assert "write_off" in sql
