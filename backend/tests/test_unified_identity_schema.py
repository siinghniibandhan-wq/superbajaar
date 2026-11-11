from pathlib import Path


def test_unified_identity_foundation_defines_permanent_party_and_sbid():
    migration = Path(__file__).parents[1] / "schema" / "043_unified_identity_foundation.sql"
    assert migration.exists(), "Unified identity requires additive migration 043"
    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table if not exists public.identity_parties" in sql
    assert "sbid text not null unique" in sql
    assert "party_type" in sql
    assert "gen_random_uuid()" in sql
    assert "identity_party_sbid_immutable" in sql


def test_unified_identity_profiles_link_existing_domain_records_without_rekeying():
    migration = Path(__file__).parents[1] / "schema" / "043_unified_identity_foundation.sql"
    assert migration.exists()
    sql = migration.read_text(encoding="utf-8").lower()

    for table in (
        "identity_profiles",
        "identity_auth_accounts",
        "identity_contacts",
        "identity_relationships",
        "identity_link_requests",
        "identity_events",
        "identity_aliases",
    ):
        assert f"create table if not exists public.{table}" in sql

    for source in (
        "customer_account_id bigint",
        "crm_customer_id bigint",
        "employee_id bigint",
        "supplier_id bigint",
        "app_user_id bigint",
    ):
        assert source in sql

    assert "on delete restrict" in sql
    assert "identity_profile_customer_uidx" in sql
    assert "identity_profile_employee_uidx" in sql
    assert "identity_profile_supplier_uidx" in sql


def test_identity_contacts_allow_shared_contact_values_across_distinct_parties():
    migration = Path(__file__).parents[1] / "schema" / "043_unified_identity_foundation.sql"
    assert migration.exists()
    sql = migration.read_text(encoding="utf-8").lower()

    assert "identity_contact_party_value_uidx" in sql
    assert "unique (contact_type, normalized_value)" not in sql
    assert "identity_contact_party_value_uidx" in sql


def test_identity_audit_events_are_immutable_and_link_operations_are_idempotent():
    migration = Path(__file__).parents[1] / "schema" / "043_unified_identity_foundation.sql"
    assert migration.exists()
    sql = migration.read_text(encoding="utf-8").lower()

    assert "identity_events_immutable" in sql
    assert "identity_events_immutable_trigger" in sql
    assert "idempotency_key" in sql
    assert "identity_link_requests_idempotency_uidx" in sql
