# topstep-claude-bridge

Pont **semi-automatique** entre TradingView, Claude (Anthropic) et un compte **Topstep** (via l'API ProjectX Gateway de TopstepX).

```
TradingView (alerte webhook)
        │
        ▼
  Serveur FastAPI ──► Garde-fous de risque Topstep (codés en dur)
        │
        ▼
  Claude Opus 4.8 ──► analyse le signal + l'état du compte → recommandation structurée
        │
        ▼
  Telegram ──► VOUS validez (✅ / ❌) — aucune exécution sans votre accord
        │
        ▼
  API ProjectX (TopstepX) ──► ordre au marché sur votre compte Topstep
```

## ⚠️ Conformité Topstep

Topstep **interdit le trading entièrement automatisé sans supervision**. Ce projet est
volontairement **semi-automatique** : chaque trade exige votre validation explicite via
Telegram. Ne retirez pas cette étape. Vérifiez les règles en vigueur sur
[help.topstep.com](https://help.topstep.com) avant toute utilisation. Utilisez d'abord
un compte d'évaluation/practice.

## Prérequis

1. **TradingView** — abonnement permettant les alertes webhook (Essential ou plus).
2. **TopstepX API** — abonnement API ProjectX (~29$/mois) : générez un `username` + `API key`
   sur votre dashboard. Docs : <https://gateway.docs.projectx.com>.
3. **Clé API Anthropic** — <https://platform.claude.com>.
4. **Bot Telegram** — créez un bot via [@BotFather](https://t.me/BotFather), récupérez le
   token, puis votre `chat_id` (envoyez un message au bot et lisez
   `https://api.telegram.org/bot<TOKEN>/getUpdates`).
5. Un serveur accessible en HTTPS depuis Internet (VPS, ou `ngrok`/`cloudflared` pour tester).

## Installation

```bash
cd topstep-claude-bridge
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis remplissez vos clés
uvicorn main:app --host 0.0.0.0 --port 8080
```

Pour tester en local sans VPS :

```bash
ngrok http 8080
# → utilisez l'URL https fournie comme URL de webhook TradingView
```

## Configuration de l'alerte TradingView

Dans votre alerte : **Webhook URL** = `https://votre-domaine/webhook/tradingview`,
et comme **message** :

```json
{"secret": "LA_MEME_VALEUR_QUE_WEBHOOK_SECRET",
 "symbol": "MGC",
 "side": "buy",
 "price": {{close}},
 "strategy": "ma-strategie-h1",
 "comment": "raison du signal"}
```

`symbol` doit correspondre à un contrat futures recherchable sur TopstepX
(ex. `MGC` micro-or, `MES` micro-S&P, `MNQ` micro-Nasdaq). Pour l'or XAUUSD,
l'équivalent futures Topstep est **GC** (or) ou **MGC** (micro-or).

## Garde-fous de risque (`.env`)

| Variable | Rôle |
|---|---|
| `RISK_MAX_DAILY_LOSS` | Stoppe tout signal si la perte du jour atteint ce montant |
| `RISK_MAX_POSITION_SIZE` | Taille max d'un ordre (contrats) |
| `RISK_MAX_OPEN_POSITIONS` | Refuse un signal si autant de positions sont déjà ouvertes |
| `APPROVAL_TIMEOUT_SECONDS` | Un trade non validé dans ce délai est rejeté |

Ces règles sont appliquées **en code, avant et indépendamment de Claude** — un signal ne
peut jamais les contourner.

## Notes techniques

- L'analyse Claude utilise `claude-opus-4-8` avec *adaptive thinking* et une **sortie
  structurée** (schéma Pydantic validé) : la décision est toujours `recommend`/`skip` avec
  taille et justification — jamais de texte libre à parser.
- Les endpoints ProjectX (`/api/Auth/loginKey`, `/api/Order/place`, …) suivent la doc
  publique ProjectX Gateway ; vérifiez-les contre la version en vigueur de l'API avant le réel.
- Le PnL journalier est ancré sur la balance au premier check du jour (redémarrer le serveur
  en cours de journée réinitialise l'ancrage — à durcir avec une persistance si besoin).

## Pistes d'amélioration

- Stop loss / take profit automatiques attachés à l'ordre (`/api/Order/place` accepte des brackets selon la doc).
- Persistance du PnL journalier (SQLite) pour survivre aux redémarrages.
- Filtre calendrier macro (bloquer NFP/FOMC/CPI automatiquement).
- Journal de trades + statistiques hebdomadaires générés par Claude.
