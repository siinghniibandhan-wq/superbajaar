# PR Portfolio Monitor

## Purpose

The PR portfolio monitor provides visibility into open pull-request volume and age. It supports the repository's operating targets without forcing unsafe merges or automatic closures.

## Operating thresholds

| Metric | Threshold | Automated response |
|---|---:|---|
| Open PR portfolio | 15 maximum target | Create/update one portfolio capacity issue when the count exceeds 15 |
| PR age | 5 calendar days | Add `pr-aging-5d` label and one attention comment |
| PR age | 7 calendar days | Add `pr-escalation-7d` label and create one linked escalation issue |
| PR age | 10 calendar days | Add `pr-target-10d` label and one target-exceeded comment |

Age is measured from the PR creation timestamp using elapsed 24-hour days.

## Schedule and triggers

- Daily at 09:00 India Standard Time (03:30 UTC).
- When a PR targeting `main` is opened, reopened, synchronized, marked ready for review, or closed.
- Manual run through GitHub Actions.

## Safety boundaries

- The workflow uses the repository-provided `GITHUB_TOKEN`; it does not require a personal access token or external service.
- Permissions are limited to reading repository contents and pull requests, and writing issue comments, labels and escalation issues.
- It does not approve, merge, close, rebase, assign reviewers, or change branch protection.
- It never closes escalation or capacity issues automatically.
- Aged PRs must not be merged solely to satisfy a time target. Valid work must not be closed merely to reduce the portfolio count.
- The repository owner retains prioritisation and merge authority.

## Operational notes

- The monitor evaluates up to the first 100 open PRs; the normal portfolio ceiling is 15.
- Labels are created if absent.
- Marker comments and marker strings in escalation issues make repeated scheduled runs idempotent.
- If a PR is blocked, the owner/team should record the blocker, accountable owner, next action and next review date.
- Workflow failures should be investigated from the GitHub Actions run logs; the monitor does not silently treat failed execution as a successful report.
