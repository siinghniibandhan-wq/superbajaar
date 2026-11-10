"""Static route-registry guard for duplicate Purchasing endpoint declarations."""
import ast
from pathlib import Path


def _route_declarations(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    declarations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "router":
                continue
            if decorator.func.attr not in {"get", "post", "put", "patch", "delete"}:
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                declarations.append((decorator.func.attr.upper(), decorator.args[0].value, node.name))
    return declarations


def test_purchasing_requisition_routes_have_one_canonical_declaration():
    api_dir = Path(__file__).parents[1] / "app" / "api"
    declarations = (
        _route_declarations(api_dir / "purchasing.py")
        + _route_declarations(api_dir / "purchasing_lifecycle.py")
    )
    requisitions = [item for item in declarations if item[1].startswith("/requisitions")]
    signatures = [(method, path) for method, path, _ in requisitions]
    duplicates = sorted({signature for signature in signatures if signatures.count(signature) > 1})
    assert not duplicates, f"Duplicate Purchasing requisition routes shadow canonical handlers: {duplicates}"
    assert {("GET", "/requisitions"), ("POST", "/requisitions"),
            ("GET", "/requisitions/{requisition_id}"),
            ("POST", "/requisitions/{requisition_id}/submit"),
            ("POST", "/requisitions/{requisition_id}/decision")} <= set(signatures)
