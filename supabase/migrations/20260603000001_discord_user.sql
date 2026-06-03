-- supabase/migrations/20260603000001_discord_user.sql
ALTER TABLE users ADD COLUMN discord_id bigint UNIQUE;
ALTER TABLE users ADD COLUMN discord_username text;
