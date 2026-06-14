import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

// Supabase Edge Runtime global — keeps function alive after response is sent
declare const EdgeRuntime: { waitUntil(p: Promise<unknown>): void };
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
  return jsonResponse({ type: 4, data: { content, flags: 4 } });
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

// ── deferred follow-up ────────────────────────────────────────────────────────

async function editOriginalResponse(token: string, content: string): Promise<void> {
  const appId = Deno.env.get("DISCORD_APPLICATION_ID")!;
  await fetch(
    `https://discord.com/api/v10/webhooks/${appId}/${token}/messages/@original`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, flags: 4 }),
    }
  );
}

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

    // /mybinders
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

    // /removebinder
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

    // /search — deferred to avoid Discord's 3-second timeout
    if (commandName === "search") {
      const query = getOption(interaction, "query")?.trim();
      if (!query) {
        return reply("Usage: /search <card name>\nExample: /search Black Lotus");
      }
      if (query.length > 100) {
        return reply("Search query is too long (max 100 characters).");
      }
      const token = interaction.token as string;
      const searchPromise = (async () => {
        try {
          const escaped = query.toLowerCase().replace(/[%_\\]/g, "\\$&");
          const { data, error } = await supabase
            .from("binder_cards")
            .select("card_name, quantity, binders(url, username, users(username, discord_username))")
            .ilike("card_name", `%${escaped}%`)
            .order("card_name")
            .limit(50);
          if (error) throw error;
          const content = (!data || data.length === 0)
            ? `No binders found containing "${query}".`
            : formatSearchResults(query, data as Array<SearchResult>);
          await editOriginalResponse(token, content);
        } catch (e) {
          console.error("Search follow-up error:", e);
          await editOriginalResponse(token, "An error occurred while searching. Please try again.");
        }
      })();
      // Keep the Edge Function alive until the follow-up is sent.
      // EdgeRuntime is a Supabase global — declare it to avoid TS errors.
      // deno-lint-ignore no-explicit-any
      (EdgeRuntime as any).waitUntil(searchPromise);
      // Respond to Discord immediately with a deferred message ("is thinking…")
      return jsonResponse({ type: 5, data: { flags: 4 } });
    }

    return reply("Unknown command.");
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

  let interaction: Record<string, unknown>;
  try {
    interaction = JSON.parse(rawBody) as Record<string, unknown>;
  } catch {
    return new Response("Bad Request", { status: 400 });
  }
  try {
    return await handleInteraction(interaction, supabase);
  } catch (e) {
    console.error("Discord bot error:", e);
    return new Response(
      JSON.stringify({ type: 4, data: { content: "An internal error occurred. Please try again later." } }),
      { headers: { "Content-Type": "application/json" } }
    );
  }
});
