#!/usr/bin/env bash
# One-file bootstrap: downloads DeckForever into ~/Games/DeckForever/app and opens it.
#   curl -fsSL https://raw.githubusercontent.com/eliog/DeckForever/main/bootstrap.sh | bash
set -euo pipefail
REPO="${DECKFOREVER_REPO:-eliog/DeckForever}"
BRANCH="${DECKFOREVER_BRANCH:-main}"
DEST="${DECKFOREVER_ROOT:-$HOME/Games/DeckForever}/app"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
curl -fsSL -o "$TMP/app.tar.gz" "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz"
mkdir -p "$DEST" "$TMP/x"
tar -xzf "$TMP/app.tar.gz" -C "$TMP/x" --strip-components=1
cp -r "$TMP/x/deckforever" "$TMP/x/run.sh" "$TMP/x/README.md" "$DEST/"
chmod +x "$DEST/run.sh"
cleanup
trap - EXIT
exec "$DEST/run.sh"
