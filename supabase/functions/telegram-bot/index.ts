import { Bot, webhookCallback } from "https://deno.land/x/grammy@v1.21.1/mod.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { upsertUser } from "./utils.ts";

export { upsertUser };

const bot = new Bot(Deno.env.get("TELEGRAM_BOT_TOKEN")!);

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
);

bot.command("start", async (ctx) => {
  await upsertUser(supabase, ctx.from!.id, ctx.from!.username);
  await ctx.reply(
    "👋 Welcome to League Binder Bot!\n\n" +
    "Commands:\n" +
    "/register <moxfield_binder_url> — Add your binder\n" +
    "/mybinders — List your registered binders\n" +
    "/removebinder <url> — Remove a binder\n" +
    "/search <card name> — Find who has a card"
  );
});

bot.command("register", async (ctx) => {
  const url = ctx.match?.trim();
  if (!url || !url.startsWith("https://moxfield.com/binders/")) {
    await ctx.reply("Please provide a valid Moxfield binder URL.\nExample: /register https://moxfield.com/binders/ABC123");
    return;
  }
  await upsertUser(supabase, ctx.from!.id, ctx.from!.username);
  const { error } = await supabase
    .from("binders")
    .insert({ user_id: ctx.from!.id, url });
  if (error?.code === "23505") {
    await ctx.reply("That binder is already registered to your account.");
    return;
  }
  if (error) throw error;
  await ctx.reply(`✅ Binder registered! It will be scraped in the next daily run.\n${url}`);
});

const handleUpdate = webhookCallback(bot, "std/http");

Deno.serve(async (req: Request) => {
  if (req.method === "POST") {
    return await handleUpdate(req);
  }
  return new Response("League Binder Bot is running.", { status: 200 });
});
