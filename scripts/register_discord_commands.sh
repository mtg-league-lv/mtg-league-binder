#!/usr/bin/env bash
# One-time script to register slash commands with Discord.
# Usage: DISCORD_APP_ID=<id> DISCORD_BOT_TOKEN=<token> bash scripts/register_discord_commands.sh

set -euo pipefail

: "${DISCORD_APP_ID:?Need DISCORD_APP_ID}"
: "${DISCORD_BOT_TOKEN:?Need DISCORD_BOT_TOKEN}"

echo "Registering slash commands for app ${DISCORD_APP_ID}..."

curl -sS -X PUT \
  "https://discord.com/api/v10/applications/${DISCORD_APP_ID}/commands" \
  -H "Authorization: Bot ${DISCORD_BOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "name": "register",
      "description": "Add a Moxfield binder to the database",
      "options": [{"name":"url","description":"Moxfield binder URL","type":3,"required":true}]
    },
    {
      "name": "mybinders",
      "description": "List your registered binders"
    },
    {
      "name": "removebinder",
      "description": "Remove a registered binder",
      "options": [{"name":"url","description":"Moxfield binder URL","type":3,"required":true}]
    },
    {
      "name": "search",
      "description": "Find binders containing a card",
      "options": [{"name":"query","description":"Card name to search for","type":3,"required":true}]
    }
  ]' | jq .

echo "Done."
