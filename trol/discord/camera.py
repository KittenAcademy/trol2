import discord
import asyncio
import json
from discord.ext import commands, tasks
from discord.ui import Select, View
from .common import onlyChannel, trolRol, requestCameraInPosition, get_positions_containing_camera, send_to_channel
from io import BytesIO
from base64 import b64decode
from time import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from trol.shared.MQTTCommands import CameraCommands

from traceback import format_exc
import imageio.v3 as iio  # TODO: eliminate

import math
from trol.shared.logger import setup_logger
log = setup_logger('CameraCog')


# TODO: use PIL instead.
def create_gif(imgdat):
    if(len(imgdat) == 0):
        log.warn("Create gif has no images.")
        return None
    try:
        imgs = []
        for d in imgdat: 
            imgs.append(iio.imread(b64decode(d.removeprefix("data:image/jpg;base64,")), extension=".jpg"))
        return BytesIO(iio.imwrite("<bytes>", imgs, extension=".gif", duration=500, loop=0))
    except:
        log.error(format_exc())
    return None

class CameraCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camchange(self, ctx, position_name, camera_name):
        position_name = self.bot.settings.legacy_position_prefix + position_name

        camera = self.bot.cameras.getByName(camera_name)
        if camera is None:
            raise Exception(f"{camera_name} does not exist")
        if not camera.ispublic:
            raise Exception(f"{camera_name} is not public")
        await self.report_failure(ctx, camera)

        try:
            requestCameraInPosition(camera_name, position_name, access_level='admin')
        except Exception as e:
            log.warning(f"Got exception {e} attempting camera change")
            await ctx.send("True change comes from within. So look within because I can't change the camera.")
            return
        await ctx.send(f"Requested {camera_name} in {position_name}")

    def contact_age(self, camera):
        if not camera.last_screenshot_timestamp:
            if camera.nothumb:
                return 0.0
            return 999999
        camera_time = datetime.fromisoformat(camera.last_screenshot_timestamp)
        current_time = datetime.now()
        timediff = current_time - camera_time
        in_seconds = timediff.total_seconds()
        return in_seconds

    async def report_failure(self, ctx, camera):
        if camera.failure_count and camera.failure_count > 5:
            await ctx.send(f"Warning: {camera._name} may be failing.  {camera.failure_count} errors since last screenshot.")
        if self.contact_age(camera) > 60:
            nice_time = datetime.fromisoformat(camera.last_screenshot_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            await ctx.send(f"Warning: {camera._name} may be failing.  Last contact {nice_time}.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camcheck(self, ctx, camera_name):
        try:
            camera = self.bot.cameras.getByName(camera_name)
            if camera is None:
                raise Exception(f"{camera_name} does not exist")
            if not camera.ispublic:
                raise Exception(f"{camera_name} is not public")
            await self.report_failure(ctx, camera)

            camera_in_positions = get_positions_containing_camera(camera_name)

            message = "```"
            message += self.get_caminfo_string(camera_name, camera)
            message += "```"

            await ctx.send(message, file=discord.File(create_gif(self.bot.camthumbs.get(camera_name, [])), filename=f"camera {camera_name}.gif"))
        except Exception as e:
            log.warning(f"got exception {e} attempting camera check")
            await ctx.send(f"There was an error checking {camera_name}. To err is human so this is probably your fault.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def lockposition(self, ctx, position_name, lock_time=600):
        log.debug(f"Admin locking position {position_name} for {lock_time}s")
        self.bot.positions.lockPosition('TROL ' + position_name, access_level='admin', lock_time=lock_time)
        await ctx.send(f"Okay, I locked {position_name} for {lock_time} seconds.")
            
    @commands.command()
    @onlyChannel()
    @trolRol()
    async def unlockposition(self, ctx, position_name):
        log.debug(f"Admin unlocking position {position_name}")
        self.bot.positions.lockPosition('TROL ' + position_name, access_level='admin', lock_time=-1)
        await ctx.send(f"Okay, I unlocked {position_name}.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def hidecamera(self, ctx, camera_name):
        log.debug(f"Admin hiding camera {camera_name}")
        camera = self.bot.cameras.getByName(camera_name)
        if camera is None:
            await send_to_channel("I've never heard of that camera, not once in my life.")
        camera.ishidden = True
        await ctx.send("Oooh, are we going to do something naughty?")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def unhidecamera(self, ctx, camera_name):
        log.debug(f"Admin unhiding camera {camera_name}")
        camera = self.bot.cameras.getByName(camera_name)
        if camera is None:
            await ctx.send("I've never heard of that camera, not once in my life.")
        camera.ishidden = False
        await ctx.send("Naughty time over!")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camprivate(self, ctx, camera_name):
        log.warn(f"Admin making camera {camera_name} private")
        camera = self.bot.cameras.getByName(camera_name)
        if camera is None:
            await ctx.send("I've never heard of that camera, not once in my life.")
        camera.ispublic = False
        await ctx.send("You got it chief!")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def caminfo(self, ctx):
        # TODO: camerainfo, positioninfo, etc.
        camerainfo = "```"
        for position_name, position in self.bot.positions.items():
            camerainfo += f"Position {position_name} currently showing {position.active}.\n"
            if position.locked_until:
                if position.locked_until < 0:
                    camerainfo += f"  Locked forever by {position.lock_level}\n"
                    continue

                locked_for = position.locked_until - time()
                if locked_for > 0:
                    camerainfo += f"  Locked for {locked_for:.0f} seconds by {position.lock_level}\n"

        camerainfo += "\n"
        camerainfo += "```"

        await ctx.send(camerainfo)

        for camera_name, camera in self.bot.cameras.items():
            if not camera.ispublic:
                continue

            camerainfo = "```"
            camerainfo += self.get_caminfo_string(camera_name, camera)
            camerainfo += "```"
            await ctx.send(camerainfo)

    def get_caminfo_string(self, camera_name, camera):
        if not camera.ispublic:
            continue

        camerainfo += f"Camera {camera_name}"
        if camera.nice_name:
            camerainfo += f" a.k.a. '{camera.nice_name}'"
        camerainfo += "\n"
        in_locations = get_positions_containing_camera(camera_name)
        if len(in_locations):
            camerainfo += f"  is in positions: {in_locations}\n"
        if camera.failure_count and camera.failure_count > 5:
            camerainfo += f"  IS FAILING! {camera.failure_count} errors!\n"
        if self.contact_age(camera) > 60:
            nice_time = datetime.fromisoformat(camera.last_screenshot_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            camerainfo += f"  IS FAILING! Last contact {nice_time}.\n"
        if self.bot.cameras.isCameraPTZLocked(camera_name, 'admin'):
            camerainfo += f"  is PTZ Locked.\n"
        if camera.ishidden:
            camerainfo += f"  is HIDDEN.\n"
        if camera.known_ptz_positions:
            camerainfo += f"  has PTZ locations: " + ", ".join(camera.known_ptz_positions.keys()) + "\n"
        return camerainfo

async def setup(bot):
    await bot.add_cog(CameraCog(bot))


