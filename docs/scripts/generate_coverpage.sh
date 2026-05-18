#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." && pwd )"

# Ensure target folder exists
mkdir -p "$ROOT_DIR/docs"

# Overwrite/create coverpage
cat > "$ROOT_DIR/docs/coverpage.md" <<EOF
---
title: Cinemate Documentation
---

**Built:** $(date -u '+%Y-%m-%d %H:%M UTC')
EOF
