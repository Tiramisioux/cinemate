#!/usr/bin/env bash
set -euo pipefail

# Ensure docs/ directory exists
mkdir -p docs

# Overwrite docs/coverpage.md with the current UTC timestamp
cat > docs/coverpage.md <<EOF
# Cinemate Docs

> **Built:** $(date -u '+%Y-%m-%d %H:%M UTC')

---
EOF
