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
    const scryfallUrl = `https://scryfall.com/search?q=%21%22${cardName.split(" ").join("+")}%22`;
    return `[${handle}](${r.binders.url}) — ${r.quantity}x [${cardName}](${scryfallUrl})`;
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
): Promise<number> {
  // Derive a deterministic negative integer ID for Discord-only users.
  // Discord snowflakes are positive 64-bit integers. We take the last 15
  // digits mod 10^15 and negate, guaranteeing no collision with positive
  // Telegram IDs. This is stable across calls for the same discord ID.
  const mod = Number(BigInt(discordId) % 1_000_000_000_000_000n);
  const deterministicId = -(mod === 0 ? 1 : mod);
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
