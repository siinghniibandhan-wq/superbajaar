#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ODOO_DIR="$SCRIPT_DIR/community"

if [[ ! -f "$ODOO_DIR/odoo-bin" ]]; then
  if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: repository checkout is required to initialize odoo/community." >&2
    exit 1
  fi
  git -C "$REPO_ROOT" submodule update --init --recursive -- odoo/community
fi

if [[ ! -f "$ODOO_DIR/odoo-bin" || ! -d "$ODOO_DIR/addons" ]]; then
  echo "ERROR: Odoo Community source is missing or incomplete at $ODOO_DIR." >&2
  exit 1
fi

ADDONS_PATH="$ODOO_DIR/addons,$SCRIPT_DIR/custom_addons"
cd "$ODOO_DIR"
exec python3 "$ODOO_DIR/odoo-bin" --addons-path="$ADDONS_PATH" "$@"
