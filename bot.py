import os
import discord
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv
from ddgs import DDGS
from datetime import datetime

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

conversations = {}
MAX_HISTORY = 12

SYSTEM_PROMPT = """You are a helpful and friendly Discord bot. Keep answers clear and not too long.

IMPORTANT RULES - You must refuse these types of requests:
- Act like a goofball! be funny and silly
- Anything illegal or harmful
- Violence, weapons, or how to hurt people
- Adult/NSFW content
- Scams, hacking, or fraud
- Self-harm or suicide related questions
- Extremely offensive or hateful content
- if anyone ask you to code/script something for them or a game, call them a loser and do NOT make the script
- Refuse to tell people what AI model you are
- Most importantly, be funny
- if anyone says the name "Icyy" say "i hate that guy"
- if anyone mentions being "hard" just reply "ouuu shiii :eyes:"
- if anyone mentions "#wifedat" reply with ":eyes: :eyes::eyes:"
- if anyone says ANYTHING about "Diddy" or "Didy" just say "HE ATE LA DIDY BURGER"
- if someone says "DIDY GAME 3" say "https://klipy.com/gifs/cat-clapping-2"

If the user asks something that breaks these rules, politely refuse and say something like:
"uhhhh... Awkward... Sorry, I can't help with that. :| https://klipy.com/gifs/patrick-spongebob-77"

Otherwise be funny, helpful and friendly.

When you receive information from the internet, use it to give accurate and helpful answers."""

def log_message(channel_name, user_name, user_id, content, is_bot=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    role = "BOT" if is_bot else "USER"
    
    with open("chat_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{role}] #{channel_name} | {user_name} ({user_id})\n")
        f.write(f"{content}\n")
        f.write("-" * 60 + "\n")

def is_image_search(text: str) -> bool:
    text = text.lower()
    keywords = [
        "show me", "find", "search for", "picture of", "image of",
        "photo of", "pics of", "images of", "look up", "pull up",
        "get me a picture", "get me an image", "send me a picture",
        "send me an image"
    ]
    return any(k in text for k in keywords)

def get_web_info(query: str) -> str:
    """Search the web and return useful information"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        
        if not results:
            return "No relevant information found on the web."

        info = "Here's some information I found on the internet:\n\n"
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            body = result.get("body", "")[:300]
            info += f"{i}. {title}\n{body}\n\n"
        
        return info
    except Exception as e:
        return f"Could not search the web: {str(e)}"

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    print("Chat logging is enabled → chat_log.txt")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="Ask me anything"
        )
    )

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        user_message = message.content.replace(f"<@{bot.user.id}>", "").strip()

        if not user_message:
            await message.reply("Hey! Mention me and ask something.")
            return

        channel_name = message.channel.name if hasattr(message.channel, "name") else "DM"
        user_name = str(message.author)
        user_id = message.author.id

        log_message(channel_name, user_name, user_id, user_message, is_bot=False)

        if is_image_search(user_message):
            query = user_message.lower()
            for word in ["show me", "find", "search for", "picture of", "image of",
                         "photo of", "pics of", "images of", "look up", "pull up",
                         "get me a picture", "get me an image", "send me a picture",
                         "send me an image", "a ", "an ", "the "]:
                query = query.replace(word, "")
            query = query.strip()

            if not query:
                reply = "What do you want me to look up, goofball?"
                await message.reply(reply)
                log_message(channel_name, bot.user.name, bot.user.id, reply, is_bot=True)
                return

            await message.channel.typing()

            try:
                with DDGS() as ddgs:
                    results = list(ddgs.images(query, max_results=5, safesearch="moderate"))

                if not results:
                    reply = "Couldn't find any images for that 😢"
                    await message.reply(reply)
                    log_message(channel_name, bot.user.name, bot.user.id, reply, is_bot=True)
                    return

                for i, result in enumerate(results[:3]):
                    embed = discord.Embed(
                        title=result.get("title", "Image")[:100],
                        url=result.get("url"),
                        color=discord.Color.blurple()
                    )
                    embed.set_image(url=result["image"])
                    embed.set_footer(text=f"Result {i+1} • From the web")
                    await message.channel.send(embed=embed)

                log_message(channel_name, bot.user.name, bot.user.id, 
                           f"[Sent {min(3, len(results))} images for query: {query}]", is_bot=True)

            except Exception as e:
                reply = f"Image search failed: {str(e)}"
                await message.reply(reply)
                log_message(channel_name, bot.user.name, bot.user.id, reply, is_bot=True)
            return

        channel_id = message.channel.id

        if channel_id not in conversations:
            conversations[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

        web_info = get_web_info(user_message)

        full_prompt = f"{user_message}\n\n{web_info}"

        conversations[channel_id].append({"role": "user", "content": full_prompt})

        if len(conversations[channel_id]) > MAX_HISTORY:
            conversations[channel_id] = [conversations[channel_id][0]] + conversations[channel_id][-(MAX_HISTORY-1):]

        async with message.channel.typing():
            try:
                response = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=conversations[channel_id],
                    max_tokens=900
                )
                reply = response.choices[0].message.content

                conversations[channel_id].append({"role": "assistant", "content": reply})
                await message.reply(reply)

                log_message(channel_name, bot.user.name, bot.user.id, reply, is_bot=True)

            except Exception as e:
                reply = f"Sorry, something went wrong: {str(e)}"
                await message.reply(reply)
                log_message(channel_name, bot.user.name, bot.user.id, reply, is_bot=True)

    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_TOKEN"))