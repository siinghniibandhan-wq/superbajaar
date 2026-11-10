import pytest

from app.services.accounting_posting import resolve_legal_entity_code


def test_assigned_establishment_code_scopes_accounting_mapping():
    assert resolve_legal_entity_code("SB-BR") == "SB-BR"


def test_unassigned_location_uses_explicit_default_mapping_scope():
    assert resolve_legal_entity_code(None) == "DEFAULT"


def test_blank_establishment_code_fails_closed_to_default_scope():
    assert resolve_legal_entity_code("   ") == "DEFAULT"


def test_non_string_establishment_code_is_rejected():
    with pytest.raises(ValueError, match="must be a string"):
        resolve_legal_entity_code(123)
