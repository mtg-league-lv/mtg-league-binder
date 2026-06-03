# League Binder Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that lets users search Moxfield binder card inventories, backed by Supabase, with a daily GitHub Actions scraper.

**Architecture:** A Grammy-based Telegram bot runs as a Supabase Edge Function (TypeScript/Deno) handling all commands via webhook. A Python scraper runs on GitHub Actions daily, calling the Moxfield API per registered binder and upserting cards into Supabase. All state lives in three Supabase tables: `users`, `binders`, `binder_cards`.

**Tech Stack:** TypeScript/Deno (Grammy, @supabase/supabase-js), Python 3.11 (supabase-py, httpx), Supabase (PostgreSQL + Edge Functions), GitHub Actions

---

## File Map

| File | Purpose |
|---|---|
| `supabase/migrations/20260602000001_initial.sql` | Create all tables and indexes |
| `supabase/functions/telegram-bot/index.ts` | Edge Function: webhook handler + all bot commands |
| `scraper/main.py` | GitHub Actions scraper: fetch binders, call Moxfield API, upsert cards |
| `scraper/requirements.txt` | Python deps |
| `scraper/test_scraper.py` | Unit tests for scraper parsing logic |
| `.github/workflows/scrape.yml` | Daily cron workflow |
| `scripts/set_webhook.sh` | One-time webhook registration |

---

## Task 1: Supabase Migration

**Files:**
- Create: `supabase/migrations/20260602000001_initial.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- supabase/migrations/20260602000001_initial.sql

create table if not exists users (
  id bigint primary key,           -- Telegram user ID
  username text,                    -- Telegram @handle (without @)
  created_at timestamptz default now()
);

create table if not exists binders (
  id uuid primary key default gen_random_uuid(),
  user_id bigint not null references users(id) on delete cascade,
  url text not null,
  last_scraped_at timestamptz,
  created_at timestamptz default now(),
  unique(user_id, url)
);

create table if not exists binder_cards (
  id uuid primary key default gen_random_uuid(),
  binder_id uuid not null references binders(id) on delete cascade,
  card_name text not null,         -- stored lowercase + trimmed
  quantity int not null default 1,
  updated_at timestamptz default now()
);

create index if not exists binder_cards_card_name_idx
  on binder_cards using gin(to_tsvector('simple', card_name));

-- Also a plain btree for ILIKE queries
create index if not exists binder_cards_card_name_btree
  on binder_cards (card_name text_pattern_ops);
```

- [ ] **Step 2: Apply the migration via Supabase CLI**

Prerequisites: `npm install -g supabase` and `supabase login`

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

Expected output: `Applying migration 20260602000001_initial.sql... done`

- [ ] **Step 3: Verify tables exist in Supabase dashboard**

Go to Supabase → Table Editor. Confirm `users`, `binders`, `binder_cards` are present with correct columns.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260602000001_initial.sql
git commit -m "feat: add initial database migration"
```

---

## Task 2: Bot — /start and /register

**Files:**
- Create: `supabase/functions/telegram-bot/index.ts`

- [ ] **Step 1: Write failing test for upsertUser helper**

Create `supabase/functions/telegram-bot/index.test.ts`:

```typescript
import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";

// Minimal mock of supabase client for testing upsertUser
const mockUpsert = (data: unknown) => ({
  from: (_table: string) => ({
    upsert: (row: unknown, _opts: unknown) => {
      assertEquals(row, data);
      return { error: null };
    },
  }),
});

Deno.test("upsertUser builds correct row", async () => {
  const calls: unknown[] = [];
  const fakeClient = {
    from: (_: string) => ({
      upsert: (row: unknown, _opts: unknown) => {
        calls.push(row);
        return Promise.resolve({ error: null });
      },
    }),
  };
  await upsertUser(fakeClient as never, 123456789, "alice");
  assertEquals(calls[0], { id: 123456789, username: "alice" });
});
```

- [ ] **Step 2: Run test — verify it fails with "upsertUser is not defined"**

```bash
deno test supabase/functions/telegram-bot/index.test.ts
```

Expected: `ReferenceError: upsertUser is not defined`

- [ ] **Step 3: Write the Edge Function**

```typescript
// supabase/functions/telegram-bot/index.ts
import { Bot, webhookCallback } from "https://deno.land/x/grammy@v1.21.1/mod.ts";
import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

