import discord
from discord.ext import commands
from trol.shared.logger import setup_logger
from io import BytesIO
from base64 import b64decode
from PIL import Image
from time import time


log = setup_logger(__name__)

bot = None;

def init(discordbot):
    """ I'm on a lack of sleep so I'm sure there's a more elegant way to provide all the data we need """
    global bot
    bot = discordbot
    bot.last_admin_activity = time()

# Permissions predicates
def trolRol(role = None):
    if role is None:
        role = bot.settings.discord.admin_role
    """ For checking whether a user has the 'trol role' - is admin """
    async def predicate(ctx):
        for r in ctx.author.roles:
            if r.name == role:
                # TODO: IDK, change this?
                # track when the last admin command was run for use by autopoll:
                bot.last_admin_activity = time()
                return True
        log.debug("Role check fail.")
        return False
    return commands.check(predicate)


def onlyChannel(channel_id = None):
    if channel_id is None:
        channel_id = int(bot.settings.discord.admin_channel)
    """ Only allow on a particular channel. """
    async def predicate(ctx):
        if(ctx.channel.id == channel_id):
            return True
        log.debug(f"message channel is {ctx.channel.id} but we expect {bot.settings.discord['admin_channel']}")
        return False
    return commands.check(predicate)

async def send_to_channel(message, channel=None, filedata=None, filename="unknown.gif", duration=None):
    try:
        await bot.wait_until_ready() # Just in case we're called too soon.
        if channel is None:
            channel=bot.settings.discord.admin_channel
        c = bot.get_channel(int(channel))
        if(c is None):
            log.warn(f"Called send_to_channel with nonexistant channel id: {channel}")
            return
        if(filedata is not None):
            await c.send(message, file=discord.File(filedata, filename=filename), delete_after=duration)
            return
        log.debug(f"Sending {message}")
        await c.send(message, delete_after=duration)
    except Exception as e:
        log.error(f"Exception in send_to_channel: {e}")

def getCameraThumbs(access_level='Discord user'):
        test = lambda camname: bot.cameras.getByName(camname).ispublic and not bot.cameras.getByName(camname).ishidden
        if access_level == 'admin':
            test = lambda camname: bot.cameras.getByName(camname).ispublic
        return {
            camname: thumbs for camname, thumbs in bot.camthumbs.items()
            if test(camname)
        }

def get_positions_containing_camera(camname: str):
        poslist = []
        for posname, pos in bot.positions.items():
            if camname == pos.active:
                poslist.append(posname)
        return poslist

def requestCameraInPosition(camera_name, position_name, lock_time=0, access_level='Discord user'):
        position = bot.positions.getByName(position_name)
        camera   = bot.cameras.getByName(camera_name)

        if position is None or camera is None:
            log.warn(f"Request for invalid position change: {camera_name} in {position_name}")
            raise Exception(f"Request for invalid position change: {camera_name} in {position_name}")
        if bot.positions.positionIsLocked(position_name, access_level=access_level):
            log.info(f"Request for locked position change: {camera_name} in {position_name} by {access_level}")
            raise Exception(f"Request for locked position change: {camera_name} in {position_name} by {access_level}")
        if not camera.ispublic and access_level != 'root':
            log.info(f"Request for non-public camera {camera_name} in {position_name} by {access_level}")
            raise Exception(f"Request for non-public camera {camera_name} in {position_name} by {access_level}")
        if position.isaudio and camera.noaudio:
            log.info(f"Request for non-audio camera {camera_name} in audio position {position_name}.")
            raise Exception(f"Request for non-audio camera {camera_name} in audio position {position_name}.")

        # Everything checks out, let's do it
        position.requested = camera_name
        bot.positions.lockPosition(position_name, access_level)

def thumbnail_to_BytesIO(thumbnail: str):
    image_data_b64 = thumbnail.removeprefix("data:image/jpg;base64,")
    image_data = b64decode(image_data_b64)
    return BytesIO(image_data)

