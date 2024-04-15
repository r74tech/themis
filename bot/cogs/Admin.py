import time

from discord.ext import commands
from discord.commands import Option, slash_command

from config import config


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @slash_command(name="ping", description="BotのPingを返します")
    async def ping(self, ctx):
        start = time.time()
        msg = await ctx.respond("Pinging...")
        end = time.time()
        await msg.edit_original_response(
            content=f"Pong! {round((end - start) * 1000)}ms"
        )

    @commands.Cog.listener(name="on_ready")
    async def on_ready(self):
        await config.NOTIFY_TO_OWNER(self.bot, "Ready!")

    

def setup(bot):
    return bot.add_cog(Admin(bot))