#!/usr/bin/env python3
"""Validate the GitHub Issue Forms template used for AI agent work packages."""

from pathlib import Path
import sys

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required: python -m pip install PyYAML") from exc

template_path = Path(".github/ISSUE_TEMPLATE/agent-work-task.yml")
workflow_path = Path(".github/workflows/agent-task-governance.yml")
path = template_path
data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

if not isinstance(data, dict):
    raise SystemExit("Issue template must be a YAML mapping.")

for key in ("name", "description", "title", "body"):
    if key not in data:
        raise SystemExit(f"Missing top-level key: {key}")

if not isinstance(data["body"], list) or not data["body"]:
    raise SystemExit("Template body must be a non-empty list.")

seen = set()
required_ids = {
    "task_type", "priority", "objective", "primary_agent", "fallback",
    "dependencies", "base", "allowed_paths", "protected_paths",
    "access_mode", "evidence", "acceptance", "verification", "output", "reviewer",
}
found = set()

for index, field in enumerate(data["body"]):
    if not isinstance(field, dict):
        raise SystemExit(f"Body item {index} must be a YAML mapping.")
    field_type = field.get("type")
    if field_type == "markdown":
        continue
    if field_type not in {"input", "textarea", "dropdown", "checkboxes"}:
        raise SystemExit(f"Unsupported issue-form field type at item {index}: {field_type!r}")
    field_id = field.get("id")
    if not field_id:
        raise SystemExit(f"Missing field id at body item {index}.")
    if field_id in seen:
        raise SystemExit(f"Duplicate field id: {field_id}")
    seen.add(field_id)
    found.add(field_id)
    if field.get("validations", {}).get("required") != "true" and field_id in required_ids:
        raise SystemExit(f"Required field is not marked required: {field_id}")
    attributes = field.get("attributes")
    if not isinstance(attributes, dict) or not attributes.get("label"):
        raise SystemExit(f"Field {field_id} needs an attributes.label.")
    if field_type in {"dropdown", "checkboxes"}:
        options = attributes.get("options")
        if not isinstance(options, list) or not options:
            raise SystemExit(f"Field {field_id} must define at least one option.")

missing = required_ids - found
if missing:
    raise SystemExit("Required fields missing from template: " + ", ".join(sorted(missing)))

print(f"PASS: {path} parsed; {len(seen)} unique fields; all required fields present.")

workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
if not isinstance(workflow, dict):
    raise SystemExit("Agent governance workflow must be a YAML mapping.")
if workflow.get("name") != "Agent task governance":
    raise SystemExit("Unexpected agent governance workflow name.")
permissions = workflow.get("permissions", {})
if permissions.get("contents") != "read" or permissions.get("issues") != "write":
    raise SystemExit("Workflow permissions must remain contents: read and issues: write.")
events = workflow.get("on", {})
if not isinstance(events, dict) or "issues" not in events or "workflow_dispatch" not in events:
    raise SystemExit("Workflow must be event-driven by issues and support manual validation.")
issue_events = set(events["issues"].get("types", []))
if not {"opened", "edited", "reopened", "labeled"} <= issue_events:
    raise SystemExit("Workflow is missing required issue lifecycle events.")
jobs = workflow.get("jobs", {})
job = jobs.get("validate-agent-task", {})
steps = job.get("steps", [])
if not any(step.get("uses") == "actions/github-script@v7" for step in steps):
    raise SystemExit("Workflow must use the reviewed GitHub Script step.")
if not workflow.get("concurrency"):
    raise SystemExit("Workflow must define a concurrency group.")
print(f"PASS: {workflow_path} parsed; least-privilege permissions and required triggers verified.")
