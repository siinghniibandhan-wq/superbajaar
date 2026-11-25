"""State -> District -> PIN coverage, express coverage and product availability rules."""
import pytest

from app.services.serviceability import blocked_product_ids, location_serves


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("SB_PIN_LOOKUP_ONLINE", "0")


def row(**profile):
    return {"id": 1, "pin_code": "110001", "state": "Delhi", "region_code": None, "profile_data": profile}


DELHI = {"state": "Delhi", "district": "New Delhi"}
JHARKHAND = {"state": "Jharkhand", "district": "Palamu"}


def test_states_without_pins_serve_the_whole_state():
    r = row(service_states=["Delhi", "Jharkhand"])
    assert location_serves(r, "110001", DELHI)
    assert location_serves(r, "822123", JHARKHAND)
    assert not location_serves(r, "800001", {"state": "Bihar", "district": "Patna"})


def test_districts_narrow_the_state():
    r = row(service_states=["Jharkhand"], service_districts=["Ranchi"])
    assert not location_serves(r, "822123", JHARKHAND)
    assert location_serves(r, "834001", {"state": "Jharkhand", "district": "Ranchi"})


def test_pin_list_serves_only_those_pins():
    r = row(service_states=["Delhi"], service_pin_codes=["110001"])
    assert location_serves(r, "110001", DELHI)
    assert not location_serves(r, "110002", DELHI)


def test_unknown_region_only_matches_explicit_pins():
    assert not location_serves(row(service_states=["Delhi"]), "110001", None)
    assert location_serves(row(service_pin_codes=["110001"]), "110001", None)


def test_warehouse_without_coverage_falls_back_to_its_own_state():
    assert location_serves(row(), "110005", DELHI)


def test_express_needs_switch_and_subset_of_standard():
    base = dict(service_states=["Delhi", "Jharkhand"])
    assert not location_serves(row(**base), "110001", DELHI, express=True)
    on = row(express_enabled=True, **base)
    assert location_serves(on, "822123", JHARKHAND, express=True)  # no express area => whole standard area
    narrow = row(express_enabled=True, express_states=["Delhi"], **base)
    assert location_serves(narrow, "110001", DELHI, express=True)
    assert not location_serves(narrow, "822123", JHARKHAND, express=True)
    assert location_serves(narrow, "822123", JHARKHAND, express=False)


class _Rules:
    def __init__(self, rules):
        self.rules = rules

    def execute(self, query, params=None):
        outer = self

        class R:
            def fetchall(self):
                return outer.rules

        return R()


def rule(product_id, allowed=True, **scope):
    return {"product_id": product_id, "region_code": scope.get("region"), "pincode": scope.get("pin"),
            "location_id": scope.get("loc"), "is_allowed": allowed}


def test_product_allowed_only_in_listed_regions():
    conn = _Rules([rule(1, True, region="Delhi"), rule(2, False, region="Jharkhand"), rule(3, True, region="IN-JH")])
    locs = [{"id": 9, "region_code": None}]
    delhi = blocked_product_ids(conn, "110001", DELHI, locs)
    assert delhi == {3}  # allow-list for Jharkhand only
    jh = blocked_product_ids(conn, "822123", JHARKHAND, locs)
    assert jh == {1, 2}  # product 1 allowed only in Delhi; product 2 blocked in Jharkhand


def test_product_rule_by_warehouse():
    conn = _Rules([rule(1, True, loc=9)])
    assert blocked_product_ids(conn, "110001", DELHI, [{"id": 9, "region_code": None}]) == set()
    assert blocked_product_ids(conn, "110001", DELHI, [{"id": 4, "region_code": None}]) == {1}
