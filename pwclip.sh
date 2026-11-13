#!/bin/bash
# Put a named credential on the clipboard without printing it.
# Usage: pwclip.sh [KEY]   default KEY is ALL_ATS_PASSWORD
set -euo pipefail
KEY="${1:-ALL_ATS_PASSWORD}"
python3 -c "
import re, subprocess, sys, pathlib
key = sys.argv[1]
root = pathlib.Path(sys.argv[2])
t = (root / 'profiles' / (root / 'PROFILE').read_text().strip() / 'ATS-CREDENTIALS.txt').read_text()
m = re.search(rf'^{re.escape(key)}\s*[:=]\s*(\S+)', t, re.M)
assert m, f'{key} missing'
subprocess.run(['pbcopy'], input=m.group(1).encode(), check=True)
" "$KEY" "$(cd "$(dirname "$0")" && pwd)"
# Clear it after 30s, but only if it still holds the password: compare hashes,
# so the value itself never reaches a variable, an argument or the terminal.
H="$(pbpaste | shasum -a 256)"
( sleep 30; [[ "$(pbpaste | shasum -a 256)" == "$H" ]] && printf '' | pbcopy ) >/dev/null 2>&1 &
disown
echo "$KEY on clipboard for 30 seconds"
