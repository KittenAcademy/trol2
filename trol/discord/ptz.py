import discord
import asyncio
from typing import Union
import json
from discord.ext import commands, tasks
from .common import onlyChannel, trolRol, getCameraThumbs, thumbnail_to_BytesIO, send_to_channel
from io import BytesIO
import base64
from traceback import format_exc
import functools

from trol.shared.MQTTCommands import CameraCommands

from trol.shared.logger import setup_logger, set_debug
log = setup_logger('CamcontrolCog')

VECTORS = {'left': (-0.2,0,0),
           'bigleft': (-0.5,0,0),
           'right': (0.2,0,0),
           'bigright': (0.5,0,0),
           'up': (0,0.2,0),
           'bigup': (0,0.5,0),
           'down': (0,-0.2,0),
           'bigdown': (0,-0.5,0),
           'zoomin': (0,0,0.25),
           'bigzoomin': (0,0,1),
           'zoomout': (0,0,-0.25),
           'bigzoomout': (0,0,-1)
           }

# TODO: This is duplicated, should be in common code
def are_coords_equal(c1, c2, tolerance=0.01):
    return all(abs(a - b) <= tolerance for a, b in zip(c1, c2))

def str_to_coords(vector_string):
    floats = tuple(map(float, vector_string.split(',')))
    if len(floats) != 3:
        raise Exception(f"Got floats but not the right number of them.")
    return floats

class PTZCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # TODO: This should not be an instance attribute since it's possible
        # we need several watchcams at once.
        # self.loopcount = 0
        # watchcam isnt' really working anyhow.

        # TODO: hacky
        # If this is set to a string, then the next ptz_arrived we get, we will save under that name.
        self.save_next_position_as = None
        self.cameraCommands = CameraCommands(bot.mqtt, bot.settings.mqtt_root)
        for camera_name, camera in bot.cameras.items():
            callback = functools.partial(self.report_camera_arrived, camera_name)
            camera.add_callback('ptz_arrived', callback)
            #camera.add_callback('ptz_arrived', lambda x,t,c=camera_name: self.report_camera_arrived(c, x))

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camgoto(self, ctx, camera_name: str, where: str):
        try:
            camera = self.bot.cameras.getByName(camera_name)
            if camera is None:
                raise Exception(f"{camera_name} does not exist")
            if not camera.ispublic:
                raise Exception(f"{camera_name} is not public")
            if self.bot.cameras.isCameraPTZLocked(camera_name, 'admin'):
                raise Exception(f"{camera_name} is PTZ locked")

            try:
                floats = str_to_coords(where)
                await self.goto_ptz_coords(ctx, camera_name, floats)
                return
            except Exception as e:
                log.debug(f"Exception {e} attempting to interpret camgoto {camera_name}:{where} as coords.")
                pass
            await self.goto_ptz_position(ctx, camera_name, where)
            return
        except Exception as e:
            log.warning(f"{ctx.author.name} got exception {e} attempting camera goto for {camera_name}.")
            await ctx.send("Use of GOTO considered harmful.")

    async def goto_ptz_coords(self, ctx, camera_name: str, coords: tuple):
        try:
            message = camera_name
            self.cameraCommands.goto_absolute_coords(camera_name = camera_name, coords = coords)
            await ctx.send(f"Request to move to {coords} has been sent.")
        except Exception as e:
            log.warning(f"{ctx.author.name} got exception {e} attempting camera goto for {camera_name}.")
            await ctx.send("Use of GOTO considered harmful.")

    def get_coords_by_name(self, camera, ptz_name):
        if not camera.known_ptz_positions:
            return None
        if ptz_name in camera.known_ptz_positions:
            return camera.known_ptz_positions[ptz_name]
        return None

    def get_name_by_coords(self, camera, search_coords):
        if not camera.known_ptz_positions:
            return None
        for ptz_name, coords in camera.known_ptz_positions.items():
            if are_coords_equal(search_coords, coords, tolerance=self.bot.settings.ptz_position_tolerance):
                return ptz_name
        return None

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def getposition(self, ctx, camera_name):
        try:
            camera = self.bot.cameras.getByName(camera_name)
            if camera is None:
                raise Exception(f"{camera_name} does not exist")
            if not camera.ispublic:
                raise Exception(f"{camera_name} is not public")

            self.update_ptz_arrived(ctx, camera_name)
            # await ctz.send(F"Requested position for {camera_name}")
        except Exception as e:
            log.warn(f"Error {e} attempting to get position/screenshot.")
    
    def update_ptz_arrived(self, ctx, camera_name):
        try:
            log.debug(f"Dispatching to cameraCommands")
            self.cameraCommands.goto_relative_vector(camera_name = camera_name, vector = (0,0,0))
        except Exception as e:
            log.warn(f"Error {e} attempting to update ptz_arrived.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def saveposition(self, ctx, camera_name, position_name, coords=None):
        try:
            camera = self.bot.cameras.getByName(camera_name)
            if camera is None:
                raise Exception(f"{camera_name} does not exist")
            if not camera.ispublic:
                raise Exception(f"{camera_name} is not public")

            if coords:
                coords_to_save = str_to_coords(vector)
                camera.known_ptz_positions[position_name] = coords_to_save
                await ctx.send(f"Assigned {camera_name} new position {position_name} at ({coords_to_save})")
                return
            self.save_next_position_as = position_name
            self.update_ptz_arrived(ctx, camera_name)
        except Exception as e:
            log.warning(f"Failed to save position: {camera_name} {position_name}")
            await ctx.send("Couldn't save position.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def delposition(self, ctx, camera_name, position_name):
        try:
            camera = self.bot.cameras.getByName(camera_name)
            if camera is None:
                raise Exception(f"{camera_name} does not exist")
            if not camera.ispublic:
                raise Exception(f"{camera_name} is not public")

            del camera.known_ptz_positions[position_name] 
            await ctx.send(f"Deleted {position_name} from {camera_name}")
        except Exception as e:
            log.warning(f"Failed to save position: {camera_name} {position_name}")
            await ctx.send("Couldn't save position.")

    async def goto_ptz_position(self, ctx, camera_name, ptz_position_name):
        try:
            camera = self.bot.cameras.getByName(camera_name)
            if camera is None:
                raise Exception(f"{camera_name} does not exist")
            if not camera.ispublic:
                raise Exception(f"{camera_name} is not public")
            if self.bot.cameras.isCameraPTZLocked(camera_name, 'admin'):
                raise Exception(f"{camera_name} is PTZ locked")

            dest_coords = None
            message = camera_name
            if ptz_position_name == 'undo':
                if camera.prior_ptz_positions is not None and len(camera.prior_ptz_positions) > 0:
                    dest_coords = camera.prior_ptz_positions.pop()
                    prev_name = self.get_name_by_coords(camera, dest_coords)
                    if not prev_name:
                        message += " going back to previous PTZ location."
                    else:
                        message += f" going back to previous PTZ location '{prev_name}'."
                else:
                    message = "What has been done cannot be undone. You just have to live with it."
            else:
                dest_coords = self.get_coords_by_name(camera, ptz_position_name) 
                message += f" has been sent to PTZ location {ptz_position_name}."
            if dest_coords is None:
                raise Exception(f" could not locate coordinates for move.")

            self.cameraCommands.goto_absolute_coords(camera_name = camera_name, coords = dest_coords)
            await ctx.send(message)
        except Exception as e:
            log.warning(f"{ctx.author.name} got exception {e} attempting camera goto for {camera_name}.")
            await ctx.send("Use of GOTO considered harmful.")

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camvector(self, ctx, camera_name, coords):
        try:
            if coords in VECTORS:
                vector = VECTORS[coords]
            else:
                vector = str_to_coords(coords)
            log.debug(f"camvector {camera_name} to {vector}")
            camera = self.bot.cameras.getByName(camera_name)
            if camera is None:
                raise Exception(f"{camera_name} does not exist")
            if not camera.ispublic:
                raise Exception(f"{camera_name} is not public")
            if self.bot.cameras.isCameraPTZLocked(camera_name, 'admin'):
                raise Exception(f"{camera_name} is PTZ locked")

            log.debug(f"Dispatching to cameraCommands")
            self.cameraCommands.goto_relative_vector(camera_name = camera_name, vector = vector)
            await ctx.send(f"{camera_name} vector command sent.")
        except Exception as e:
            log.warning(f"got exception {e} attempting vector: {format_exc()}")
            await ctx.send("Sorry, I can't.")

    def report_camera_arrived(self, camera_name):
        try:
            camera = self.bot.cameras.getByName(camera_name)
            message_data = camera.ptz_arrived
            position = message_data['coords']
            screenshot_data = message_data.get('screenshot', None)
            log.debug(f"Got camera arrival: {camera_name}, {position}, {screenshot_data[:30]}")
            if self.save_next_position_as:
                camera.known_ptz_positions[self.save_next_position_as] = position
                self.save_next_position_as = None
            position_name = self.get_name_by_coords(camera, position)
            if not position_name:
                position_name = ''
            if screenshot_data:
                screenshot_data = screenshot_data.split(",")[1]
                screenshot = BytesIO(base64.b64decode(screenshot_data))

                loop = asyncio.get_event_loop()
                loop.create_task(
                    send_to_channel(
                        message=f"{camera_name} is at {position_name} ({position})",
                        filedata=screenshot,
                        filename='screenshot.jpg'
                    )
                )
            else:
                loop = asyncio.get_event_loop()
                loop.create_task(send_to_channel(message=f"{camera_name} is at {position_name} ({position})"))
        except Exception as e:
            log.error(f"report_camera_arrived is failing: {e}:{format_exc()}")

#    #####################
#    # Goal:  Find a way to update images in-place on Discord for nice camera viewing in "real time."
#    # Although this works, it causes the embed to resize in a very annoying way when changing images, so it's 
#    # not really useable IMO.
#    @commands.command()
#    @trolRol()
#    async def watchcam(self, ctx, camera_name):
#        initial_thumbnails = getCameraThumbs('admin').get(camera_name, [])
#        if len(initial_thumbnails) == 0:
#            await ctx.send("No cameras by that name.")
#        image_bytes = thumbnail_to_BytesIO(initial_thumbnails[-1])
#
#        embed = discord.Embed(title=camera_name)
#        embed.set_image(url=f"attachment://image{self.loopcount}.jpg")
#        message = await ctx.send(embed=embed, file=discord.File(image_bytes, filename=f"image{self.loopcount}.jpg"))
#        self.update_view.start(message, ctx, camera_name)
#    @tasks.loop(count = 5)
#    async def update_view(self, message, ctx, camera_name):
#        try:
#            await asyncio.sleep(5)
#            self.loopcount += 1
#            log.debug("Updating embed.")
#            thumbnails = getCameraThumbs('admin').get(camera_name, [])
#            image_bytes = thumbnail_to_BytesIO(thumbnails[-1])
#
#            embed = message.embeds[0]
#            embed.set_image(url=f"attachment://image{self.loopcount}.jpg")
#            await message.edit(embed=embed, attachments=[discord.File(image_bytes, filename=f"image{self.loopcount}.jpg")])
#        except Exception as e:
#            log.error(f"Exception {e}: {format_exc()}")
#    ##############



async def setup(bot):
    await bot.add_cog(PTZCog(bot))


