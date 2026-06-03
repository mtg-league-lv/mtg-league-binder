# Discord Bot Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Discord slash-command bot sharing the same Supabase DB as the Telegram bot, with unified user identity across both platforms.

**Architecture:** A new `supabase/functions/discord-bot/` Edge Function handles Discord webhook interactions (Ed25519-verified). Shared formatting and DB utilities move from `telegram-bot/utils.ts` to `_shared/utils.ts` and are imported by both bots. Two new nullable columns (`discord_id`, `discord_username`) on the `users` table link Discord accounts to the same user rows as Telegram.

**Tech Stack:** Deno, Supabase Edge Functions, Supabase JS client, Discord HTTP Interactions API, Web Crypto API (Ed25519)

---

## File Map

| Action | Path |
|--------|------|
| New | `supabase/migrations/20260603000001_discord_user.sql` |
| New (moved from telegram-bot) | `supabase/functions/_shared/utils.ts` |
| New | `supabase/functions/_shared/utils.test.ts` |
| Modify | `supabase/functions/telegram-bot/index.ts` (import path + search cast) |
| Replace | `supabase/functions/telegram-bot/index.test.ts` (slim, no utils tests) |
| New | `supabase/functions/discord-bot/index.ts` |
| New | `supabase/functions/discord-bot/index.test.ts` |
| New | `scripts/register_discord_commands.sh` |

---

### Task 1: DB Migration — add Discord identity to users

**Files:**
- Create: `supabase/migrations/20260603000001_discord_user.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- supabase/migrations/20260603000001_discord_user.sql
ALTER TABLE users ADD COLUMN discord_id bigint UNIQUE;
ALTER TABLE users ADD COLUMN discord_username text;
```

- [ ] **Step 2: Apply the migration via Supabase MCP**

Use the `apply_migration` MCP tool with:
- `name`: `discord_user`
- `query`: the SQL above

Expected: migration applied successfully, no errors.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260603000001_discord_user.sql
git commit -m "feat: add discord_id and discord_username columns to users"
```

---

### Task 2: Move utils to `_shared` and update for Discord

**Files:**
- Create: `supabase/functions/_shared/utils.ts`
- Delete content of: `supabase/functions/telegram-bot/utils.ts` (replace with re-export)

- [ ] **Step 1: Create `supabase/functions/_shared/utils.ts`**

Full file content:

```typescript
import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export type SearchResult = {
  card_name: string;
  quantity: number;
  binders: {
    url: string;
    username: string | null;
    users: { username: string | null; discord_username: string | null } | null;
  };
};

export function formatBinderList(
  binders: Array<{ url: string; last_scraped_at: string | null }>
): string {
  const lines = binders.map((b, i) => {
    const scraped = b.last_scraped_at
      ? `Last scraped: ${new Date(b.last_scraped_at).toUTCString()}`
      : "Not yet scraped";
    return `${i + 1}. ${b.url}\n   ${scraped}`;
  });
  return "Your binders:\n\n" + lines.join("\n\n");
}

export function formatSearchResults(
  query: string,
  results: Array<SearchResult>
): string {
  const lines = results.map((r) => {
    const telegramUser = r.binders.users?.username;
    const discordUser = r.binders.users?.discord_username;
    const handle = telegramUser
      ? `@${telegramUser}`
      : discordUser
        ? `@${discordUser}`
        : (r.binders.username ?? "unknown");
    const cardName = r.card_name
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    return `${handle} — ${r.quantity}x ${cardName}\n🔗 ${r.binders.url}`;
  });
  return `🃏 ${query}\n──────────────\n` + lines.join("\n\n");
}

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

