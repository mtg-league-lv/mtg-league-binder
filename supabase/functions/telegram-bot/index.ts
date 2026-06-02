import { Bot, webhookCallback } from "npm:grammy@1.21.1";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { upsertUser, formatBinderList, formatSearchResults } from "./utils.ts";

const bot = new Bot(Deno.env.get("TELEGRAM_BOT_TOKEN")!);

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
);

bot.command("start", async (ctx) => {
  if (!ctx.from) {
    await ctx.reply("Cannot identify sender.");
    return;
  }
  await upsertUser(supabase, ctx.from.id, ctx.from.username);
  await ctx.reply(
    "👋 Welcome to League Binder Bot!\n\n" +
    "Commands:\n" +
    "/register <moxfield_binder_url> — Add your binder\n" +
    "/mybinders — List your registered binders\n" +
    "/removebinder <url> — Remove a binder\n" +
    "/search <card name> — Find binders containing a card"
  );
});

const MOXFIELD_BINDER_RE = /^https:\/\/moxfield\.com\/binders\/[A-Za-z0-9_-]+/;

bot.command("register", async (ctx) => {
  if (!ctx.from) {
    await ctx.reply("Cannot identify sender.");
    return;
  }
  const url = ctx.match?.trim();
  if (!url || !MOXFIELD_BINDER_RE.test(url)) {
    await ctx.reply("Please provide a valid Moxfield binder URL.\nExample: /register https://moxfield.com/binders/ABC123");
    return;
  }
  await upsertUser(supabase, ctx.from.id, ctx.from.username);
  const { error } = await supabase
    .from("binders")
    .insert({ user_id: ctx.from.id, url });
  if (error?.code === "23505") {
    await ctx.reply("That binder is already registered to your account.");
    return;
  }
  if (error) throw error;
  await ctx.reply(`✅ Binder registered! It will be scraped in the next daily run.\n${url}`);
});

bot.command("mybinders", async (ctx) => {
  if (!ctx.from) { await ctx.reply("Cannot identify sender."); return; }

  const { data, error } = await supabase
    .from("binders")
    .select("url, last_scraped_at")
    .eq("user_id", ctx.from.id)
    .order("created_at", { ascending: true });
  if (error) throw error;

  if (!data || data.length === 0) {
    await ctx.reply("You have no registered binders. Use /register <url> to add one.");
    return;
  }

  await ctx.reply(formatBinderList(data));
});

bot.command("removebinder", async (ctx) => {
  if (!ctx.from) { await ctx.reply("Cannot identify sender."); return; }

  const url = ctx.match?.trim();
  if (!url || !MOXFIELD_BINDER_RE.test(url)) {
    await ctx.reply("Please provide a valid Moxfield binder URL.\nUsage: /removebinder <url>\nTip: use /mybinders to see your registered binders.");
    return;
  }

  const { error, count } = await supabase
    .from("binders")
    .delete({ count: "exact" })
    .eq("user_id", ctx.from.id)
    .eq("url", url);

  if (error) throw error;

  if (count === 0 || count === null) {
    await ctx.reply("No binder found with that URL in your account.");
  } else {
    await ctx.reply(`🗑️ Binder removed: ${url}`);
  }
});

bot.command("search", async (ctx) => {
  if (!ctx.from) { await ctx.reply("Cannot identify sender."); return; }

  const query = ctx.match?.trim();
  if (!query) {
    await ctx.reply("Usage: /search <card name>\nExample: /search Black Lotus");
    return;
  }

  const escaped = query.toLowerCase().replace(/[%_\\]/g, "\\$&");
  const { data, error } = await supabase
    .from("binder_cards")
    .select("card_name, quantity, binders(url, users(username))")
    .ilike("card_name", `%${escaped}%`)
    .order("card_name")
    .limit(50);

  if (error) throw error;

  if (!data || data.length === 0) {
    await ctx.reply(`No binders found containing "${query}".`);
    return;
  }

  const typed = data as Array<{
    card_name: string;
    quantity: number;
    binders: { url: string; users: { username: string | null } };
  }>;

  await ctx.reply(formatSearchResults(query, typed));
});

bot.catch((err) => {
  console.error("Bot error:", err);
});

const handleUpdate = webhookCallback(bot, "std/http");

Deno.serve(async (req: Request) => {
  if (req.method === "POST") {
    return await handleUpdate(req);
  }
  return new Response("League Binder Bot is running.", { status: 200 });
});
