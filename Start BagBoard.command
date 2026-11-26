#!/bin/bash
# Double-click to start BagBoard. Leave the window open; closing it stops BagBoard.
cd "$(dirname "$0")"
if ! python3 -c "" 2>/dev/null; then
  echo "BagBoard needs Python 3, which comes with Apple's command line developer tools."
  echo "macOS should now show a window offering to install them. Click Install, wait until it"
  echo "has finished, then start BagBoard again."
  xcode-select --install 2>/dev/null
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
fi
exec python3 starter.py "$@"
