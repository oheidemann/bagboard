#!/bin/bash
# Installs BagBoard into ~/BagBoard (or the folder in BAGBOARD_DIR) and starts it.
#   curl -fsSL https://raw.githubusercontent.com/oheidemann/bagboard/main/install.sh | bash
# Running it again repairs the program; your notes and settings in the data folder stay.
set -euo pipefail
DIR="${BAGBOARD_DIR:-$HOME/BagBoard}"
URL="${BAGBOARD_UPDATE_URL:-https://github.com/oheidemann/bagboard/releases/latest/download/}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Downloading BagBoard ..."
curl -fsSL -o "$TMP/BagBoard.zip" "${URL}BagBoard.zip"
unzip -q "$TMP/BagBoard.zip" -d "$TMP"
mkdir -p "$DIR"
cp -R "$TMP/BagBoard/." "$DIR/"
echo "BagBoard is in $DIR"
if [ -z "${BAGBOARD_NO_START:-}" ]; then
  echo "Starting it. Next time: double-click \"Start BagBoard.command\" in that folder."
  open "$DIR/Start BagBoard.command"
fi
