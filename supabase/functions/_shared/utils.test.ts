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

Deno.test("upsertUser uses null when username undefined", async () => {
  const calls: unknown[] = [];
  const fakeClient = {
    from: (_: string) => ({
      upsert: (row: unknown, _opts: unknown) => {
        calls.push(row);
        return Promise.resolve({ error: null });
      },
    }),
  };
  await upsertUser(fakeClient as never, 999, undefined);
  assertEquals(calls[0], { id: 999, username: null });
});

// ── upsertDiscordUser ─────────────────────────────────────────────────────────

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
  assertEquals((row.id as number) < 0, true);
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
  assertEquals((row.id as number) < 0, true);
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
    "🃏 Black Lotus\n──────────────\n[@alice](https://moxfield.com/binders/AAA) — 2x Black Lotus"
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
    "🃏 Black Lotus\n──────────────\n[@alice_dc](https://moxfield.com/binders/AAA) — 2x Black Lotus"
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
    "🃏 Black Lotus\n──────────────\n[Bob](https://moxfield.com/binders/BBB) — 1x Black Lotus\n\n[unknown](https://moxfield.com/binders/CCC) — 3x Black Lotus"
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
    "🃏 Black Lotus\n──────────────\n[Admin](https://moxfield.com/binders/DDD) — 1x Black Lotus"
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
