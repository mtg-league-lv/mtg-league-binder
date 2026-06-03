# League Binder Bot — Design Spec

**Date:** 2026-06-02  
**Status:** Approved

## Overview

A Telegram bot that lets users search for Magic: The Gathering cards across a community database of Moxfield binders. Users register their binder URLs with the bot; a daily scraper keeps card inventory up to date. Admins manage binders directly via the Supabase dashboard.

---

## Architecture

Three components:

1. **Telegram Bot** — Supabase Edge Function (TypeScript/Deno + Grammy). Webhook-based; stateless per invocation. Handles all user commands and queries Supabase directly.
2. **Scraper** — Python script (`scraper/main.py`) run daily by GitHub Actions. Uses Playwright (headless Chromium) to scrape Moxfield binder pages (which are JS-rendered) and upserts card data into Supabase.
3. **Supabase** — PostgreSQL database storing users, binder registrations, and scraped card inventory.

```
┌─────────────────────────────────────────────────────┐
│                     Supabase                         │
│  ┌──────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │  users   │  │  binders   │  │   binder_cards  │  │
│  └──────────┘  └────────────┘  └─────────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │                             │
   ┌──────▼──────┐              ┌───────▼────────┐
   │ Telegram Bot│              │ GitHub Actions  │
   │ Edge Function              │  scraper.py     │
   │ (TypeScript) │              │  runs daily     │
   └─────────────┘              └────────────────┘
```

---

## Database Schema

### `users`
| column | type | notes |
|---|---|---|
| `id` | `bigint` PK | Telegram user ID |
| `username` | `text` | Telegram @handle |
| `created_at` | `timestamptz` | auto |

### `binders`
| column | type | notes |
|---|---|---|
| `id` | `uuid` PK | |
| `user_id` | `bigint` FK → users | binder owner |
| `url` | `text` | full Moxfield binder URL |
| `last_scraped_at` | `timestamptz` | nullable; updated after each scrape |
| `created_at` | `timestamptz` | auto |

### `binder_cards`
| column | type | notes |
|---|---|---|
| `id` | `uuid` PK | |
| `binder_id` | `uuid` FK → binders | |
| `card_name` | `text` | normalized: lowercase, trimmed |
| `quantity` | `int` | |
| `updated_at` | `timestamptz` | auto |

**Index:** `binder_cards(card_name)` for fast substring search.

Card search uses `ILIKE '%query%'` on `card_name`.

---

## Telegram Bot Commands

| command | access | description |
|---|---|---|
| `/start` | anyone | Welcome message and usage instructions |
| `/register <moxfield_binder_url>` | any user | Registers a binder URL under the caller's account |
| `/mybinders` | any user | Lists the caller's registered binders |
| `/removebinder <url>` | any user | Removes one of the caller's binders |
| `/search <card name>` | anyone | Returns all users who have the card (substring match) |

Admins add binder URLs for other users directly via the Supabase dashboard — no bot command needed.

### Search Response Format

```
🃏 Black Lotus
──────────────
@alice — 2x
🔗 https://moxfield.com/binders/xxx

@bob — 1x
🔗 https://moxfield.com/binders/yyy
```

If no matches found:
```
No binders found containing "Black Lotus".
```

---

## Scraper

**Location:** `scraper/main.py`  
**Schedule:** GitHub Actions cron `0 3 * * *` (daily 3am UTC) + manual `workflow_dispatch`

### Steps per run

1. Fetch all rows from `binders` table via Supabase service role client
2. For each binder URL:
   - Launch Playwright headless Chromium, navigate to the URL
   - Extract all card names and quantities from the rendered page
   - Delete existing `binder_cards` rows for this binder
   - Insert fresh rows (full replace strategy)
   - Update `binders.last_scraped_at = now()`
3. If a binder URL is unreachable or returns an error: log the failure, skip silently, keep last known data

### Secrets (GitHub Actions)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

### Python dependencies
- `playwright`
- `supabase` (supabase-py)

---

## Edge Function — Bot Hosting

**URL:** `https://<project>.supabase.co/functions/v1/telegram-bot`

Telegram webhook is registered once via `setWebhook` API call pointing at this URL.

### Environment Variables (Supabase dashboard)
- `TELEGRAM_BOT_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

### TypeScript dependencies (Deno)
- `grammy` — Telegram bot framework
- `@supabase/supabase-js` — Supabase client

---

## Project Structure

```
supabase/
  functions/
    telegram-bot/
      index.ts          — webhook handler + command router
  migrations/
    001_initial.sql     — users, binders, binder_cards tables + index
scraper/
  main.py
  requirements.txt
.github/
  workflows/
    scrape.yml
scripts/
  set_webhook.sh        — one-time webhook registration
```

---

## Out of Scope

- Fuzzy/typo-tolerant search (substring match only)
- Notifying users when their binder is unreachable
- Multi-platform support (Telegram only)
- Card image previews
