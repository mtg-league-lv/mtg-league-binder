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
