# Discord Bot Extension — Design Spec

## Goal

Add a Discord bot with the same card-search and binder-management functionality as the existing Telegram bot, sharing the same Supabase database and business logic.

## Architecture

A new Supabase Edge Function (`discord-bot`) sits alongside the existing `telegram-bot` function. Both functions import shared formatting and DB utilities from `supabase/functions/_shared/utils.ts`. The database schema is extended with two nullable columns on `users` to store Discord identity. No new tables are needed.

## Tech Stack

- **Runtime:** Deno (Supabase Edge Functions), same as Telegram bot
- **Discord API:** Raw HTTP — no library needed (Discord's webhook model is simple)
- **Signature verification:** `@noble/ed25519` (Deno-compatible, available via esm.sh)
- **Database:** Supabase (existing project, same tables)

---

## Database Changes

### Migration: add Discord identity to users

```sql
ALTER TABLE users ADD COLUMN discord_id bigint UNIQUE;
ALTER TABLE users ADD COLUMN discord_username text;
```

Both columns are nullable. Existing Telegram-only users are unaffected. A user who registers on both platforms shares one `users` row (matched by `discord_id` on Discord upserts, matched by `id` on Telegram upserts).

---

## Shared Utils (`supabase/functions/_shared/utils.ts`)

Move `supabase/functions/telegram-bot/utils.ts` to `supabase/functions/_shared/utils.ts`. Update the Telegram bot import path accordingly.

### Exports

**`upsertUser(client, telegramId, telegramUsername)`**
Unchanged. Upserts on `id` (Telegram user ID).

**`upsertDiscordUser(client, discordId, discordUsername)`**
New. Upserts on `discord_id` conflict.

```typescript
export async function upsertDiscordUser(
  client: SupabaseClient,
  discordId: bigint,
  discordUsername: string | undefined
) {
  const { error } = await client
    .from("users")
    .upsert(
      { discord_id: discordId, discord_username: discordUsername ?? null },
      { onConflict: "discord_id" }
    );
  if (error) throw error;
}
```

**`formatBinderList`** — unchanged.

**`formatSearchResults`** — updated display priority:
1. Telegram `@handle` (`users.username`)
2. Discord `@handle` (`users.discord_username`)
3. Binder `username` (scraper-sourced fallback)
4. `"unknown"`

Updated type signature for results:
```typescript
binders: {
  url: string;
  username: string | null;
  users: { username: string | null; discord_username: string | null } | null;
}
```

Updated handle resolution:
```typescript
const handle =
  r.binders.users?.username
    ? `@${r.binders.users.username}`
    : r.binders.users?.discord_username
      ? `@${r.binders.users.discord_username}`
      : (r.binders.username ?? "unknown");
```

---

## Discord Edge Function (`supabase/functions/discord-bot/index.ts`)

### Webhook verification

Every request from Discord must be verified using Ed25519 before processing. Requests failing verification return HTTP 401.

```typescript
import { verify } from "https://esm.sh/@noble/ed25519@2";

async function verifyDiscordRequest(req: Request, body: string): Promise<boolean> {
  const signature = req.headers.get("x-signature-ed25519") ?? "";
  const timestamp = req.headers.get("x-signature-timestamp") ?? "";
  const PUBLIC_KEY = Deno.env.get("DISCORD_PUBLIC_KEY")!;
  return verify(
    hexToBytes(signature),
    new TextEncoder().encode(timestamp + body),
    hexToBytes(PUBLIC_KEY)
  );
}
```

### PING handling

Discord sends type-1 interactions to verify the endpoint. Must respond with `{"type": 1}`.

### Slash commands

| Command | Arguments | Behaviour |
|---------|-----------|-----------|
| `/register` | `url` (string) | Validate Moxfield URL, insert into `binders`, confirm |
| `/mybinders` | — | List user's binders with last-scraped time |
| `/removebinder` | `url` (string) | Delete matching binder row, confirm |
| `/search` | `query` (string) | Search `binder_cards` ilike, return formatted list |

All business logic mirrors the Telegram bot exactly. User identity comes from `interaction.member?.user ?? interaction.user`.

### Response format

All replies use Discord interaction response type 4 (channel message with source):

```typescript
return new Response(
  JSON.stringify({ type: 4, data: { content: message } }),
  { headers: { "Content-Type": "application/json" } }
);
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `DISCORD_PUBLIC_KEY` | Ed25519 public key for request verification |
| `DISCORD_BOT_TOKEN` | Bearer token for registering slash commands |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |

---

## Setup Script (`scripts/register_discord_commands.sh`)

One-time script to register the 4 slash commands with Discord's REST API.

```bash
#!/usr/bin/env bash
# Usage: DISCORD_APP_ID=... DISCORD_BOT_TOKEN=... bash scripts/register_discord_commands.sh

curl -X PUT \
  "https://discord.com/api/v10/applications/${DISCORD_APP_ID}/commands" \
  -H "Authorization: Bot ${DISCORD_BOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '[
    {"name":"register","description":"Add a Moxfield binder","options":[{"name":"url","description":"Moxfield binder URL","type":3,"required":true}]},
    {"name":"mybinders","description":"List your registered binders"},
    {"name":"removebinder","description":"Remove a binder","options":[{"name":"url","description":"Moxfield binder URL","type":3,"required":true}]},
    {"name":"search","description":"Find binders containing a card","options":[{"name":"query","description":"Card name","type":3,"required":true}]}
  ]'
```

---

## Testing

### `supabase/functions/_shared/utils.test.ts`

Tests migrated from `telegram-bot/index.test.ts` plus new Discord coverage:

- `upsertUser` — existing tests (move here)
- `upsertDiscordUser` — same structure: correct row built, throws on error
- `formatBinderList` — existing tests (move here)
- `formatSearchResults` — existing tests plus:
  - Falls back to Discord handle when no Telegram handle
  - Falls back to binder username when neither handle present

### `supabase/functions/discord-bot/index.test.ts`

- Valid Ed25519 signature passes verification
- Invalid signature returns 401
- PING interaction (type 1) returns `{"type":1}`
- `/register` with valid URL inserts and replies with confirmation
- `/register` with invalid URL replies with usage message
- `/mybinders` with no binders replies with empty-state message
- `/search` with results returns formatted card list
- `/search` with no results returns not-found message

### `supabase/functions/telegram-bot/index.test.ts`

Slimmed down to Telegram-specific wiring only (utils tests moved to shared).

---

## File Changes Summary

| Action | Path |
|--------|------|
| New migration | `supabase/migrations/20260603000001_discord_user.sql` |
| Move + update | `supabase/functions/telegram-bot/utils.ts` → `supabase/functions/_shared/utils.ts` |
| Update import | `supabase/functions/telegram-bot/index.ts` |
| New | `supabase/functions/discord-bot/index.ts` |
| New | `supabase/functions/discord-bot/index.test.ts` |
| New | `supabase/functions/_shared/utils.test.ts` |
| Update | `supabase/functions/telegram-bot/index.test.ts` |
| New | `scripts/register_discord_commands.sh` |