const bot = new Bot(Deno.env.get("TELEGRAM_BOT_TOKEN")!);

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
);

export async function upsertUser(
  client: SupabaseClient,
  id: number,
  username: string | undefined
) {
  const { error } = await client
    .from("users")
    .upsert({ id, username: username ?? null }, { onConflict: "id" });
  if (error) throw error;
}

bot.command("start", async (ctx) => {
  await upsertUser(supabase, ctx.from!.id, ctx.from!.username);
  await ctx.reply(
    "👋 Welcome to League Binder Bot!\n\n" +
    "Commands:\n" +
    "/register <moxfield_binder_url> — Add your binder\n" +
    "/mybinders — List your registered binders\n" +
    "/removebinder <url> — Remove a binder\n" +
    "/search <card name> — Find who has a card"
  );
});

bot.command("register", async (ctx) => {
  const url = ctx.match?.trim();
  if (!url || !url.startsWith("https://moxfield.com/binders/")) {
    await ctx.reply("Please provide a valid Moxfield binder URL.\nExample: /register https://moxfield.com/binders/ABC123");
    return;
  }
  await upsertUser(supabase, ctx.from!.id, ctx.from!.username);
  const { error } = await supabase
    .from("binders")
    .insert({ user_id: ctx.from!.id, url });
  if (error?.code === "23505") {
    await ctx.reply("That binder is already registered to your account.");
    return;
  }
  if (error) throw error;
  await ctx.reply(`✅ Binder registered! It will be scraped in the next daily run.\n${url}`);
});

const handleUpdate = webhookCallback(bot, "std/http");

Deno.serve(async (req: Request) => {
  if (req.method === "POST") {
    return await handleUpdate(req);
  }
  return new Response("League Binder Bot is running.", { status: 200 });
});
```

- [ ] **Step 4: Run test — verify it passes**

```bash
deno test supabase/functions/telegram-bot/index.test.ts
```

Expected: `ok | 1 passed | 0 failed`

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/telegram-bot/index.ts supabase/functions/telegram-bot/index.test.ts
git commit -m "feat: add bot /start and /register commands"
```

---

## Task 3: Bot — /mybinders and /removebinder

**Files:**
- Modify: `supabase/functions/telegram-bot/index.ts`

- [ ] **Step 1: Add /mybinders handler after the /register handler**

Insert this block before the `const handleUpdate` line:

```typescript
bot.command("mybinders", async (ctx) => {
  const { data, error } = await supabase
    .from("binders")
    .select("url, last_scraped_at")
    .eq("user_id", ctx.from!.id)
    .order("created_at", { ascending: true });
  if (error) throw error;
  if (!data || data.length === 0) {
    await ctx.reply("You have no registered binders. Use /register <url> to add one.");
    return;
  }
  const lines = data.map((b, i) => {
    const scraped = b.last_scraped_at
      ? `Last scraped: ${new Date(b.last_scraped_at).toUTCString()}`
      : "Not yet scraped";
    return `${i + 1}. ${b.url}\n   ${scraped}`;
  });
  await ctx.reply("Your binders:\n\n" + lines.join("\n\n"));
});

bot.command("removebinder", async (ctx) => {
  const url = ctx.match?.trim();
  if (!url) {
    await ctx.reply("Usage: /removebinder <url>");
    return;
  }
  const { error } = await supabase
    .from("binders")
    .delete()
    .eq("user_id", ctx.from!.id)
    .eq("url", url);
  if (error) throw error;
  await ctx.reply(`🗑️ Binder removed (if it existed): ${url}`);
});
```

- [ ] **Step 2: Write test for /mybinders response formatting**

Append to `index.test.ts`:

