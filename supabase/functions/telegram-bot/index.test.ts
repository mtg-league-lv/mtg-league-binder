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
