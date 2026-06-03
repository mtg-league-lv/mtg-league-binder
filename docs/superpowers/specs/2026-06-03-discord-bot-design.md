# Discord Bot Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Discord slash-command bot with the same functionality as the Telegram bot (register binder, list binders, remove binder, search cards), sharing the same Supabase database and unifying users across both platforms.

**Architecture:** A new Supabase Edge Function `discord-bot` handles Discord interaction webhooks. Shared formatting logic moves to `supabase/functions/_shared/utils.ts`. The `users` table gains `discord_id` and `discord_username` columns. Both bots write to the same `binders` and `binder_cards` tables.

**Tech Stack:** TypeScript (Deno), Supabase Edge Functions, Discord Interactions API (webhook model), Ed25519 signature verification via Web Crypto API

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `supabase/functions/_shared/utils.ts` | Create | `formatSearchResults`, `formatBinderList`, `upsertTelegramUser`, `upsertDiscordUser`, `BINDER_URL_RE` |
| `supabase/functions/telegram-bot/utils.ts` | Modify | Re-export from `_shared/utils.ts`; remove duplicate code |
| `supabase/functions/telegram-bot/index.ts` | Modify | Use `BINDER_URL_RE` from shared (accepts deckstats URLs too) |
| `supabase/functions/discord-bot/index.ts` | Create | Discord webhook handler with slash command routing |
| `supabase/functions/discord-bot/verify.ts` | Create | Ed25519 request signature verification |
| `supabase/functions/discord-bot/index.test.ts` | Create | Unit tests for Discord response formatting |
| `supabase/migrations/YYYYMMDD_discord_users.sql` | Create | Add `discord_id`, `discord_username` to `users` |

---

## Database Migration

```sql
ALTER TABLE users ADD COLUMN discord_id bigint UNIQUE;
ALTER TABLE users ADD COLUMN discord_username text;
```

The `users` table now represents a platform-agnostic user. A row may have `id` (Telegram), `discord_id`, both, or neither (admin rows with `user_id = null` on binders). The `binders.user_id` foreign key continues to reference `users.id` (the Telegram numeric ID, used as the primary key). Discord users that have never used Telegram get a new row with `id` set to their Discord ID (guaranteed unique across platforms since Discord IDs are 64-bit snowflakes and Telegram IDs are also 64-bit integers; in the unlikely event of collision, Discord users are inserted with a negative `id` derived from their Discord ID to avoid conflicts).

> **Implementation note:** To keep things simple, use `discord_id` as the primary lookup for Discord upserts. Insert a new `users` row using `discord_id` as the value for `id` if no existing row has that `discord_id`. If a collision occurs, prefix with a high bit or use a separate sequence. The safest approach: add `discord_id bigint UNIQUE` and look up users by `discord_id` for Discord interactions, by `id` for Telegram interactions.

---

## Shared Utils (`_shared/utils.ts`)

Moved from `telegram-bot/utils.ts`, with additions:

```typescript
// Binder URL validation — both platforms
export const BINDER_URL_RE =
  /^https:\/\/(moxfield\.com\/binders\/[A-Za-z0-9_-]+|deckstats\.net\/collection\/\d+)/;

// Unchanged from current utils.ts
export function formatBinderList(...) { ... }
export function formatSearchResults(...) { ... }

// Telegram upsert (existing upsertUser renamed)
export async function upsertTelegramUser(
  client: SupabaseClient,
  telegramId: number,
  username: string | undefined
): Promise<void>

// Discord upsert (new)
export async function upsertDiscordUser(
  client: SupabaseClient,
  discordId: bigint,
  username: string | undefined
): Promise<void>
```

The `formatSearchResults` handle priority:
1. Telegram `@username` (from `users.username`)
2. Discord `@username` (from `users.discord_username`)
3. Binder `username` column
4. `"unknown"`

---

## Discord Bot (`discord-bot/index.ts`)

### Interaction flow
Discord sends a `POST` to the Edge Function URL for every slash command interaction. The bot must:
1. Verify Ed25519 signature (Discord rejects bots that skip this — returns 401).
2. Respond to `PING` with `PONG` (Discord liveness check).
3. Route `APPLICATION_COMMAND` interactions to handlers by command name.
4. Return a JSON response body immediately (Discord requires response within 3 seconds).

### Commands
Same semantics as Telegram:

| Discord Command | Telegram equivalent | Notes |
|----------------|-------------------|-------|
| `/register <url>` | `/register <url>` | Validates against `BINDER_URL_RE` |
| `/mybinders` | `/mybinders` | Lists user's binders |
| `/removebinder <url>` | `/removebinder <url>` | Removes by URL |
| `/search <card>` | `/search <card>` | Returns formatted results |

### Response format
Discord slash commands return ephemeral or public messages. All responses use `type: 4` (`CHANNEL_MESSAGE_WITH_SOURCE`) and are public (visible in channel) to preserve the social discovery aspect.

---

## Ed25519 Signature Verification (`verify.ts`)

Discord requires every webhook request to include `X-Signature-Ed25519` and `X-Signature-Timestamp` headers. Verification uses the Web Crypto API (available in Deno):

```typescript
export async function verifyDiscordRequest(
  req: Request,
  publicKey: string,
  body: string
): Promise<boolean> {
  const signature = req.headers.get("X-Signature-Ed25519");
  const timestamp = req.headers.get("X-Signature-Timestamp");
  if (!signature || !timestamp) return false;

  const key = await crypto.subtle.importKey(
    "raw",
    hexToUint8Array(publicKey),
    { name: "Ed25519", namedCurve: "Ed25519" },
    false,
    ["verify"]
  );
  return crypto.subtle.verify(
    "Ed25519",
    key,
    hexToUint8Array(signature),
    new TextEncoder().encode(timestamp + body)
  );
}
```

---

## Environment Variables

| Variable | Used by | Value |
|----------|---------|-------|
| `TELEGRAM_BOT_TOKEN` | telegram-bot | existing |
| `DISCORD_PUBLIC_KEY` | discord-bot | from Discord Developer Portal |
| `DISCORD_APPLICATION_ID` | discord-bot setup script | for registering slash commands |
| `DISCORD_BOT_TOKEN` | discord-bot setup script | for registering slash commands |
| `SUPABASE_URL` | both | existing |
| `SUPABASE_SERVICE_ROLE_KEY` | both | existing |

---

## Slash Command Registration

Discord slash commands must be registered via the Discord API before they appear in the UI. A one-time setup script (`scripts/register_discord_commands.ts`) calls `https://discord.com/api/v10/applications/{id}/commands` to register the 4 commands. This is run once after deployment, not on every deploy.

---

## Testing

### Unit tests (`discord-bot/index.test.ts`)
- `verifyDiscordRequest` rejects missing headers
- `verifyDiscordRequest` rejects bad signature
- `/search` with no results returns correct message
- `/register` with invalid URL returns error message
- `formatSearchResults` with discord_username fallback

### Manual smoke test
1. Set webhook URL in Discord Developer Portal to the deployed Edge Function URL
2. Run `/search Black Lotus` in a Discord server — expect card list
3. Run `/register https://moxfield.com/binders/TEST` — expect confirmation