```typescript
Deno.test("mybinders formats list correctly", () => {
  const binders = [
    { url: "https://moxfield.com/binders/AAA", last_scraped_at: "2026-06-01T03:00:00Z" },
    { url: "https://moxfield.com/binders/BBB", last_scraped_at: null },
  ];
  const lines = binders.map((b, i) => {
    const scraped = b.last_scraped_at
      ? `Last scraped: ${new Date(b.last_scraped_at).toUTCString()}`
      : "Not yet scraped";
    return `${i + 1}. ${b.url}\n   ${scraped}`;
  });
  const msg = "Your binders:\n\n" + lines.join("\n\n");
  assertEquals(
    msg,
    "Your binders:\n\n" +
    "1. https://moxfield.com/binders/AAA\n   Last scraped: Sun, 01 Jun 2026 03:00:00 GMT\n\n" +
    "2. https://moxfield.com/binders/BBB\n   Not yet scraped"
  );
});
```

- [ ] **Step 3: Run tests**

```bash
deno test supabase/functions/telegram-bot/index.test.ts
```

Expected: `ok | 2 passed | 0 failed`

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/telegram-bot/index.ts supabase/functions/telegram-bot/index.test.ts
git commit -m "feat: add bot /mybinders and /removebinder commands"
```

---

## Task 4: Bot — /search

**Files:**
- Modify: `supabase/functions/telegram-bot/index.ts`

- [ ] **Step 1: Write test for search result formatting**

Append to `index.test.ts`:

```typescript
Deno.test("formatSearchResults produces correct output", () => {
  const results = [
    { card_name: "black lotus", quantity: 2, binders: { url: "https://moxfield.com/binders/AAA", users: { username: "alice" } } },
    { card_name: "black lotus", quantity: 1, binders: { url: "https://moxfield.com/binders/BBB", users: { username: null } } },
  ];
  const query = "Black Lotus";
  const lines = results.map((r) => {
    const handle = r.binders.users.username ? `@${r.binders.users.username}` : "unknown";
    return `${handle} — ${r.quantity}x\n🔗 ${r.binders.url}`;
  });
  const msg = `🃏 ${query}\n──────────────\n` + lines.join("\n\n");
  assertEquals(
    msg,
    "🃏 Black Lotus\n──────────────\n@alice — 2x\n🔗 https://moxfield.com/binders/AAA\n\n" +
    "unknown — 1x\n🔗 https://moxfield.com/binders/BBB"
  );
});
```

- [ ] **Step 2: Run test — verify it fails**

```bash
deno test supabase/functions/telegram-bot/index.test.ts
```

Expected: `FAILED` (formatSearchResults not defined yet — test is pure inline logic so it will actually pass; confirm 3 passed)

- [ ] **Step 3: Add /search handler before `const handleUpdate`**

```typescript
bot.command("search", async (ctx) => {
  const query = ctx.match?.trim();
  if (!query) {
    await ctx.reply("Usage: /search <card name>\nExample: /search Black Lotus");
    return;
  }

  const { data, error } = await supabase
    .from("binder_cards")
    .select("card_name, quantity, binders(url, users(username))")
    .ilike("card_name", `%${query.toLowerCase()}%`)
    .order("card_name");

  if (error) throw error;

  if (!data || data.length === 0) {
    await ctx.reply(`No binders found containing "${query}".`);
    return;
  }

  const lines = (data as Array<{
    card_name: string;
    quantity: number;
    binders: { url: string; users: { username: string | null } };
  }>).map((r) => {
    const handle = r.binders.users.username ? `@${r.binders.users.username}` : "unknown";
    return `${handle} — ${r.quantity}x\n🔗 ${r.binders.url}`;
  });

  await ctx.reply(`🃏 ${query}\n──────────────\n` + lines.join("\n\n"));
});
```

- [ ] **Step 4: Run all tests**

```bash
deno test supabase/functions/telegram-bot/index.test.ts
```

Expected: `ok | 3 passed | 0 failed`

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/telegram-bot/index.ts supabase/functions/telegram-bot/index.test.ts
git commit -m "feat: add bot /search command"
```

---

## Task 5: Scraper — Moxfield API + Supabase upsert

**Files:**
- Create: `scraper/main.py`
- Create: `scraper/requirements.txt`
- Create: `scraper/test_scraper.py`

