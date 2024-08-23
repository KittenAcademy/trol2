import discord
import asyncio
from discord.ext import commands
from .common import onlyChannel, trolRol, send_to_channel
from trol.shared.MQTTVariable import MQTTVariable
from trol.shared.logger import setup_logger
log = setup_logger('NewsCog')

class NewsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scroll_active = MQTTVariable(bot.mqtt, f"{bot.settings.mqtt_root}/scroll/isactive", bool, initial_value=False)
        self.scroll_text = MQTTVariable(bot.mqtt, f"{bot.settings.mqtt_root}/scroll/newsticker", str, initial_value="")
        self.scroll_text.add_callback(self.handle_text_changed)

    def handle_text_changed(self):
        loop=asyncio.get_event_loop()
        if self.scroll_text.value != '':
            loop.create_task(send_to_channel(f"Scroll set to '{self.scroll_text.value}'."))
        else:
            loop.create_task(send_to_channel(f"Scroll is blank."))


    def handle_scroll_active(self):
        loop=asyncio.get_event_loop()
        if self.scroll_active.value:
            loop.create_task(send_to_channel(f"Live stream scrolling: '{self.scroll_text.value}'."))
        else:
            loop.create_task(send_to_channel(f"Live stream scroll completed."))

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def setnews(self, ctx):
        log.debug("setnews")
        m = discord.utils.remove_markdown(ctx.message.clean_content).removeprefix(r"$setnews").removeprefix(r"$delnews").removeprefix(r"$clearnews").strip()
        log.debug(f"setnews {m}")
        prev_scroll = self.scroll_text.value
        if m is not None:
            self.scroll_text.value = m
        else:
            self.scroll_text.value = ""
        log.debug(f"Scroll was '{prev_scroll}' and is now '{self.scroll_text.value}'.")
        await ctx.send(f"Scroll was '{prev_scroll}'.  Hold for confirmation.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def delnews(self, ctx):
        await self.clearnews(ctx)

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def clearnews(self, ctx):
        await self.setnews(ctx)

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def checknews(self, ctx):
        log.debug(f"News scroll:  '{self.scroll_text.value}'")
        await ctx.send(f"News scroll:  '{self.scroll_text.value}'")

async def setup(bot):
    await bot.add_cog(NewsCog(bot))

