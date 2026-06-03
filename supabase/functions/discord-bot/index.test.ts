import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { verifyDiscordRequest, handleInteraction } from "./index.ts";

// ── verifyDiscordRequest ──────────────────────────────────────────────────────

Deno.test("verifyDiscordRequest accepts a valid signature", async () => {
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
    "a".repeat(128),
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

Deno.test("handleInteraction responds to PING with type 1", async () => {
  const res = await handleInteraction({ type: 1 }, null as never);
  const body = await res.json();
  assertEquals(body, { type: 1 });
});

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
  const inserted = (inserts[0] as { table: string; row: Record<string, unknown> }).row;
  assertEquals(inserted.url, "https://moxfield.com/binders/ABC123");
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
    from: (table: string) => {
      if (table === "users") {
        return {
          upsert: (_row: unknown, _opts: unknown) => Promise.resolve({ error: null }),
        };
      }
      return {
        select: (_cols: string) => ({
          eq: (_col: string, _val: unknown) => ({
            order: (_col2: string, _opts: unknown) =>
              Promise.resolve({ data: [], error: null }),
          }),
        }),
      };
    },
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
    from: (table: string) => {
      if (table === "users") {
        return {
          upsert: (_row: unknown, _opts: unknown) => Promise.resolve({ error: null }),
        };
      }
      return {
        select: (_cols: string) => ({
          eq: (_col: string, _val: unknown) => ({
            order: (_col2: string, _opts: unknown) =>
              Promise.resolve({ data: binderData, error: null }),
          }),
        }),
      };
    },
  };
  const interaction = makeInteraction("mybinders");
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("moxfield.com/binders/X1"), true);
});

// ── /removebinder ─────────────────────────────────────────────────────────────

Deno.test("/removebinder with valid URL removes and confirms", async () => {
  const fakeSupabase = {
    from: (table: string) => {
      if (table === "users") {
        return {
          upsert: (_row: unknown, _opts: unknown) => Promise.resolve({ error: null }),
        };
      }
      return {
        delete: (_opts: unknown) => ({
          eq: (_col: string, _val: unknown) => ({
            eq: (_col2: string, _val2: unknown) =>
              Promise.resolve({ error: null, count: 1 }),
          }),
        }),
      };
    },
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

Deno.test("/removebinder when binder not found replies with not-found message", async () => {
  const fakeSupabase = {
    from: (table: string) => {
      if (table === "users") {
        return {
          upsert: (_row: unknown, _opts: unknown) => Promise.resolve({ error: null }),
        };
      }
      return {
        delete: (_opts: unknown) => ({
          eq: (_col: string, _val: unknown) => ({
            eq: (_col2: string, _val2: unknown) =>
              Promise.resolve({ error: null, count: 0 }),
          }),
        }),
      };
    },
  };
  const interaction = makeInteraction("removebinder", [
    { name: "url", value: "https://moxfield.com/binders/NOTMINE" },
  ]);
  const res = await handleInteraction(interaction, fakeSupabase as never);
  const body = await res.json();
  assertEquals(body.data.content.includes("No binder found"), true);
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