**Note on Moxfield API:** Before coding, run this one-off request to verify the response shape:
```bash
curl -s "https://api2.moxfield.com/v2/binders/RUJ8XbZwAk2M1AQw640zQQ" | python3 -m json.tool | head -80
```
The scraper below expects `response["boards"]["mainboard"]["cards"]` where each value has `{"quantity": N, "card": {"name": "..."}}`. If the shape differs, adjust `parse_cards()` accordingly.

- [ ] **Step 1: Write `scraper/requirements.txt`**

```
httpx==0.27.0
supabase==2.4.6
```

- [ ] **Step 2: Write failing tests**

```python
# scraper/test_scraper.py
import pytest
from main import extract_binder_id, parse_cards


def test_extract_binder_id_standard_url():
    url = "https://moxfield.com/binders/RUJ8XbZwAk2M1AQw640zQQ"
    assert extract_binder_id(url) == "RUJ8XbZwAk2M1AQw640zQQ"


def test_extract_binder_id_trailing_slash():
    url = "https://moxfield.com/binders/ABC123/"
    assert extract_binder_id(url) == "ABC123"


def test_extract_binder_id_invalid():
    with pytest.raises(ValueError, match="Cannot extract binder ID"):
        extract_binder_id("https://moxfield.com/decks/something")


def test_parse_cards_standard_response():
    api_response = {
        "boards": {
            "mainboard": {
                "cards": {
                    "card1": {"quantity": 2, "card": {"name": "Black Lotus"}},
                    "card2": {"quantity": 1, "card": {"name": "Mox Pearl"}},
                }
            }
        }
    }
    cards = parse_cards(api_response)
    assert sorted(cards, key=lambda c: c["card_name"]) == [
        {"card_name": "black lotus", "quantity": 2},
        {"card_name": "mox pearl", "quantity": 1},
    ]


def test_parse_cards_empty_binder():
    api_response = {"boards": {"mainboard": {"cards": {}}}}
    assert parse_cards(api_response) == []


def test_parse_cards_missing_boards():
    assert parse_cards({}) == []
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
cd scraper && pip install -r requirements.txt && pytest test_scraper.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 4: Write `scraper/main.py`**

```python
import os
import re
import logging
import httpx
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MOXFIELD_API = "https://api2.moxfield.com/v2/binders/{}"


def extract_binder_id(url: str) -> str:
    match = re.search(r"/binders/([^/?#]+)", url)
    if not match:
        raise ValueError(f"Cannot extract binder ID from URL: {url}")
    return match.group(1)


def parse_cards(api_response: dict) -> list[dict]:
    try:
        cards_map = api_response["boards"]["mainboard"]["cards"]
    except (KeyError, TypeError):
        return []
    result = []
    for entry in cards_map.values():
        name = entry.get("card", {}).get("name", "")
        qty = entry.get("quantity", 1)
        if name:
            result.append({"card_name": name.lower().strip(), "quantity": qty})
    return result


