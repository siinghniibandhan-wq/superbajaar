#!/usr/bin/env python3
"""Run deterministic, local simulations of the agent task governance rules."""

from pathlib import Path
import json
import subprocess
import tempfile
import yaml

root = Path(__file__).resolve().parents[2]
workflow_path = root / ".github/workflows/agent-task-governance.yml"
template_path = root / ".github/ISSUE_TEMPLATE/agent-work-task.yml"

workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
template = yaml.load(template_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

steps = workflow["jobs"]["validate-agent-task"]["steps"]
embedded_js = next(
    step["with"]["script"]
    for step in steps
    if step.get("uses") == "actions/github-script@v7"
)

required_ids = {
    "task_type", "priority", "objective", "primary_agent", "fallback",
    "dependencies", "base", "allowed_paths", "protected_paths",
    "access_mode", "evidence", "acceptance", "verification", "output", "reviewer",
}
fields = [field for field in template["body"] if field.get("type") != "markdown"]
ids = [field["id"] for field in fields]
assert len(ids) == len(set(ids)), "Issue form contains duplicate field IDs."
assert required_ids <= set(ids), "Issue form is missing required field IDs."

required_headings = [
    "Task type", "Priority", "Objective and user impact",
    "Primary agent / accountable owner", "Approved fallback",
    "Dependencies", "Repository, starting branch and base commit",
    "Allowed paths / write scope", "Protected paths / systems", "Access mode",
    "Required inputs and evidence", "Acceptance criteria",
    "Tests and verification required", "Expected deliverable and handoff",
    "Independent reviewer",
]
assert {field["attributes"]["label"] for field in fields} >= set(required_headings)

valid_body = "\n\n".join(f"### {heading}\n\nvalue" for heading in required_headings)
incomplete_body = valid_body.replace(
    "### Objective and user impact\n\nvalue",
    "### Objective and user impact\n\n_No response_",
)

harness = r"""
const calls = [];
const issueRecord = { number: 42, title: '[AGENT TASK] CI simulation', body: __BODY__, labels: __LABELS__ };
const context = {
  eventName: 'issues',
  payload: { action: __ACTION__, inputs: {} },
  issue: { number: 42 },
  repo: { owner: 'example', repo: 'simulation' }
};
const github = { rest: { issues: {
  get: async () => ({ data: issueRecord }),
  listLabelsForRepo: async () => ({ data: [] }),
  createLabel: async ({ name }) => calls.push(['createLabel', name]),
  addLabels: async ({ labels }) => {
    calls.push(['addLabels', labels]);
    issueRecord.labels.push(...labels.map(name => ({ name })));
  },
  removeLabel: async ({ name }) => {
    calls.push(['removeLabel', name]);
    issueRecord.labels = issueRecord.labels.filter(label => label.name !== name);
  },
  createComment: async ({ body }) => calls.push(['comment', body])
}}};
const core = {
  getInput: () => '',
  setFailed: value => calls.push(['failed', value]),
  info: value => calls.push(['info', value]),
  notice: value => calls.push(['notice', value])
};
(async () => {
  try {
    __SCRIPT__
  } finally {
    process.stdout.write(JSON.stringify(calls));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def run_simulation(body: str, labels=None, action="opened"):
    source = harness.replace("__BODY__", json.dumps(body))
    source = source.replace("__LABELS__", json.dumps(labels or []))
    source = source.replace("__ACTION__", json.dumps(action))
    source = source.replace("__SCRIPT__", embedded_js)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(source)
        path = Path(handle.name)
    try:
        result = subprocess.run(["node", str(path)], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    finally:
        path.unlink(missing_ok=True)


ready = run_simulation(valid_body)
assert ["addLabels", ["agent:ready"]] in ready, ready
assert not any(call[0] == "failed" for call in ready), ready
assert any(call[0] == "notice" and "does not dispatch" in call[1] for call in ready), ready
print("PASS: complete task becomes READY without dispatching an agent.")

blocked = run_simulation(incomplete_body)
assert ["addLabels", ["agent:blocked"]] in blocked, blocked
assert any(call[0] == "comment" and "Objective and user impact" in call[1] for call in blocked), blocked
assert any(call[0] == "failed" and "Objective and user impact" in call[1] for call in blocked), blocked
print("PASS: incomplete task becomes BLOCKED with an explanatory comment.")

reopened = run_simulation(valid_body, labels=[{"name": "agent:done"}], action="reopened")
assert ["addLabels", ["agent:ready"]] in reopened, reopened
assert ["removeLabel", "agent:done"] in reopened, reopened
print("PASS: reopened DONE task returns to READY for reassessment.")
