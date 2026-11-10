# GitHub `main` to AWS EC2 automatic code synchronisation

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
