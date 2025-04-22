import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import random
import requests
import html  # To decode HTML entities in the API response

# Setting up environment
load_dotenv()
TOKEN = os.getenv('Token')
intents = discord.Intents.default()
intents.message_content = True
channel_id = os.getenv('Channel_ID')

# Set the default character for intents
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command("help") # Remove the default help ocmmand

@bot.command(name='help') # Create new help command to override the default one
async def help_command(ctx):
    help_text = (
        "Here are the commands you can use:\n"
        "`!remindme <time_in_seconds> <reminder>` - Set a reminder.\n"
        "`!roll [sides]` - Roll a die with the specified number of sides (default is 100).\n"
        "`!trivia` - Get a trivia question and answer it.\n"
    )
    await ctx.send(help_text)


@bot.event
async def on_ready(): # Displays in terminal when bot is ready
    print(f'{bot.user} has connected to Discord!')

@bot.event # Whenever bot is mentioned, respond
async def on_message(message):
    if bot.user in message.mentions:
        await message.channel.send("Howdy!")
    await bot.process_commands(message)

@bot.command(name='remindme')
async def remindme(ctx, time: int, *, reminder: str):
    # Send initial message
    await ctx.send(f"Reminder set for {time} seconds.")
    await asyncio.sleep(time) # Sleep for specified time
    await ctx.send(f"Time is up: {reminder}") # Timer over, send reminder

@remindme.error # Error handling function for remindme command
async def remindme_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!remindme <time_in_seconds> <reminder>`\nExample: `!remindme 60 Take a break!`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Arguments must be !remindme <time_in_seconds> <reminder>.\nExample: `!remindme 60 Take a break!`")

@bot.command(name='roll') # Roll command to roll 1-100
async def roll(ctx, sides: int = 100):
    result = random.randint(1, sides)
    await ctx.send(f'You rolled a {result}!')

@bot.command(name='trivia') # Trivia command using the Open Trivia Database API
async def trivia(ctx):
    # Fetch trivia questions from the API
    url = os.getenv("api_link")
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if data["response_code"] == 0:  # Ensure the API returned questions
            question_data = data["results"][0]
            question = html.unescape(question_data["question"])
            correct_answer = html.unescape(question_data["correct_answer"])
            incorrect_answers = [html.unescape(ans) for ans in question_data["incorrect_answers"]]
            
            # Combine correct and incorrect answers and shuffle them
            options = incorrect_answers + [correct_answer]
            random.shuffle(options)
            
            # Format the question and options
            options_text = "\n".join([f"{i+1}. {option}" for i, option in enumerate(options)])
            trivia_message = f"**{question}**\n\n{options_text}\n\nReply with the number of your answer!"
            
            # Send the question to the user
            await ctx.send(trivia_message)
            
            # Wait for the user's response
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
            
            try:
                user_response = await bot.wait_for("message", check=check, timeout=30.0)
                user_answer = int(user_response.content)

                if 1 <= user_answer <= len(options) and options[user_answer - 1] == correct_answer:
                    await ctx.author.send(f"🎉 Correct! The answer is **{correct_answer}**.")
                else:
                    await ctx.author.send(f"❌ Wrong! The correct answer was **{correct_answer}**.")
            except asyncio.TimeoutError:
                await ctx.author.send("⏰ Time's up! You didn't answer in time.")
        else:
            await ctx.send("⚠️ No trivia questions available at the moment. Try again later.")
    else:
        await ctx.send("⚠️ Failed to fetch trivia questions. Please try again later.")

@bot.event # Error handling for the bot
async def on_error(event, *args, **kwargs):
    print(f'An error occurred in {event}:', args, kwargs)

bot.run(TOKEN)