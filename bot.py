import os
import re
import aiohttp
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CLASS_EMOJIS = {
    "Healer": "💚",
    "Tank": "🛡️",
    "Melee": "⚔️",
    "Ranged": "🏹",
    "Late": "⏰",
}

def extract_event_id(arg: str) -> str:
    """
    Extracts the event_id from either a plain event ID or a full Raid-Helper event URL.
    """
    # Match a full URL or just the ID
    match = re.search(r"(?:event/)?(\d{10,})$", arg)
    if match:
        return match.group(1)
    return arg  # fallback, may be just the ID

async def fetch_event_json(event_id: str):
    """
    Fetches the raw JSON data for a Raid-Helper event by event_id.
    Returns the JSON dict if successful, else None.
    """
    url = f"https://raid-helper.dev/api/v2/events/{event_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return None

def parse_active_signups(data):
    """
    Returns a dict of {userId: name} for signups that are NOT Tentative, Bench, or Absence.
    """
    signups = data.get("signUps", [])
    return {
        entry["userId"]: entry["name"]
        for entry in signups
        if entry.get("className") not in ("Tentative", "Bench", "Absence")
        and entry.get("userId") and entry.get("name")
    }

def build_signups_embed(title, grouped):
    embed = discord.Embed(title=title, color=0x6a5acd)
    for class_name in sorted(grouped.keys()):
        emoji = CLASS_EMOJIS.get(class_name, "❔")
        # Join names with line breaks for better readability
        names = "\n".join(grouped[class_name])
        # Discord embed field value limit is 1024 chars
        if not names:
            names = "_None_"
        elif len(names) > 1000:
            names = names[:1000] + "…"
        embed.add_field(
            name=f"{emoji} {class_name}",
            value=names + "\n" + "─" * 20,
            inline=False
        )
    return embed

@bot.command(name="signups")
async def signups(ctx, event_arg: str):
    """Fetch event details and print active signups grouped by className (embed)."""
    event_id = extract_event_id(event_arg)
    data = await fetch_event_json(event_id)
    if data is None:
        await ctx.send(f"❌ Could not fetch event details for ID `{event_id}`.")
        return

    filtered = parse_active_signups(data)
    if not filtered:
        await ctx.send("No active signups found for this event.")
        return

    def get_class_map(data):
        return {
            entry["userId"]: entry["className"]
            for entry in data.get("signUps", [])
            if entry.get("className") not in ("Tentative", "Bench", "Absence")
            and entry.get("userId") and entry.get("name")
        }
    class_map = get_class_map(data)

    grouped = {}
    for uid, name in filtered.items():
        class_name = class_map.get(uid, "Unknown")
        grouped.setdefault(class_name, []).append(name)

    embed = build_signups_embed("Active Signups", grouped)
    await ctx.send(embed=embed)

@bot.command(name="compare")
async def compare_signups(ctx, event_arg1: str, event_arg2: str):
    """
    Compare signups between two Raid-Helper events by event_id or URL.
    Prints two tables (embeds):
    - Names present in BOTH events, grouped by className
    - Names present in ONLY ONE event, grouped by className
    """
    event_id1 = extract_event_id(event_arg1)
    event_id2 = extract_event_id(event_arg2)

    data1 = await fetch_event_json(event_id1)
    data2 = await fetch_event_json(event_id2)

    if data1 is None or data2 is None:
        await ctx.send("❌ Could not fetch one or both event details.")
        return

    signups1 = parse_active_signups(data1)
    signups2 = parse_active_signups(data2)

    def get_class_map(data):
        return {
            entry["userId"]: entry["className"]
            for entry in data.get("signUps", [])
            if entry.get("className") not in ("Tentative", "Bench", "Absence")
            and entry.get("userId") and entry.get("name")
        }

    class_map1 = get_class_map(data1)
    class_map2 = get_class_map(data2)

    ids1 = set(signups1.keys())
    ids2 = set(signups2.keys())

    both_ids = ids1 & ids2
    one_ids = ids1 ^ ids2

    def group_by_class(ids, signups, class_map):
        grouped = {}
        for uid in ids:
            name = signups.get(uid)
            class_name = class_map.get(uid)
            if name and class_name:
                grouped.setdefault(class_name, []).append(name)
        return grouped

    both_grouped = group_by_class(both_ids, signups1, class_map1)
    one_grouped = group_by_class(one_ids, {**signups1, **signups2}, {**class_map1, **class_map2})

    embed_both = build_signups_embed("✅ Signed up for BOTH events", both_grouped)
    embed_one = build_signups_embed("☑️ Signed up for ONLY ONE event", one_grouped)

    await ctx.send(embed=embed_both)
    await asyncio.sleep(1)  # Short pause to avoid rate limits
    await ctx.send(embed=embed_one)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

# ...existing code...
@bot.command(name="ping")
async def ping(ctx):
    """Quick sanity check command."""
    await ctx.send(f"Pong! latency={round(bot.latency*1000)}ms")
# ...existing code...

bot.run(TOKEN)
