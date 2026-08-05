#!/usr/bin/env bash
# Recupere l'historique XAUUSD M15 utilise par le backtest.
# Source : dataset public ejtraderLabs/historical-data (MetaTrader export).
# Les prix y sont en centiemes, la conversion est faite par backtest/smc/data.py.
set -euo pipefail

DEST="$(cd "$(dirname "$0")" && pwd)/data"
TMP="${TMPDIR:-/tmp}/xauusd-historical-data"

mkdir -p "$DEST"

if [ ! -d "$TMP/.git" ]; then
  git clone --depth 1 --filter=blob:none --no-checkout \
    https://github.com/ejtraderLabs/historical-data "$TMP"
fi

git -C "$TMP" sparse-checkout init --cone
git -C "$TMP" sparse-checkout set XAUUSD
git -C "$TMP" checkout HEAD

cp "$TMP"/XAUUSD/XAUUSD*.csv "$DEST"/
echo "Donnees copiees dans $DEST :"
ls -la "$DEST"
