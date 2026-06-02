# League Binder Bot

A Telegram bot for searching Magic: The Gathering cards across community Moxfield binders.

## Architecture

- **Bot:** Supabase Edge Function (`supabase/functions/telegram-bot/`) — TypeScript/Deno + Grammy
- **Scraper:** Python script (`scraper/main.py`) — runs daily via GitHub Actions
- **Database:** Supabase PostgreSQL — `users`, `binders`, `binder_cards` tables

## Setup

### 1. Supabase project

1. Create a project at [supabase.com](https://supabase.com)
2. Apply the migration: paste `supabase/migrations/20260602000001_initial.sql` into the Supabase SQL Editor and run it

### 2. Telegram bot

1. Create a bot via [@BotFather](https://t.me/BotFather) and get your `TELEGRAM_BOT_TOKEN`

### 3. Deploy the Edge Function

```bash
npm install -g supabase
supabase login
supabase link --project-ref <your-project-ref>
supabase functions deploy telegram-bot --no-verify-jwt
```

In Supabase dashboard → Edge Functions → telegram-bot → Secrets, add:
- `TELEGRAM_BOT_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

### 4. Register the webhook

```bash
TELEGRAM_BOT_TOKEN=<your-token> \
EDGE_FUNCTION_URL=https://<project-ref>.supabase.co/functions/v1/telegram-bot \
bash scripts/set_webhook.sh
```

### 5. GitHub Actions (scraper)

In your GitHub repo → Settings → Secrets → Actions, add:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The scraper runs daily at 3am UTC. Trigger manually: Actions → Daily Binder Scrape → Run workflow.

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/register <url>` | Register a Moxfield binder |
| `/mybinders` | List your registered binders |
| `/removebinder <url>` | Remove a binder |
| `/search <card name>` | Find who has a card |

## Moxfield API note

The scraper uses `https://api2.moxfield.com/v2/binders/{id}`. If Moxfield changes their API, update `parse_cards()` in `scraper/main.py`.
