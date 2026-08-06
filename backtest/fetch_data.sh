#!/usr/bin/env bash
# Recupere l'historique XAUUSD M15 utilise par le backtest.
#
# Deux sources publiques, fusionnees par backtest/prepare_data.py :
#   1. BaseMax/XAUUSD-LSTM        -> XAU_15m_data.csv, 2004 -> 2025 (source principale)
#   2. ejtraderLabs/historical-data -> XAUUSD/XAUUSDm15.csv, 2012 -> 2022 (recoupement)
#
# Les deux series coincident au cent pres sur leur recouvrement (230 398
# bougies communes), meme fuseau serveur EET. La seconde sert de controle
# croise et de secours si la premiere devient indisponible.
#
# Au-dela de mars 2025 la source principale devient lacunaire (trous de 10 a
# 80 jours) : prepare_data.py coupe automatiquement au dernier segment continu.
# Pour aller plus loin, exporter depuis un terminal MetaTrader (voir
# docs/BACKTEST_SMC.md) et passer le fichier a prepare_data.py.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/data"
TMP="${TMPDIR:-/tmp}/xauusd-sources"

mkdir -p "$DEST" "$TMP"

clone_sparse() {  # repo, dossier, chemin a extraire
  local repo="$1" dir="$TMP/$2" path="$3"
  if [ ! -d "$dir/.git" ]; then
    GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --no-checkout \
      "https://github.com/$repo" "$dir"
  fi
  git -C "$dir" sparse-checkout init --cone >/dev/null
  git -C "$dir" sparse-checkout set --no-cone "/$path" >/dev/null
  git -C "$dir" checkout HEAD >/dev/null 2>&1
}

echo "== Telechargement des sources =="
clone_sparse "BaseMax/XAUUSD-LSTM"          "basemax"  "XAU_15m_data.csv"
clone_sparse "ejtraderLabs/historical-data" "ejtrader" "XAUUSD"
# Source du forward test : bougies 5 min en UTC allant jusqu'a aout 2025,
# soit au-dela de la coupure de l'historique principal (21 mars 2025).
clone_sparse "ilahuerta-IA/backtrader-pullback-window-xauusd" "forward" "data/XAUUSD_5m_5Yea.csv"

cp "$TMP"/ejtrader/XAUUSD/XAUUSD*.csv "$DEST"/ 2>/dev/null || true
mv "$DEST/XAUUSDm15.csv" "$DEST/XAUUSDm15_ejtrader.csv" 2>/dev/null || true
cp "$TMP"/forward/data/XAUUSD_5m_5Yea.csv "$DEST/XAUUSD_5m_forward.csv" 2>/dev/null || true

echo
echo "== Preparation de l'historique M15 =="
python3 "$HERE/prepare_data.py" \
  "$TMP/basemax/XAU_15m_data.csv" \
  "$DEST/XAUUSDm15_ejtrader.csv" \
  -o "$DEST/XAUUSDm15.csv"

echo
echo "== Audit =="
python3 "$HERE/verify_data.py" --data "$DEST/XAUUSDm15.csv"
