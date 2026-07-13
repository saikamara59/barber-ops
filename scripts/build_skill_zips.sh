#!/usr/bin/env bash
# Build Cowork-uploadable ZIPs of the two skills into dist/.
# Each ZIP contains the skill folder (SKILL.md + scripts/) at its top level.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/appointment-management-skill.zip dist/weekly-summary-skill.zip
(cd skills && zip -qr ../dist/appointment-management-skill.zip appointment-management)
(cd skills && zip -qr ../dist/weekly-summary-skill.zip weekly-summary)
ls -la dist/
