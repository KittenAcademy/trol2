import discord
from discord.ext import commands, tasks
import asyncio
import traceback

from trol.shared.settings import get_settings

from trol.shared.logger import setup_logger
from trol.shared.MQTT import MQTTConnectionManager
from trol.shared.MQTTCameras import MQTTCameras
from trol.shared.MQTTPositions import MQTTPositions
from trol.shared.MQTTVariable import MQTTVariable
import trol.discord.common as common

log = setup_logger(__name__)

class LoggingContext(commands.Context):
    async def send(self, content=None, **kwargs):
        # Log the user, command, its parameters, and the message to the console
        user = self.author
        command_name = self.command.name if self.command else 'No command'
        command_args = self.args if self.command else 'No args'
        command_kwargs = self.kwargs if self.command else 'No kwargs'
        print(f"User: {user}, Command: {command_name}, Args: {command_args}, Kwargs: {command_kwargs}, Sending message: {content}")

        # Call the original send method
        return await super().send(content, **kwargs)
class LoggingBot(commands.Bot):
    async def get_context(self, message, *, cls=LoggingContext):
        return await super().get_context(message, cls=cls)

def camlist_changed(mqtt, mqtt_root, cameras, ptzdata, camthumbs):
    log.debug("New camlist rec'd")
    for camname in cameras.keys():
        if camname not in camthumbs:
            log.debug(f"New cam: {camname}")
            mqtt.subscribe(f"{mqtt_root}/cameras/{camname}/screenshot", lambda x,t,c=camname: thumbnail_receive(c,x,camthumbs))


def thumbnail_receive(camname, thumbnail, camthumbs):
    if thumbnail == '':
        log.debug(f"Thumb for {camname} is dead.")
        return
    if camname not in camthumbs:
        log.debug(f"Got first thumbnail for {camname}")
        camthumbs[camname] = []

    # new screenshot goes at front of array, and delete all but the most recent 
    # TODO: Any good reason not to do this on the populating end and keep several in MQTT?
    camthumbs[camname].append(thumbnail)
    del camthumbs[camname][:-5]


def main():
    asyncio.run(async_main())

async def async_main():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = LoggingBot(command_prefix='$', intents=intents, help_command=None)

    bot.settings = get_settings()
    bot.settings.load_from_command_line()

    bot.mqtt = MQTTConnectionManager(**bot.settings.mqtt)
    bot.cameras = MQTTCameras(bot.mqtt, f"{bot.settings.mqtt_root}/cameras")
    bot.positions = MQTTPositions(bot.mqtt, f"{bot.settings.mqtt_root}/positions")
    bot.camthumbs = {}
    bot.ptzdata = {}

    bot.settings.sync_via_mqtt(bot.mqtt, f"{bot.settings.mqtt_root}/settings")

    @bot.event
    async def on_command_error(ctx, error):
        log.error(f'Error in command {ctx.command}: {error}')
        traceback_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        log.error(traceback_str)

    @bot.event
    async def on_error(method, *args, **kwargs):
        log.error(f'Error')

    @bot.event
    async def on_ready():
        log.info("Bot ready.")
        MQTT_events.start()
        channel = bot.get_channel(int(bot.settings.discord.admin_channel))
        await channel.send("I'm back! Did I miss anything good?")

    # MQTT event processing loop
    @tasks.loop(seconds=1)
    async def MQTT_events():
        bot.mqtt.process_callbacks_for_time(1, quit_early=True)

    bot.cameras.add_callback( lambda: camlist_changed(bot.mqtt, bot.settings.mqtt_root, bot.cameras, bot.ptzdata, bot.camthumbs) )

    log.info("Populating global subscriptions")
    bot.mqtt.process_initialization_callbacks()

    # This just provides the bot and contained globals to the stuff in common.
    common.init(bot)

    await bot.load_extension('trol.discord.camera')
    await bot.load_extension('trol.discord.ptz')
    await bot.load_extension('trol.discord.voting')
    await bot.load_extension('trol.discord.news')
    await bot.load_extension('trol.discord.utility')
    await bot.load_extension('trol.discord.obs')

    
    async def informCameraChanged(position_name):
        channel = bot.get_channel(int(bot.settings.discord.admin_channel))
        await channel.send(f"{position_name} changed to {bot.positions.getByName(position_name).active}")

    for position_name, position in bot.positions.items():
        position.add_callback('active', lambda x=position_name: asyncio.create_task(informCameraChanged(x)))

    log.info("Discord bot loop starting.")
    await bot.start(bot.settings.discord['botkey'])

if __name__ == '__main__':
    main()


