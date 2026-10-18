#!/usr/bin/env bash
# Bionic Wine product entry. See arlinux/BUILD.md.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
command="${1:---help}"
shift || true
case "$command" in
  github) exec python3 arlinux/build/github-products.py "$@" ;;
  wine) exec python3 arlinux/build/wine-pipeline.py "$@" ;;
  publish-wine) exec python3 arlinux/publish-wine-latest.py "$@" ;;
  *) echo 'Usage: ./arlinux/build.sh {github|wine|publish-wine} ...' ;;
esac
