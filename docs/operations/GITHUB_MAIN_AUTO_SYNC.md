# GitHub `main` to AWS EC2 automatic code synchronisation

**Status:** Operational behaviour reference  
**Last reviewed:** 12 November 2026  
**Scope:** Source checkout synchronization only; not application deployment or database migration.

> This document describes the repository automation. Confirm the installed systemd units on the EC2 host before relying on it; a script or unit file in Git is not proof that the timer is installed or active.

## Behaviour

The EC2 host checks `origin/main` every two minutes using a dedicated systemd timer. If the remote branch has advanced and the production checkout is clean, the script performs a fast-forward-only update. If there is no new commit, it exits without changing the checkout.

Target checkout: `/opt/superbajaar/source`  
Branch: `main`  
Remote: `origin`  
Runtime user: `ubuntu`

## Safety boundaries

- The synchroniser refuses to run unless the checkout is on `main`.
- It refuses to update a dirty working tree, including untracked files.
- It never runs `reset`, `clean`, force operations, builds, SQL migrations, or service restarts.
- It refuses non-fast-forward divergence for manual investigation.
- A lock prevents overlapping runs.
- Authentication is inherited from the checkout's existing Git remote configuration. Do not put tokens or private keys in this repository or in the script.
- The existing schema migration timer and its status-only behaviour are not modified.

This is code synchronisation only. It does not mean the application has been rebuilt or redeployed/restarted.

## Install on the EC2 host

After the new files are present in `/opt/superbajaar/source`, run:

```bash
sudo bash /opt/superbajaar/source/backend/scripts/install_github_sync.sh
```

The installer enables `superbajaar-github-sync.timer` and triggers one initial check. The timer starts one minute after boot and then every two minutes.

## Verify

```bash
systemctl list-timers --all | grep superbajaar-github-sync
systemctl status superbajaar-github-sync.timer
systemctl status superbajaar-github-sync.service
journalctl -u superbajaar-github-sync.service -n 50 --no-pager
tail -n 50 /var/log/superbajaar-github-sync.log
```

## Roll back / disable

```bash
sudo systemctl disable --now superbajaar-github-sync.timer
```

Disabling the timer does not revert any code already synchronised.


---

## Current three-lane deployment relationship — 13 November 2026

The GitHub sync timer described above remains the original, unchanged source-sync lane. The owner reports that it continues to run every two minutes as `ubuntu`, using `backend/scripts/sync_main.sh` for fetch and fast-forward only. It requires a clean checkout and never builds, migrates or restarts the application.

The schema apply and backend deployment lanes are separate timers:

- `superbajaar-schema.timer`: even minutes; applies eligible migrations after verified backup.
- `superbajaar-backend-deploy.timer`: odd minutes; deploys backend changes only after required migrations are present in the ledger.

The intended total delay after a GitHub push is approximately 2–4 minutes. See the [three-lane deployment runbook](PRODUCTION_DEPLOYMENT.md#aws-native-three-lane-auto-deployment--13-november-2026). This relationship does not change the sync script's safety boundaries above.
