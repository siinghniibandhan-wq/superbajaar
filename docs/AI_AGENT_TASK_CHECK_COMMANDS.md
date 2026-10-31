# AI Agent Task Check and Activation Commands

> Purpose: provide a repeatable, user-invoked pull workflow. GitHub is the shared task board; each AI agent checks its own work when the user asks it to. This document does not create background polling or provider sessions.

## 1. Shared assignment convention

Every delegated issue must identify its accountable owner in both the title/body and a routing label:

- `agent:chatgpt`
- `agent:copilot`
- `agent:gemini`
- `agent:perplexity`
- `agent:claude`

Use one `agent:<name>` label per issue. Also include:
- `Task owner: <agent>`
- `Task type: <audit | implementation | research | QA | documentation>`
- `Status: <ready | acknowledged | in-progress | blocked | review>`
- exact scope, allowed/protected paths, acceptance criteria, dependencies and expected report.

A label is a routing marker, not proof that an agent was notified, accepted or started. For Copilot cloud-agent execution, use the supported GitHub Copilot assignment/automation mechanism and verify its session/PR evidence. For Gemini and Perplexity, the user must invoke the relevant connected AI and ask it to check its assignments; an issue mention alone does not start a separate AI session.

## 2. Standard agent pull protocol

When the user says "Check GitHub task assignments", "Check your assigned issues", or equivalent:

1. Identify yourself by your actual provider/agent role. Do not impersonate another agent.
2. Read `README.md`, `AGENTS.md`, `docs/AI_ENGINEERING_OPERATING_MODEL.md`, this file, and the task-specific instructions.
3. Inspect the repository `siinghniibandhan-wq/superbajaar`.
4. Find all **open** issues carrying your exact `agent:<your-name>` label and confirm the issue body says you are the accountable owner. Sort by priority first, then most recently updated. Also inspect comments and linked PRs for changes, reassignment, blockers or completion.
5. Do not treat an issue assigned to another agent, a mere @mention, a reviewer request, or an issue without your owner marker as your assignment.
6. If there are no matching open issues, respond exactly in substance: "No open GitHub task assignments found for me in Super Bajaar as of <timestamp>. I did not start any work."
7. If there are matching issues, report issue number/title, priority, task type, scope, allowed paths, dependencies and any approval gates. Then begin the highest-priority ready task within your role and permissions. If multiple tasks are ready, work sequentially; do not overlap file paths or start duplicate implementations.
8. Before editing, inspect the latest `main`, open PRs/issues and reserved paths. Follow feature-branch, schema, security, testing and approval rules in `AGENTS.md`.
9. Post an acknowledgement comment in the issue before execution, then post progress, blockers and evidence in the same issue. Acknowledgement is not completion.
10. If access is missing, the issue cannot be read, scope conflicts, paid usage is required, or an approval gate is reached, report the exact blocker and stop the affected action. Never invent access, execution, tests or completion.

## 3. Copy-and-paste activation prompts

### GitHub Copilot

```text
Check your GitHub task assignments for the Super Bajaar repository (siinghniibandhan-wq/superbajaar). Read AGENTS.md, docs/AI_ENGINEERING_OPERATING_MODEL.md and docs/AI_AGENT_TASK_CHECK_COMMANDS.md first. Find open issues labelled agent:copilot whose body names GitHub Copilot as the accountable owner. Inspect comments, linked PRs, priority, allowed paths and dependencies. If none exist, report that no open assignments were found and do not start work. If one or more exist, acknowledge the highest-priority ready issue, then execute only within its scope and repository instructions. Use a dedicated feature branch and PR; never push to main, edit protected schema/migration assets, merge or deploy. Report actual commands, tests, commit SHA and blockers in the issue. Do not treat a mention alone as proof of assignment.
```

### Google Gemini

```text
Check your GitHub task assignments for Super Bajaar (siinghniibandhan-wq/superbajaar). Read AGENTS.md, docs/AI_ENGINEERING_OPERATING_MODEL.md and docs/AI_AGENT_TASK_CHECK_COMMANDS.md. Search for open issues labelled agent:gemini and verify that the issue body names Google Gemini as accountable owner. Inspect comments, linked PRs, priority, scope and dependencies. If none exist, say no open assignments were found and do not start work. If assignments exist, acknowledge the highest-priority ready task and begin only the permitted work. Gemini's default role is independent read-only audit/research unless the issue explicitly authorises a separate non-schema implementation task. Never edit schema/migrations, production data, secrets or infrastructure. Record evidence and unverified areas in the issue. Do not claim access or execution you cannot verify.
```

### Perplexity

```text
Check your GitHub task assignments for Super Bajaar (siinghniibandhan-wq/superbajaar). Read AGENTS.md, docs/AI_ENGINEERING_OPERATING_MODEL.md and docs/AI_AGENT_TASK_CHECK_COMMANDS.md. Find open issues labelled agent:perplexity and verify that the issue body names Perplexity as accountable owner. Inspect priority, comments, scope and dependencies. If none exist, report no open assignments found. If an issue exists, acknowledge it and perform the assigned external research/source verification only. Prefer primary official documentation, provide direct links, publication/update dates and clearly separate verified facts from assumptions. Do not edit code, create commits, change schema or claim private repository access unless actually available. Post the research findings in the issue.
```

### ChatGPT coordinator

```text
Check GitHub task assignments for Super Bajaar (siinghniibandhan-wq/superbajaar). Read AGENTS.md, docs/AI_ENGINEERING_OPERATING_MODEL.md and docs/AI_AGENT_TASK_CHECK_COMMANDS.md. Find open issues labelled agent:chatgpt and verify the issue body names ChatGPT as accountable owner. Also inspect all open agent-labelled issues and linked PRs to coordinate dependencies and avoid duplicate work. If no ChatGPT-owned issue exists, report that clearly; do not claim other agents have started. If an issue is assigned to me, acknowledge it, perform the permitted coordination/review/documentation work, and update GitHub with evidence. Do not claim another agent's work, and do not merge, deploy, incur paid usage or perform protected production/schema actions without owner approval.
```

## 4. Status meanings

- `READY`: issue is assigned and available for the named agent to pull; no agent acceptance is implied.
- `ACKNOWLEDGED`: the agent has explicitly confirmed acceptance in the issue.
- `IN PROGRESS`: the agent has started the scoped work and posted evidence of execution.
- `BLOCKED`: the agent has identified an access, dependency, approval or technical blocker.
- `REVIEW`: implementation/research output is ready for independent review.
- `COMPLETE`: acceptance criteria and evidence are recorded; this does not mean merged or deployed.

## 5. Important limitations

- This is **user-invoked polling**, not autonomous background monitoring. Each AI only checks when the user opens/uses that AI and gives it the activation prompt, unless a separate supported provider automation is configured.
- GitHub issues and labels do not themselves launch Gemini, Perplexity or a new ChatGPT session.
- Copilot must be explicitly started through an eligible Copilot agent assignment/automation. Creating an issue or adding `agent:copilot` alone is not proof of dispatch.
- The 60-second fallback timer applies only after actual dispatch with delivery evidence. Do not start it merely because an issue was created or labelled.
- Never ask the owner to paste API keys into chat. Use only existing authorised connections and provider-supported sign-in/permissions. No new paid usage without approval.
