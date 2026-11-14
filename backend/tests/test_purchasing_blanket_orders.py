"""Regression guards for the additive blanket purchase-order workflow."""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _routes(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "router"
                    and decorator.args and isinstance(decorator.args[0], ast.Constant)):
                found.add((decorator.func.attr.upper(), decorator.args[0].value))
    return found


def test_blanket_order_routes_are_registered_once():
    routes = _routes(ROOT / "app/api/purchasing_blanket_orders.py")
    assert {
        ("GET", "/blanket-orders"),
        ("POST", "/blanket-orders"),
        ("GET", "/blanket-orders/{blanket_id}"),
        ("POST", "/blanket-orders/{blanket_id}/submit"),
        ("POST", "/blanket-orders/{blanket_id}/approve"),
        ("POST", "/blanket-orders/{blanket_id}/releases"),
    } <= routes
    assert len(routes) == len(set(routes))


def test_blanket_order_schema_is_required_and_registered():
    required = (ROOT / "schema_required.txt").read_text(encoding="utf-8")
    migration = (ROOT / "schema/046_purchasing_blanket_orders.sql").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "046_purchasing_blanket_orders.sql" in required
    for table in (
        "purchase_blanket_orders",
        "purchase_blanket_order_lines",
        "purchase_blanket_order_releases",
        "purchase_blanket_order_release_lines",
    ):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in migration
    assert "purchasing_blanket_orders_router" in main


def test_blanket_release_uses_standard_po_and_enforces_caps():
    source = (ROOT / "app/api/purchasing_blanket_orders.py").read_text(encoding="utf-8")
    assert "INSERT INTO purchase_orders" in source
    assert "INSERT INTO purchase_order_lines" in source
    assert "Release exceeds the remaining agreed quantity" in source
    assert "Release exceeds the remaining blanket contract value" in source
    assert "Only approved active blanket orders can be released" in source
