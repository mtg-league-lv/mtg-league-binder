#!/usr/bin/env bash
# scripts/set_webhook.sh
# Usage: TELEGRAM_BOT_TOKEN=xxx EDGE_FUNCTION_URL=https://... bash scripts/set_webhook.sh

set -euo pipefail

: "${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN}"
: "${EDGE_FUNCTION_URL:?Set EDGE_FUNCTION_URL}"

curl -s -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${EDGE_FUNCTION_URL}\"}" | python3 -m json.tool
