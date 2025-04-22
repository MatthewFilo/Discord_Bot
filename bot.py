import discord
from discord.ext import commands
from discord.ext import tasks
import os
from dotenv import load_dotenv
import asyncio
import random
import requests
import html  # To decode HTML entities in the API response
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry

# Setting up environment
load_dotenv()
TOKEN = os.getenv('Token')
intents = discord.Intents.default()
intents.message_content = True
channel_id = os.getenv('Channel_ID')

# Set the default character for intents
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command("help") # Remove the default help command

# Set up the Open Meteo API client with caching and retry
cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)
WIND_SPEED_THRESHOLD = 30 # emergency wind speed threshold
url = "https://api.open-meteo.com/v1/forecast"

@bot.command(name='help') # Create new help command to override the default one
async def help_command(ctx):
    help_text = (
        "Here are the commands you can use:\n"
        "`!remindme <time_in_seconds> <reminder>` - Set a reminder.\n"
        "`!roll [sides]` - Roll a die with the specified number of sides (default is 100).\n"
        "`!trivia` - Get a trivia question and answer it.\n"
        "`!FWweather` - Get the weather forecast for Fort Worth.\n"
        "`!SDweather` - Get the weather forecast for San Diego.\n"
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

@bot.command(name='FWweather') # Alerts the user of the weather in Fort Worth
async def FWweather(ctx):
    params = {
        "latitude": 32.7254,
        "longitude": -97.3208,
        "hourly": ["temperature_2m", "precipitation_probability", "wind_gusts_10m"],
        "forecast_days": 1,
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "wind_speed_unit": "mph"
    }
    response = openmeteo.weather_api(url, params=params)[0]
    hourly = response.Hourly()
    
    data = {
        "Time": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left"
        ),
        "Temp (°F)": hourly.Variables(0).ValuesAsNumpy(),
        "Precip (%)": hourly.Variables(1).ValuesAsNumpy(),
        "Wind Gusts (mph)": hourly.Variables(2).ValuesAsNumpy()
    }
    
    df = pd.DataFrame(data).head(5)  # Show only the first 5 rows
    
    # Format the DataFrame for Discord message
    formatted_data = "```\n" + df.to_string(index=False, justify="center") + "\n```"
    await ctx.send(f"**Fort Worth Weather:**\n{formatted_data}")

@tasks.loop(minutes=30) # Check every 30 minutes
async def check_wind_speed():
    params = {
        "latitude": 32.7254,
        "longitude": -97.3208,
        "hourly": ["temperature_2m", "precipitation_probability", "wind_gusts_10m"],
        "forecast_days": 1,
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "wind_speed_unit": "mph"
    }
    response = openmeteo.weather_api(url, params=params)[0]
    hourly = response.Hourly()
    
    wind_gusts = hourly.Variables(2).ValuesAsNumpy()
    
    if wind_gusts[0] > WIND_SPEED_THRESHOLD:
        channel = bot.get_channel(int(channel_id))
        await channel.send(f"⚠️ Wind gusts are over {WIND_SPEED_THRESHOLD} mph! Stay safe!")
@check_wind_speed.before_loop
async def before_check_wind_speed():
    await bot.wait_until_ready()

@bot.command(name='SDweather') # Alerts the user of the weather in San Diego
async def SDweather(ctx):
    params = {
        "latitude": 32.7157,
        "longitude": -117.1647,
        "hourly": ["temperature_2m", "precipitation_probability", "rain"],
        "forecast_days": 1,
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "wind_speed_unit": "mph"
    }
    response = openmeteo.weather_api(url, params=params)[0]
    hourly = response.Hourly()
    
    data = {
        "Time": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left"
        ),
        "Temp (°F)": hourly.Variables(0).ValuesAsNumpy(),
        "Precip (%)": hourly.Variables(1).ValuesAsNumpy(),
        "Rain (in)": hourly.Variables(2).ValuesAsNumpy()
    }
    
    df = pd.DataFrame(data).head(5)  # Show only the first 5 rows
    
    # Format the DataFrame for Discord message
    formatted_data = "```\n" + df.to_string(index=False, justify="center") + "\n```"
    await ctx.send(f"**San Diego Weather:**\n{formatted_data}")

@bot.event # Error handling for the bot
async def on_error(event, *args, **kwargs):
    print(f'An error occurred in {event}:', args, kwargs)

bot.run(TOKEN)
check_wind_speed.start() # Start the wind speed check loop
