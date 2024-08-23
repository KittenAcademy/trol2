import discord
import json
import asyncio
from discord.ext import commands
from .common import onlyChannel, trolRol, send_to_channel
from trol.shared.MQTTCommands import OBSCommands
from trol.shared.logger import setup_logger
log = setup_logger('UtilityCog')

class OBSCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.obscommands = OBSCommands(bot.mqtt, bot.settings.mqtt_root)
        self.previous_stats = None
        self.startup = True

        
        bot.mqtt.subscribe(f"{bot.settings.mqtt_root}/obs/stats", self.receive_streaming_stats)
        loop = asyncio.get_event_loop()
        bot.mqtt.subscribe(f"{bot.settings.mqtt_root}/obs/arewelive", lambda x: loop.create_task(self.report_streaming(json.loads(x))))
        bot.mqtt.subscribe(f"{bot.settings.mqtt_root}/obs/is_recording", lambda x: loop.create_task(self.report_recording(json.loads(x))))
        bot.mqtt.process_initialization_callbacks()
        loop.create_task(self.startup_complete())

    async def startup_complete(self):
        self.startup = False

    async def report_streaming(self, is_active: bool):
        if not is_active:
            await send_to_channel("Everybody panic!  The stream is off!")
        if self.startup:
            return
        await send_to_channel("Streaming started.  Whew.")

    async def report_recording(self, is_active:bool):
        if self.startup:
            return
        if is_active:
            await send_to_channel("Recording started.")
        else:
            await send_to_channel("Recording ended.")

    def receive_streaming_stats(self, statsjson):
        stats = json.loads(statsjson)
        if self.previous_stats:
            # TODO: some less-sensitive check on 'outputCongestion'
            # TODO: check these in different ways.
            for item in ['outputReconnecting', 'outputSkippedFrames']:
                if self.previous_stats.get(item) != stats.get(item):
                    log.warning(f"{item} has changed from {self.previous_stats.get(item)} to {stats.get(item)}")
                    loop = asyncio.get_event_loop()
                    loop.create_task(send_to_channel(f"Everybody panic!  Stream status has changed!  {item} is {stats.get(item)}"))
        self.previous_stats = stats

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def stopstreaming(self, ctx):
        log.debug(f"Request to stop streaming by {ctx.author.name}")
        self.obscommands.stop_streaming()
        await ctx.send("Okay, here comes nothing!")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def startstreaming(self, ctx):
        log.debug(f"Request to start streaming by {ctx.author.name}")
        self.obscommands.start_streaming()
        await ctx.send("ARE WE LIVE?!")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def fullscreen(self, ctx, position_name):
        position_name = self.bot.settings.legacy_position_prefix + position_name
        self.obscommands.make_fullscreen(position_name = position_name)
        await ctx.send("Done!  ... I guess, probably.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def reset_scene(self, ctx):
        self.obscommands.restore_scene_defaults()
        await ctx.send("Done!  ... I assume.")

async def setup(bot):
    await bot.add_cog(OBSCog(bot))