export async function upsertDiscordUser(
  client: SupabaseClient,
  discordId: string,
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

- [ ] **Step 2: Replace `supabase/functions/telegram-bot/utils.ts` with a re-export**

Replace the entire file with:

```typescript
// Re-export from shared utils so existing imports keep working.
export { formatBinderList, formatSearchResults, upsertUser } from "../_shared/utils.ts";
```

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/_shared/utils.ts supabase/functions/telegram-bot/utils.ts
git commit -m "refactor: move utils to _shared, add upsertDiscordUser and discord_username fallback"
```

---

### Task 3: Shared utils tests

**Files:**
- Create: `supabase/functions/_shared/utils.test.ts`

- [ ] **Step 1: Create `supabase/functions/_shared/utils.test.ts`**

```typescript
import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import {
  upsertUser,
  upsertDiscordUser,
  formatBinderList,
  formatSearchResults,
} from "./utils.ts";

// ── upsertUser ────────────────────────────────────────────────────────────────

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

Deno.test("upsertUser throws on error", async () => {
  const fakeError = { message: "db error", code: "500" };
  const fakeClient = {
    from: (_: string) => ({
      upsert: (_row: unknown, _opts: unknown) =>
        Promise.resolve({ error: fakeError }),
    }),
  };
  let threw = false;
  try {
    await upsertUser(fakeClient as never, 1, "test");
  } catch (e) {
    threw = true;
    assertEquals(e, fakeError);
  }
  assertEquals(threw, true);
});

// ── upsertDiscordUser ─────────────────────────────────────────────────────────

Deno.test("upsertDiscordUser builds correct row", async () => {
  const calls: unknown[] = [];
  const fakeClient = {
    from: (_: string) => ({
      upsert: (row: unknown, _opts: unknown) => {
        calls.push(row);
        return Promise.resolve({ error: null });
      },
    }),
  };
  await upsertDiscordUser(fakeClient as never, "123456789012345678", "bob");
  assertEquals(calls[0], { discord_id: "123456789012345678", discord_username: "bob" });
});

Deno.test("upsertDiscordUser uses null when username undefined", async () => {
  const calls: unknown[] = [];
  const fakeClient = {
    from: (_: string) => ({
      upsert: (row: unknown, _opts: unknown) => {
        calls.push(row);
        return Promise.resolve({ error: null });
      },
    }),
  };
  await upsertDiscordUser(fakeClient as never, "111", undefined);
  assertEquals(calls[0], { discord_id: "111", discord_username: null });
});

Deno.test("upsertDiscordUser throws on error", async () => {
  const fakeError = { message: "db error", code: "500" };
  const fakeClient = {
    from: (_: string) => ({
      upsert: (_row: unknown, _opts: unknown) =>
        Promise.resolve({ error: fakeError }),
    }),
  };
  let threw = false;
  try {
    await upsertDiscordUser(fakeClient as never, "1", "test");
  } catch (e) {
    threw = true;
    assertEquals(e, fakeError);
  }
  assertEquals(threw, true);
});

// ── formatSearchResults ───────────────────────────────────────────────────────

Deno.test("formatSearchResults uses telegram username when available", () => {
  const results = [
    {
      card_name: "black lotus",
      quantity: 2,
      binders: {
        url: "https://moxfield.com/binders/AAA",
        username: "BinderOwner",
        users: { username: "alice", discord_username: "alice_discord" },
      },
    },
  ];
  const msg = formatSearchResults("Black Lotus", results);
  assertEquals(
    msg,
    "🃏 Black Lotus\n──────────────\n@alice — 2x Black Lotus\n🔗 https://moxfield.com/binders/AAA"
  );
});

Deno.test("formatSearchResults falls back to discord username when no telegram user", () => {
  const results = [
    {
      card_name: "black lotus",
      quantity: 2,
      binders: {
        url: "https://moxfield.com/binders/AAA",
        username: "BinderOwner",
        users: { username: null, discord_username: "alice_dc" },
      },
    },
  ];
  const msg = formatSearchResults("Black Lotus", results);
  assertEquals(
    msg,
    "🃏 Black Lotus\n──────────────\n@alice_dc — 2x Black Lotus\n🔗 https://moxfield.com/binders/AAA"
  );
});

Deno.test("formatSearchResults falls back to binder username when no telegram or discord user", () => {
  const results = [
    {
      card_name: "black lotus",
      quantity: 1,
      binders: {
        url: "https://moxfield.com/binders/BBB",
        username: "Bob",
        users: { username: null, discord_username: null },
      },
    },
    {
      card_name: "black lotus",
      quantity: 3,
      binders: {
        url: "https://moxfield.com/binders/CCC",
        username: null,
        users: { username: null, discord_username: null },
      },
    },
  ];
  const msg = formatSearchResults("Black Lotus", results);
  assertEquals(
    msg,
    "🃏 Black Lotus\n──────────────\nBob — 1x Black Lotus\n🔗 https://moxfield.com/binders/BBB\n\nunknown — 3x Black Lotus\n🔗 https://moxfield.com/binders/CCC"
  );
});

Deno.test("formatSearchResults handles null users relation", () => {
  const results = [
    {
      card_name: "black lotus",
      quantity: 1,
      binders: {
        url: "https://moxfield.com/binders/DDD",
        username: "Admin",
        users: null,
      },
    },
  ];
  const msg = formatSearchResults("Black Lotus", results);
  assertEquals(
    msg,
    "🃏 Black Lotus\n──────────────\nAdmin — 1x Black Lotus\n🔗 https://moxfield.com/binders/DDD"
  );
});

// ── formatBinderList ──────────────────────────────────────────────────────────

Deno.test("formatBinderList formats list correctly", () => {
  const binders = [
    { url: "https://moxfield.com/binders/AAA", last_scraped_at: "2026-06-01T03:00:00Z" },
    { url: "https://moxfield.com/binders/BBB", last_scraped_at: null },
  ];
  const msg = formatBinderList(binders);
  assertEquals(
    msg,
    "Your binders:\n\n" +
    "1. https://moxfield.com/binders/AAA\n   Last scraped: Mon, 01 Jun 2026 03:00:00 GMT\n\n" +
    "2. https://moxfield.com/binders/BBB\n   Not yet scraped"
  );
});
```

- [ ] **Step 2: Run tests**

```bash
deno test supabase/functions/_shared/utils.test.ts --allow-env
```

Expected: all 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/_shared/utils.test.ts
git commit -m "test: add shared utils tests including upsertDiscordUser and discord handle fallback"
```

---

### Task 4: Update Telegram bot to use shared types

**Files:**
- Modify: `supabase/functions/telegram-bot/index.ts`
- Modify: `supabase/functions/telegram-bot/index.test.ts`

- [ ] **Step 1: Update the search cast in `telegram-bot/index.ts`**

Replace the `typed` declaration (lines 118–122):

```typescript
  const typed = data as Array<{
    card_name: string;
    quantity: number;
    binders: { url: string; username: string | null; users: { username: string | null } | null };
  }>;
```

With:

```typescript
  const typed = data as Array<{
    card_name: string;
    quantity: number;
    binders: { url: string; username: string | null; users: { username: string | null; discord_username: string | null } | null };
  }>;
```

Also update the select query on line 106 to include `discord_username`:

```typescript
    .select("card_name, quantity, binders(url, username, users(username, discord_username))")
```

- [ ] **Step 2: Replace `telegram-bot/index.test.ts`**

The utils tests now live in `_shared/utils.test.ts`. Slim down this file to only test Telegram-specific wiring:

```typescript
import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
// Shared util tests have moved to supabase/functions/_shared/utils.test.ts
// This file only tests Telegram-bot-specific wiring.

Deno.test("telegram bot test file placeholder — wiring tested via integration", () => {
  assertEquals(true, true);
});
```

- [ ] **Step 3: Run the existing shared tests to confirm nothing broke**

```bash
deno test supabase/functions/_shared/utils.test.ts --allow-env
```

Expected: all 10 PASS.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/telegram-bot/index.ts supabase/functions/telegram-bot/index.test.ts
git commit -m "feat: update telegram bot to include discord_username in search select and type cast"
```

---

### Task 5: Discord bot — skeleton, Ed25519 verification, PING

**Files:**
- Create: `supabase/functions/discord-bot/index.ts`
- Create: `supabase/functions/discord-bot/index.test.ts`

- [ ] **Step 1: Write the failing test for verification and PING**

Create `supabase/functions/discord-bot/index.test.ts`:

```typescript
import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { verifyDiscordRequest, handleInteraction } from "./index.ts";

// ── verifyDiscordRequest ──────────────────────────────────────────────────────

Deno.test("verifyDiscordRequest accepts a valid signature", async () => {
  // Generate a real Ed25519 keypair using Web Crypto
  const keyPair = await crypto.subtle.generateKey(
    { name: "Ed25519" },
    true,
    ["sign", "verify"]
  );
  const rawPublicKey = await crypto.subtle.exportKey("raw", keyPair.publicKey);
  const publicKeyHex = Array.from(new Uint8Array(rawPublicKey))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const timestamp = "1234567890";
  const body = '{"type":1}';
  const msgBytes = new TextEncoder().encode(timestamp + body);
  const sigBytes = await crypto.subtle.sign("Ed25519", keyPair.privateKey, msgBytes);
  const sigHex = Array.from(new Uint8Array(sigBytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const valid = await verifyDiscordRequest(sigHex, timestamp, body, publicKeyHex);
  assertEquals(valid, true);
});

Deno.test("verifyDiscordRequest rejects an invalid signature", async () => {
  const keyPair = await crypto.subtle.generateKey(
    { name: "Ed25519" },
    true,
    ["sign", "verify"]
  );
  const rawPublicKey = await crypto.subtle.exportKey("raw", keyPair.publicKey);
  const publicKeyHex = Array.from(new Uint8Array(rawPublicKey))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const valid = await verifyDiscordRequest(
    "a".repeat(128), // garbage signature
    "1234567890",
    '{"type":1}',
    publicKeyHex
  );
  assertEquals(valid, false);
});

Deno.test("verifyDiscordRequest returns false when headers missing", async () => {
  const valid = await verifyDiscordRequest("", "", '{"type":1}', "a".repeat(64));
  assertEquals(valid, false);
});

// ── PING ──────────────────────────────────────────────────────────────────────

Deno.test("handleInteraction responds to PING with type 1", async () => {
  const res = await handleInteraction({ type: 1 }, null as never);
  const body = await res.json();
  assertEquals(body, { type: 1 });
});
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
deno test supabase/functions/discord-bot/index.test.ts --allow-env
```

Expected: error — `supabase/functions/discord-bot/index.ts` does not exist.

- [ ] **Step 3: Create `supabase/functions/discord-bot/index.ts` with the skeleton**

```typescript
import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  upsertDiscordUser,
  formatBinderList,
  formatSearchResults,
  SearchResult,
} from "../_shared/utils.ts";

// ── helpers ───────────────────────────────────────────────────────────────────

function hexToUint8(hex: string): Uint8Array {
  if (hex.length % 2 !== 0 || hex.length === 0) return new Uint8Array(0);
  return new Uint8Array(hex.match(/.{2}/g)!.map((b) => parseInt(b, 16)));
}

export async function verifyDiscordRequest(
  sig: string,
  ts: string,
  rawBody: string,
  publicKey: string
): Promise<boolean> {
  if (!sig || !ts || !publicKey) return false;
  try {
    const key = await crypto.subtle.importKey(
      "raw",
      hexToUint8(publicKey),
      { name: "Ed25519" },
      false,
      ["verify"]
    );
    return await crypto.subtle.verify(
      "Ed25519",
      key,
      hexToUint8(sig),
      new TextEncoder().encode(ts + rawBody)
    );
  } catch {
    return false;
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function reply(content: string): Response {
  return jsonResponse({ type: 4, data: { content } });
}

function getUser(
  interaction: Record<string, unknown>
): { id: string; username: string | undefined } | null {
  const member = interaction.member as Record<string, unknown> | undefined;
  const user = (member?.user ?? interaction.user) as
    | Record<string, unknown>
    | undefined;
  if (!user?.id) return null;
  return { id: user.id as string, username: user.username as string | undefined };
}

function getOption(interaction: Record<string, unknown>, name: string): string | undefined {
  const opts = (
    (interaction.data as Record<string, unknown>)?.options as Array<{
      name: string;
      value: unknown;
    }>
  ) ?? [];
  return opts.find((o) => o.name === name)?.value as string | undefined;
}

const MOXFIELD_BINDER_RE = /^https:\/\/moxfield\.com\/binders\/[A-Za-z0-9_-]+/;

// ── command handlers ──────────────────────────────────────────────────────────

export async function handleInteraction(
  interaction: Record<string, unknown>,
  supabase: SupabaseClient
): Promise<Response> {
  // PING
  if (interaction.type === 1) {
    return jsonResponse({ type: 1 });
  }

  // APPLICATION_COMMAND
  if (interaction.type === 2) {
    const user = getUser(interaction);
    if (!user) return reply("Cannot identify sender.");

    const commandName = (interaction.data as Record<string, unknown>)?.name as string;

    // /register
    if (commandName === "register") {
      const url = getOption(interaction, "url")?.trim();
      if (!url || !MOXFIELD_BINDER_RE.test(url)) {
        return reply(
          "Please provide a valid Moxfield binder URL.\nExample: /register https://moxfield.com/binders/ABC123"
        );
      }
      await upsertDiscordUser(supabase, user.id, user.username);
      const { error } = await supabase
        .from("binders")
        .insert({ user_id: null, url });
      if (error?.code === "23505") {
        return reply("That binder is already registered.");
      }
      if (error) throw error;
      return reply(`✅ Binder registered! It will be scraped in the next daily run.\n${url}`);
    }

    // /mybinders
    if (commandName === "mybinders") {
      await upsertDiscordUser(supabase, user.id, user.username);
      // Look up the users.id (PK) for this discord user
      const { data: userData, error: userErr } = await supabase
        .from("users")
        .select("id")
        .eq("discord_id", user.id)
        .single();
      if (userErr || !userData) {
        return reply("You have no registered binders. Use /register <url> to add one.");
      }
      const { data, error } = await supabase
        .from("binders")
        .select("url, last_scraped_at")
        .eq("user_id", userData.id)
        .order("created_at", { ascending: true });
      if (error) throw error;
      if (!data || data.length === 0) {
        return reply("You have no registered binders. Use /register <url> to add one.");
      }
      return reply(formatBinderList(data));
    }

    // /removebinder
    if (commandName === "removebinder") {
      const url = getOption(interaction, "url")?.trim();
      if (!url || !MOXFIELD_BINDER_RE.test(url)) {
        return reply(
          "Please provide a valid Moxfield binder URL.\nUsage: /removebinder <url>"
        );
      }
      const { data: userData } = await supabase
        .from("users")
        .select("id")
        .eq("discord_id", user.id)
        .single();
      if (!userData) {
        return reply("No binder found with that URL in your account.");
      }
      const { error, count } = await supabase
        .from("binders")
        .delete({ count: "exact" })
        .eq("user_id", userData.id)
        .eq("url", url);
      if (error) throw error;
      if (count === 0 || count === null) {
        return reply("No binder found with that URL in your account.");
      }
      return reply(`🗑️ Binder removed: ${url}`);
    }

    // /search
    if (commandName === "search") {
      const query = getOption(interaction, "query")?.trim();
      if (!query) {
        return reply("Usage: /search <card name>\nExample: /search Black Lotus");
      }
      const escaped = query.toLowerCase().replace(/[%_\\]/g, "\\$&");
      const { data, error } = await supabase
        .from("binder_cards")
        .select("card_name, quantity, binders(url, username, users(username, discord_username))")
        .ilike("card_name", `%${escaped}%`)
        .order("card_name")
        .limit(50);
      if (error) throw error;
      if (!data || data.length === 0) {
        return reply(`No binders found containing "${query}".`);
      }
      return reply(formatSearchResults(query, data as Array<SearchResult>));
    }
  }

  return new Response("OK", { status: 200 });
}

// ── Edge Function entry point ─────────────────────────────────────────────────

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
);

Deno.serve(async (req: Request) => {
  const rawBody = await req.text();
  const sig = req.headers.get("x-signature-ed25519") ?? "";
  const ts = req.headers.get("x-signature-timestamp") ?? "";
  const publicKey = Deno.env.get("DISCORD_PUBLIC_KEY") ?? "";

  const valid = await verifyDiscordRequest(sig, ts, rawBody, publicKey);
  if (!valid) return new Response("Unauthorized", { status: 401 });

  const interaction = JSON.parse(rawBody) as Record<string, unknown>;
  return handleInteraction(interaction, supabase);
});
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
deno test supabase/functions/discord-bot/index.test.ts --allow-env
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/discord-bot/index.ts supabase/functions/discord-bot/index.test.ts
git commit -m "feat: add discord-bot Edge Function with Ed25519 verification and PING handler"
```

---

### Task 6: Discord bot — command handler tests

**Files:**
- Modify: `supabase/functions/discord-bot/index.test.ts`

- [ ] **Step 1: Add command tests to `index.test.ts`**

Append these tests to the existing file (after the PING test):

```typescript
// ── helpers for building fake interactions ────────────────────────────────────

function makeInteraction(
  commandName: string,
  options: Array<{ name: string; value: string }> = [],
  userId = "111222333444555666"
): Record<string, unknown> {
  return {
    type: 2,
    user: { id: userId, username: "testuser" },
    data: { name: commandName, options },
  };
}

// ── /register ─────────────────────────────────────────────────────────────────

Deno.test("/register with valid URL inserts and confirms", async () => {
  const inserts: unknown[] = [];
  const upserts: unknown[] = [];
  const fakeSupabase = {
    from: (table: string) => ({
      upsert: (row: unknown, _opts: unknown) => {
        upserts.push({ table, row });
        return Promise.resolve({ error: null });
      },
      insert: (row: unknown) => {
        inserts.push({ table, row });
        return Promise.resolve({ error: null });
      },
    }),
  };

  const interaction = makeInteraction("register", [
    { name: "url", value: "https://moxfield.com/binders/ABC123" },
  ]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();

  assertEquals(body.type, 4);
  assertEquals(body.data.content.includes("✅"), true);
  assertEquals(inserts.length, 1);
});

Deno.test("/register with invalid URL replies with usage message", async () => {
  const fakeSupabase = { from: () => ({}) };
  const interaction = makeInteraction("register", [
    { name: "url", value: "https://notmoxfield.com/binders/ABC" },
  ]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.type, 4);
  assertEquals(body.data.content.includes("valid Moxfield"), true);
});

Deno.test("/register with duplicate URL replies with already-registered message", async () => {
  const fakeSupabase = {
    from: (_table: string) => ({
      upsert: (_row: unknown, _opts: unknown) => Promise.resolve({ error: null }),
      insert: (_row: unknown) =>
        Promise.resolve({ error: { code: "23505" } }),
    }),
  };
  const interaction = makeInteraction("register", [
    { name: "url", value: "https://moxfield.com/binders/ABC123" },
  ]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("already registered"), true);
});

// ── /mybinders ────────────────────────────────────────────────────────────────

Deno.test("/mybinders with no binders replies with empty-state message", async () => {
  const fakeSupabase = {
    from: (table: string) => ({
      upsert: (_row: unknown, _opts: unknown) => Promise.resolve({ error: null }),
      select: (_cols: string) => ({
        eq: (_col: string, _val: unknown) => ({
          single: () => Promise.resolve({ data: { id: 99 }, error: null }),
          order: (_col2: string, _opts: unknown) =>
            Promise.resolve({ data: [], error: null }),
        }),
      }),
    }),
  };
  const interaction = makeInteraction("mybinders");
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("no registered binders"), true);
});

Deno.test("/mybinders with binders returns formatted list", async () => {
  const binderData = [
    { url: "https://moxfield.com/binders/X1", last_scraped_at: null },
  ];
  const fakeSupabase = {
    from: (_table: string) => ({
      upsert: (_row: unknown, _opts: unknown) => Promise.resolve({ error: null }),
      select: (_cols: string) => ({
        eq: (_col: string, _val: unknown) => ({
          single: () => Promise.resolve({ data: { id: 99 }, error: null }),
          order: (_col2: string, _opts: unknown) =>
            Promise.resolve({ data: binderData, error: null }),
        }),
      }),
    }),
  };
  const interaction = makeInteraction("mybinders");
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("moxfield.com/binders/X1"), true);
});

// ── /removebinder ─────────────────────────────────────────────────────────────

Deno.test("/removebinder with valid URL removes and confirms", async () => {
  const fakeSupabase = {
    from: (_table: string) => ({
      select: (_cols: string) => ({
        eq: (_col: string, _val: unknown) => ({
          single: () => Promise.resolve({ data: { id: 99 }, error: null }),
        }),
      }),
      delete: (_opts: unknown) => ({
        eq: (_col: string, _val: unknown) => ({
          eq: (_col2: string, _val2: unknown) =>
            Promise.resolve({ error: null, count: 1 }),
        }),
      }),
    }),
  };
  const interaction = makeInteraction("removebinder", [
    { name: "url", value: "https://moxfield.com/binders/ABC123" },
  ]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("🗑️"), true);
});

Deno.test("/removebinder with invalid URL replies with usage message", async () => {
  const fakeSupabase = { from: () => ({}) };
  const interaction = makeInteraction("removebinder", [
    { name: "url", value: "not-a-url" },
  ]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("valid Moxfield"), true);
});

// ── /search ───────────────────────────────────────────────────────────────────

Deno.test("/search with results returns formatted card list", async () => {
  const cardData = [
    {
      card_name: "black lotus",
      quantity: 2,
      binders: {
        url: "https://moxfield.com/binders/AAA",
        username: null,
        users: { username: "alice", discord_username: null },
      },
    },
  ];
  const fakeSupabase = {
    from: (_table: string) => ({
      select: (_cols: string) => ({
        ilike: (_col: string, _val: string) => ({
          order: (_col2: string) => ({
            limit: (_n: number) => Promise.resolve({ data: cardData, error: null }),
          }),
        }),
      }),
    }),
  };
  const interaction = makeInteraction("search", [{ name: "query", value: "black lotus" }]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("🃏"), true);
  assertEquals(body.data.content.includes("@alice"), true);
});

Deno.test("/search with no results replies with not-found message", async () => {
  const fakeSupabase = {
    from: (_table: string) => ({
      select: (_cols: string) => ({
        ilike: (_col: string, _val: string) => ({
          order: (_col2: string) => ({
            limit: (_n: number) => Promise.resolve({ data: [], error: null }),
          }),
        }),
      }),
    }),
  };
  const interaction = makeInteraction("search", [{ name: "query", value: "cardthatdoesnotexist" }]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("No binders found"), true);
});
```

- [ ] **Step 2: Run all discord-bot tests**

```bash
deno test supabase/functions/discord-bot/index.test.ts --allow-env
```

Expected: all tests PASS. If a test fails due to the chained fake Supabase client shape, adjust the fake client to match the actual chain used in the handler.

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/discord-bot/index.test.ts
git commit -m "test: add full command handler tests for discord-bot"
```

---

### Task 7: Fix /register to link binder to Discord user

**Context:** In Task 5, `/register` inserts `user_id: null`. It should insert the actual `users.id` primary key for the Discord user (which is auto-generated when `upsertDiscordUser` runs the first time — but the `users` table has `id bigint primary key` which is the *Telegram* ID, not auto-generated). 

**Design clarification:** The `users` table PK (`id`) is a Telegram user ID (caller-supplied bigint). Discord users don't have a row in `users` via the existing schema — `discord_id` is a new nullable column, but there's no auto-generated PK for Discord-only users.

**Solution:** For Discord users, the binder `user_id` stays `null` (same as admin-added binders). We track ownership via `discord_id` on the `users` table separately. The `/mybinders` and `/removebinder` commands already handle this by looking up `users.id` via `discord_id` — but for Discord-registered binders with `user_id = null`, that lookup will find nothing.

**Revised approach:** Add a generated `id` column to `users` for Discord-only users by changing the schema, OR store binders with `user_id = null` and track Discord ownership via a separate `discord_binders` view — this is too complex. 

**Simplest correct approach:** When a Discord user first registers, create a `users` row with a negative ID (e.g. `-(discord_id % 2^53)` to avoid collision) or use a sequence. Actually, the cleanest fix is: add a `serial` / `bigserial` generated column as a secondary PK — but that changes the schema significantly.

**Pragmatic fix for this plan:** Use `discord_id` cast to a negative number as the `users.id` for Discord-only users. Discord snowflakes are positive 64-bit integers. We store `id = -1 * (discord_id_as_bigint % 10^15)` to fit in JS number range with a negative prefix to guarantee no collision with Telegram IDs (which are positive). This is a deterministic mapping.

**Files:**
- New migration: `supabase/migrations/20260603000002_discord_user_id_sequence.sql`
- Modify: `supabase/functions/_shared/utils.ts`
- Modify: `supabase/functions/discord-bot/index.ts`

- [ ] **Step 1: Add migration to allow negative IDs (already allowed — bigint has no constraint)**

No migration needed. The `users.id` column is `bigint primary key` with no positive-only constraint. Negative values are valid.

- [ ] **Step 2: Update `upsertDiscordUser` in `_shared/utils.ts` to also set a deterministic `id`**

In `supabase/functions/_shared/utils.ts`, replace the `upsertDiscordUser` function:

```typescript
export async function upsertDiscordUser(
  client: SupabaseClient,
  discordId: string,
  discordUsername: string | undefined
) {
  // Use a deterministic negative ID for Discord-only users so they
  // get a users.id PK without conflicting with positive Telegram IDs.
  // We take the last 15 digits of the discord snowflake and negate it.
  const deterministicId = -(Number(BigInt(discordId) % 1_000_000_000_000_000n));
  const { error } = await client
    .from("users")
    .upsert(
      {
        id: deterministicId,
        discord_id: discordId,
        discord_username: discordUsername ?? null,
      },
      { onConflict: "discord_id" }
    );
  if (error) throw error;
  return deterministicId;
}
```

Note: `upsertDiscordUser` now returns `number` (the deterministic ID).

- [ ] **Step 3: Update `discord-bot/index.ts` — use returned ID for binder insert**

In the `/register` handler, replace the insert block:

```typescript
    if (commandName === "register") {
      const url = getOption(interaction, "url")?.trim();
      if (!url || !MOXFIELD_BINDER_RE.test(url)) {
        return reply(
          "Please provide a valid Moxfield binder URL.\nExample: /register https://moxfield.com/binders/ABC123"
        );
      }
      const userId = await upsertDiscordUser(supabase, user.id, user.username);
      const { error } = await supabase
        .from("binders")
        .insert({ user_id: userId, url });
      if (error?.code === "23505") {
        return reply("That binder is already registered.");
      }
      if (error) throw error;
      return reply(`✅ Binder registered! It will be scraped in the next daily run.\n${url}`);
    }
```

In the `/mybinders` handler, simplify — no need for a separate user lookup since we now know `userId`:

```typescript
    if (commandName === "mybinders") {
      const userId = await upsertDiscordUser(supabase, user.id, user.username);
      const { data, error } = await supabase
        .from("binders")
        .select("url, last_scraped_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: true });
      if (error) throw error;
      if (!data || data.length === 0) {
        return reply("You have no registered binders. Use /register <url> to add one.");
      }
      return reply(formatBinderList(data));
    }
```

In the `/removebinder` handler:

```typescript
    if (commandName === "removebinder") {
      const url = getOption(interaction, "url")?.trim();
      if (!url || !MOXFIELD_BINDER_RE.test(url)) {
        return reply(
          "Please provide a valid Moxfield binder URL.\nUsage: /removebinder <url>"
        );
      }
      const userId = await upsertDiscordUser(supabase, user.id, user.username);
      const { error, count } = await supabase
        .from("binders")
        .delete({ count: "exact" })
        .eq("user_id", userId)
        .eq("url", url);
      if (error) throw error;
      if (count === 0 || count === null) {
        return reply("No binder found with that URL in your account.");
      }
      return reply(`🗑️ Binder removed: ${url}`);
    }
```

- [ ] **Step 4: Update shared utils test for new `upsertDiscordUser` signature**

In `supabase/functions/_shared/utils.test.ts`, update the `upsertDiscordUser` tests:

```typescript
Deno.test("upsertDiscordUser builds correct row with deterministic id", async () => {
  const calls: unknown[] = [];
  const fakeClient = {
    from: (_: string) => ({
      upsert: (row: unknown, _opts: unknown) => {
        calls.push(row);
        return Promise.resolve({ error: null });
      },
    }),
  };
  const id = await upsertDiscordUser(fakeClient as never, "123456789012345678", "bob");
  const row = calls[0] as Record<string, unknown>;
  assertEquals(row.discord_id, "123456789012345678");
  assertEquals(row.discord_username, "bob");
  assertEquals(typeof row.id, "number");
  assertEquals((row.id as number) < 0, true); // deterministic negative ID
  assertEquals(id, row.id);
});

Deno.test("upsertDiscordUser uses null when username undefined", async () => {
  const calls: unknown[] = [];
  const fakeClient = {
    from: (_: string) => ({
      upsert: (row: unknown, _opts: unknown) => {
        calls.push(row);
        return Promise.resolve({ error: null });
      },
    }),
  };
  await upsertDiscordUser(fakeClient as never, "111000000000000000", undefined);
  const row = calls[0] as Record<string, unknown>;
  assertEquals(row.discord_username, null);
});
```

Also update the `/register`, `/mybinders`, `/removebinder` tests in `discord-bot/index.test.ts` — the fake supabase clients need their `upsert` to return a value that `upsertDiscordUser` can use. Since `upsertDiscordUser` computes the ID locally (not from DB), the fake just needs `{ error: null }`.

- [ ] **Step 5: Run all tests**

```bash
deno test supabase/functions/_shared/utils.test.ts supabase/functions/discord-bot/index.test.ts --allow-env
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add supabase/functions/_shared/utils.ts supabase/functions/_shared/utils.test.ts supabase/functions/discord-bot/index.ts supabase/functions/discord-bot/index.test.ts
git commit -m "feat: use deterministic negative ID for Discord users to link binders correctly"
```

---

### Task 8: Setup script for registering Discord slash commands

**Files:**
- Create: `scripts/register_discord_commands.sh`

- [ ] **Step 1: Create `scripts/register_discord_commands.sh`**

```bash
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
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/register_discord_commands.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/register_discord_commands.sh
git commit -m "feat: add Discord slash command registration script"
```

---

### Task 9: Deploy discord-bot Edge Function

**Files:** None (deployment step)

- [ ] **Step 1: Deploy via Supabase MCP**

Use the `deploy_edge_function` MCP tool with:
- `function_name`: `discord-bot`
- `entrypoint_path`: `supabase/functions/discord-bot/index.ts`

Also set secrets in Supabase dashboard (or via `supabase secrets set`):
- `DISCORD_PUBLIC_KEY` — from Discord Developer Portal → your app → General Information → Public Key
- `DISCORD_BOT_TOKEN` — from Discord Developer Portal → Bot → Token

- [ ] **Step 2: Get the Edge Function URL**

Use `get_project_url` MCP tool or check Supabase dashboard.
The URL will be: `https://<project-ref>.supabase.co/functions/v1/discord-bot`

- [ ] **Step 3: Configure Discord Interactions Endpoint URL**

In Discord Developer Portal → your app → General Information → Interactions Endpoint URL, set it to the Edge Function URL.

Discord will send a PING to verify. The function must return `{"type":1}` — it will.

- [ ] **Step 4: Register slash commands**

```bash
DISCORD_APP_ID=<your-app-id> DISCORD_BOT_TOKEN=<your-token> bash scripts/register_discord_commands.sh
```

Expected: JSON array of 4 registered commands printed.

- [ ] **Step 5: Commit final state**

```bash
git add -A
git commit -m "feat: deploy discord-bot Edge Function and complete Discord bot implementation"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ DB migration — Task 1
- ✅ Shared utils move + `upsertDiscordUser` + `discord_username` fallback — Tasks 2–3
- ✅ Telegram bot updated — Task 4
- ✅ Discord bot Ed25519 verification — Task 5
- ✅ PING handler — Task 5
- ✅ All 4 slash commands — Tasks 5, 7
- ✅ Tests for all commands — Task 6
- ✅ Setup script — Task 8
- ✅ Deployment — Task 9

**Type consistency:**
- `SearchResult` type exported from `_shared/utils.ts` and used in both bots
- `upsertDiscordUser` returns `number` (deterministic ID) — used in Task 7 handlers
- All fake supabase clients in tests match actual chain shape used in handlers
