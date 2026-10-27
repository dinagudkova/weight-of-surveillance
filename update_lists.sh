#!/usr/bin/env bash
# Downloads fresh copies of the tracker lists and the CrUX Germany top list.
set -euo pipefail
cd "$(dirname "$0")/lists"
curl -fsSL -o ddg-tds.json https://raw.githubusercontent.com/duckduckgo/tracker-blocklists/main/web/v6/extension-tds.json
curl -fsSL -o easyprivacy.txt https://raw.githubusercontent.com/easylist/easylist/gh-pages/easyprivacy.txt
curl -fsSL -o easylist.txt https://raw.githubusercontent.com/easylist/easylist/gh-pages/easylist.txt
curl -fsSL -o easylistgermany.txt https://raw.githubusercontent.com/easylist/easylistgermany/gh-pages/easylistgermany.txt
echo "Lists updated: $(date -u +%F)"
