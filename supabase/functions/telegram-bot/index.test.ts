import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { upsertUser } from "./utils.ts";

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
