import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { upsertUser, formatBinderList, formatSearchResults } from "./utils.ts";

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
      upsert: (_row: unknown, _opts: unknown) => {
        return Promise.resolve({ error: fakeError });
      },
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

Deno.test("formatSearchResults produces correct output", () => {
  const results = [
    {
      card_name: "black lotus",
      quantity: 2,
      binders: { url: "https://moxfield.com/binders/AAA", users: { username: "alice" } },
    },
    {
      card_name: "black lotus",
      quantity: 1,
      binders: { url: "https://moxfield.com/binders/BBB", users: { username: null } },
    },
  ];
  const msg = formatSearchResults("Black Lotus", results);
  assertEquals(
    msg,
    "🃏 Black Lotus\n──────────────\n@alice — 2x\n🔗 https://moxfield.com/binders/AAA\n\nunknown — 1x\n🔗 https://moxfield.com/binders/BBB"
  );
});

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