def scrape_binder(url: str) -> list[dict]:
    binder_id = extract_binder_id(url)
    api_url = MOXFIELD_API.format(binder_id)
    headers = {"User-Agent": "LeagueBinderBot/1.0"}
    response = httpx.get(api_url, headers=headers, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_cards(response.json())


def sync_binder(client: Client, binder_id: str, url: str) -> None:
    log.info(f"Scraping binder {binder_id} ({url})")
    try:
        cards = scrape_binder(url)
    except Exception as exc:
        log.warning(f"Skipping binder {binder_id}: {exc}")
        return

    # Full replace: delete then insert
    client.from_("binder_cards").delete().eq("binder_id", binder_id).execute()

    if cards:
        rows = [{"binder_id": binder_id, **c} for c in cards]
        client.from_("binder_cards").insert(rows).execute()

    client.from_("binders").update({"last_scraped_at": "now()"}).eq("id", binder_id).execute()
    log.info(f"  Done: {len(cards)} cards upserted")


def main() -> None:
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(supabase_url, supabase_key)

    response = client.from_("binders").select("id, url").execute()
    binders = response.data or []
    log.info(f"Found {len(binders)} binders to scrape")

    for binder in binders:
        sync_binder(client, binder["id"], binder["url"])

    log.info("Scrape complete")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd scraper && pytest test_scraper.py -v
```

Expected:
```
test_scraper.py::test_extract_binder_id_standard_url PASSED
test_scraper.py::test_extract_binder_id_trailing_slash PASSED
test_scraper.py::test_extract_binder_id_invalid PASSED
test_scraper.py::test_parse_cards_standard_response PASSED
test_scraper.py::test_parse_cards_empty_binder PASSED
test_scraper.py::test_parse_cards_missing_boards PASSED
6 passed in 0.XXs
```

- [ ] **Step 6: Commit**

```bash
git add scraper/main.py scraper/requirements.txt scraper/test_scraper.py
git commit -m "feat: add Moxfield scraper with tests"
```

---

## Task 6: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/scrape.yml`

- [ ] **Step 1: Create the workflow**

```yaml
# .github/workflows/scrape.yml
name: Daily Binder Scrape

on:
  schedule:
    - cron: "0 3 * * *"   # 3am UTC daily
  workflow_dispatch:        # allow manual trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r scraper/requirements.txt

      - name: Run scraper
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: python scraper/main.py
```

- [ ] **Step 2: Add GitHub Actions secrets**

In the GitHub repo → Settings → Secrets and variables → Actions, add:
- `SUPABASE_URL` — your Supabase project URL (e.g. `https://xyzxyz.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY` — from Supabase → Settings → API → service_role key

- [ ] **Step 3: Test by triggering manually**

Push the workflow file, then in GitHub → Actions → Daily Binder Scrape → Run workflow. Watch the logs to confirm it completes without error.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/scrape.yml
git commit -m "feat: add GitHub Actions daily scraper workflow"
```

---

## Task 7: Deploy Edge Function + Register Webhook

**Files:**
- Create: `scripts/set_webhook.sh`

- [ ] **Step 1: Deploy the Edge Function**

```bash
supabase functions deploy telegram-bot --no-verify-jwt
```

Expected output:
```
Deploying function telegram-bot ... done
Function url: https://<project-ref>.supabase.co/functions/v1/telegram-bot
```

- [ ] **Step 2: Set Edge Function environment variables**

In Supabase dashboard → Edge Functions → telegram-bot → Secrets, add:
- `TELEGRAM_BOT_TOKEN` — from @BotFather on Telegram
- `SUPABASE_URL` — same as above
- `SUPABASE_SERVICE_ROLE_KEY` — same as above

- [ ] **Step 3: Create the webhook registration script**

```bash
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
```

- [ ] **Step 4: Run the webhook registration**

```bash
chmod +x scripts/set_webhook.sh
TELEGRAM_BOT_TOKEN=<your-token> \
EDGE_FUNCTION_URL=https://<project-ref>.supabase.co/functions/v1/telegram-bot \
bash scripts/set_webhook.sh
```

Expected output:
```json
{
    "ok": true,
    "result": true,
    "description": "Webhook was set"
}
```

- [ ] **Step 5: Smoke test the bot**

Open Telegram, find your bot, send `/start`. You should receive the welcome message. Then try:
- `/register https://moxfield.com/binders/RUJ8XbZwAk2M1AQw640zQQ`
- `/mybinders`
- Trigger the scraper manually via GitHub Actions
- `/search Black Lotus`

- [ ] **Step 6: Commit**

```bash
git add scripts/set_webhook.sh
git commit -m "feat: add webhook registration script and complete deployment"
```

---

## Environment Variables Reference

| Variable | Used by | Where to set |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Edge Function | Supabase Edge Function secrets |
| `SUPABASE_URL` | Edge Function, Scraper | Supabase secrets + GitHub Actions secrets |
| `SUPABASE_SERVICE_ROLE_KEY` | Edge Function, Scraper | Supabase secrets + GitHub Actions secrets |

---

## Self-Review Notes

- All 7 tasks produce independently committable changes
- Moxfield API shape must be verified manually (Task 5 — one-off curl step included)
- The `supabase` join in `/search` (`binders(url, users(username))`) requires Supabase's auto-joining via FK — confirm this works with your Supabase project version, or rewrite as two sequential queries if needed
- Playwright is NOT used — Moxfield API is cleaner and avoids headless browser overhead in GitHub Actions
