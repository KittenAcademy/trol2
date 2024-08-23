import discord
from discord.ext import commands
from .common import onlyChannel, trolRol
from trol.shared.logger import setup_logger
log = setup_logger('UtilityCog')

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @trolRol()
    async def ping(self, ctx):
        log.debug("Got ping")
        await ctx.send('pong')

    @commands.command()
    @trolRol()
    async def help(self, ctx):
        message = (
            "```"
            "TROL2\n"
            "News Commands:\n"
            " $checknews         = See what news exists\n"
            " $setnews           = Set the news\n"
            " $clearnews         = Delete the news\n"
            "Camera Commands:\n"
            " $caminfo           = Information on all cameras\n"
            " $camgridjpg        = Display all cameras in a static image\n"
            " $camgrid           = Display a single GIF of all cameras\n"
            " $camchange POS CAM = Change the camera at position POS to CAM\n"
            " $camcheck CAM      = Show camera info and preview gif\n"
            " $camprivate CAM    = Set a camera inaccessable to all remote users including you\n"
            " $fullscreen POS    = Set a position (not a camera) fullscreen\n"
            " $reset_scene       = Undo fullscreen and any other shenanigans.\n"
            "```"
            )
        await ctx.send(message)
        message = (
            "```"
            "PTZ Commands:\n"
            " $camgoto CAM LOC   = PTZ control, send camera to locations\n"
            "                      LOC can be 'undo', name or x,y,z\n"
            " $camvector CAM VECTOR = move x,y,z relative to current position\n"
            " $saveposition CAM NAME COORDS = Save a position.\n"
            "                     uses current position if COORDS are omitted\n"
            " $delposition CAM NAME = delete an existing position name\n"
            " $getposition CAM   = gets the current position (and a screenshot)\n"
            "   PTZ coordinates are always x,y,z x,y range -1 to 1, z range 0 to 1\n"
            "```"
            )
        await ctx.send(message)
        message = (
            "```"
            "Voting Controls\n"
            " $camselect POS...  = Display all cameras, pick one or more to put on the stream\n"
            "                      POS is optional; if omitted will attempt to set all positions\n"
            " $campoll POS...    = $camselect but polls users in user channel\n"
            " $lockposition POS SEC = Lock camera in position POS for SEC seconds\n"
            "                       = SEC is optional, defaults to 600\n"
            " $unlockposition POS   = Unlock position\n"
            " $hidecamera CAM       = Hide camera from voters\n"
            " $unhidecamera CAM     = Unhide camera from voters\n"
            " $setnicename CAM NAME = Give a camera a user-friendly alias for voters\n"
            "OBS Controls\n"
            " $stopstreaming        = Stop the live stream!\n"
            " $startstreaming       = Start the live stream!\n"
            " $startrecording       = Start recording (e.g. micro-closeup)\n"
            " $stoprecording        = Stop recording\n"
            "Other:\n"
            " $help              = This\n"
            " $ping              = Pong\n"
            "```"
        )
        await ctx.send(message)

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))


