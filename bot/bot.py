import logging

import discord
from discord.ext import commands
import sentry_sdk

from config import config

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s][%(levelname)s] %(message)s"
)

sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=1.0)

# bot init
bot = commands.Bot(
    help_command=None,
    case_insensitive=True,
    activity=discord.CustomActivity(name="ロール監視中"),
    intents=discord.Intents.all(),
)

bot.load_extension("cogs.Admin")
bot.load_extension("cogs.CogManager")

bot.run(config.TOKEN)