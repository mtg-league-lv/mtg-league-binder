import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

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
