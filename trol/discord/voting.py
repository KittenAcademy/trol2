import discord
import asyncio
from discord.ext import commands, tasks
from discord.ui import Select, View
from .common import onlyChannel, trolRol, send_to_channel, requestCameraInPosition, getCameraThumbs
from io import BytesIO
from base64 import b64decode
from time import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from traceback import format_exc

import math
from trol.shared.logger import setup_logger, set_debug
log = setup_logger('VotingCog')
set_debug(log)


class CamVotingMenu(discord.ui.Select):
    def __init__(self, options, vote_storage, nice_name_map):
        super().__init__(
            placeholder="Choose one or more options...",
            min_values=1,
            max_values=len(options),
            options=options,
        )
        self.vote_storage = vote_storage
        self.nice_name_map = nice_name_map

    async def callback(self, interaction: discord.Interaction):
        selected_options = self.values
        user_id = interaction.user.id

        # Store the latest selections of the user
        self.vote_storage[user_id] = selected_options
        log.debug(f"{interaction.user.name} selected {selected_options}")
        nice_selected_options = [self.nice_name_map[camname] for camname in selected_options]
        await interaction.response.send_message(f"You selected: {', '.join(nice_selected_options)}", ephemeral=True)

class CamVotingView(discord.ui.View):
    def __init__(self, options, vote_storage, nice_name_map):
        super().__init__()
        self.vote_storage = vote_storage
        self.menu = CamVotingMenu(options, vote_storage, nice_name_map)
        self.add_item(self.menu)

def create_image_grid(images, text_labels, font_size = 25):
    grid_size = math.ceil(math.sqrt(len(images)))
    img_width, img_height = images[0].size

    grid_img_width = grid_size * img_width
    grid_img_height = grid_size * img_height
    grid_img = Image.new('RGB', (grid_img_width, grid_img_height), color='black')

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        log.debug("Loaded DejaVuSans.ttf")
    except IOError:
        font = ImageFont.load_default()
        log.debug("Loaded default font.")

    for index, image in enumerate(images):
        x = (index % grid_size) * img_width
        y = (index // grid_size) * img_height
        grid_img.paste(image, (x, y))

        draw = ImageDraw.Draw(grid_img)
        text_label = text_labels[index]
        draw.text((x + 10, y + 10), text_label, fill="white", font=font)

    return grid_img

def decode_image(b64_string):
    image_data_b64 = b64_string.removeprefix("data:image/jpg;base64,")
    image_data = b64decode(image_data_b64)
    return Image.open(BytesIO(image_data))

# TODO: Maybe put this in common.
async def get_ctx_from_channel(bot, channel: discord.TextChannel):
    # Create a fake message object
    message = discord.Message(state=channel._state, channel=channel)
    # Create the context
    ctx = commands.Context(bot=bot, message=message, prefix="", command=None)

    return ctx

def get_time_strings(epoch_time):

    interval = epoch_time - time() 

    # Human-readable amount of time (since the epoch)
    total_seconds = int(interval)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    #human_readable_time = f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds"
    human_readable_time = ""
    if minutes:
        human_readable_time = f"{minutes} minutes, {seconds} seconds"
    else:
        human_readable_time = f"{seconds} seconds"


    # Formatted clock time in YYYY-MM-DD HH:MM:SS for the current timezone
    # formatted_time = datetime.fromtimestamp(epoch_time).strftime('%Y-%m-%d %H:%M:%S')
    formatted_time = datetime.fromtimestamp(epoch_time).strftime('%H:%M:%S')

    return formatted_time, human_readable_time

class VotingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_poll_cameras.start()
        self.auto_poll_status_message = None
        self.last_auto_poll = time()
        self.poll_active = False

    async def make_user_channel_message(self, text=""):
        c = self.bot.get_channel(int(self.bot.settings.discord.user_channel))
        if(c is None):
            log.error(f"Can't get user channel! {bot.settings.discord.user_channel}")
            return
        message = await c.send(text)
        return message

    def get_next_poll_time(self):
        # Determine whether the next poll is at the scheduled time or at a later time because admins are active:
        nominal_poll_time = self.last_auto_poll + self.bot.settings.discord.voting.poll_interval
        admin_poll_delay_time = self.bot.last_admin_activity + self.bot.settings.discord.voting.admin_inactivity_period
        next_poll_time = max(nominal_poll_time, admin_poll_delay_time)
        
        return next_poll_time


    async def update_auto_poll_message(self):
        try:
            if self.poll_active:
                return

            now = time()
            next_poll_time = self.get_next_poll_time()
            time_until_poll = next_poll_time - now

            message = ""

            if self.bot.settings.discord.voting.enable_autopoll:
                if time_until_poll >= 0: 
                    time_string, human_time_string = get_time_strings(next_poll_time)
                    message = f"Next camera selection in {human_time_string} at {time_string}\n(NOTE: Scheduled time will frequently be pushed back.  Poll time not guaranteed.)\n\n"
                else:
                    message = f"Next camera selection imminent!\n\n\n"
            else:
                message = "Camera selection is currently offline.\n\n\n"

            message += f"Current cameras:\n"
            for position_name in self.bot.settings.discord.voting.positions:
                position = self.bot.positions.getByName(position_name)
                nice_position_name = position.nice_name
                nice_camera_name = self.bot.cameras.getByName(position.active).nice_name
                message += f"{nice_position_name}: {nice_camera_name}\n"

            if self.auto_poll_status_message is None:
                self.auto_poll_status_message = await self.make_user_channel_message(message)
            else:
                await self.auto_poll_status_message.edit(content=message)
        except Exception as e:
            log.error(f"Caught exception {e}: \n{format_exc()}")



    @tasks.loop(seconds=10) 
    async def auto_poll_cameras(self):
        await self.bot.wait_until_ready()
        try:

            if self.poll_active:
                return

            await self.update_auto_poll_message()
            
            channel = self.bot.get_channel(int(self.bot.settings.discord.user_channel))
            if channel is None:
                log.error(f"I can't find the user channel {self.bot.settings.discord.user_channel}.")
                return

            if not self.bot.settings.discord.voting.enable_autopoll:
                # log.debug("Not autopolling because autopoll is not enabled.")
                return

            now = time()
            next_poll_time = self.get_next_poll_time()
            time_until_poll = next_poll_time - now

            if now < next_poll_time:
                if time_until_poll < 15.0:
                    self.auto_poll_cameras.change_interval(seconds=1)
                time_string, human_time_string = get_time_strings(next_poll_time)
                # log.debug(f"Not autopolling for {human_time_string} at {time_string}")
                return
            
            log.debug("Beginning poll.")
            # We're clear, poll it.
            await self.reset_auto_poll()

            await self.poll_cameras(channel)

        except Exception as e: 
            log.error(f"Exception {e} attempting autopoll.")
            log.error(format_exc())

#    @auto_poll_cameras.before_loop
#    async def before_auto_poll_cameras(self):
#        await self.bot.wait_until_ready()  # Ensure the bot is ready
#        log.debug(f"Setting up atuomatic polling every {self.poll_interval} seconds.")
#        self.auto_poll_cameras.change_interval(seconds=self.poll_interval)

    def cog_unload(self):
        self.auto_poll_cameras.cancel()


    @commands.command()
    @onlyChannel()
    @trolRol()
    async def campoll(self, ctx, *position_names):
        """ Run the poll in the user channel even if this was initiated from the admin channel. """
        channel = self.bot.get_channel(int(self.bot.settings.discord.user_channel))
        if channel is None:
            await ctx.send(f"I can't find the user channel.")
            return

        user_ctx = await self.bot.get_context(ctx.message)
        user_ctx.channel = channel
        user_ctx.send = channel.send

        # Any user poll should reset the autopoll.
        await self.reset_auto_poll()

        await self.poll_cameras(user_ctx, position_names=position_names, access_level='Discord user')

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camselect(self, ctx, *position_names):
        await self.poll_cameras(ctx, position_names=position_names, access_level='admin')

    async def reset_auto_poll(self):
        if self.auto_poll_status_message is not None:
            await self.auto_poll_status_message.delete()
            self.auto_poll_status_message = None

        self.last_auto_poll = time()
        self.auto_poll_cameras.change_interval(seconds=10)

    # position_names in legacy format.
    async def poll_cameras(self, ctx, position_names=None, access_level='Discord user'):
        position_list = []
        if position_names:
            position_list = [self.bot.settings.legacy_position_prefix + position_name for position_name in position_names 
                             if not self.bot.positions.positionIsLocked(self.bot.settings.legacy_position_prefix + position_name, access_level=access_level)]
        else:
            position_list = [position_name for position_name in self.bot.settings.discord.voting.positions
                             if not self.bot.positions.positionIsLocked(position_name, access_level=access_level)]
        
        if len(position_list) == 0:
            await ctx.send("No vote possible currently (no positions eligible).")
            return

        # get subset of cameras allowed in position by config and by access level
        if access_level == 'admin':  # Admins aren't constrained by your petty rules.
            cameras_touse = getCameraThumbs(access_level).keys()
        else:
            eligible_cameras = set()
            for position in position_list:
                cameras_for_position = self.bot.settings.discord.voting.voting_camera_limits.get(position, [])
                eligible_cameras.update(cameras_for_position)
            log.debug(f"All cameras: {eligible_cameras}")
            # limit to only cameras that are publically accessable.
            cameras_touse = [camera for camera in getCameraThumbs().keys() 
                             if camera in eligible_cameras]
            # Filter out cameras that are active in non-voting positions
            non_voting_active_cameras = [self.bot.positions.getByName(position).active for position in self.bot.settings.discord.voting.positions if position not in position_list]
            cameras_touse = [camera for camera in cameras_touse if camera not in non_voting_active_cameras]

        log.debug(f"cameras to use: {cameras_touse}")

        if len(cameras_touse) == 0:
            await ctx.send("No cameras are eligible to poll.", delete_after = 20)
            return

        # get current cameras in voting positions and select them for the voting user
        pre_selected_cameras = [self.bot.positions.getByName(position_name).active for position_name in position_list]

        nice_position_names = [self.bot.positions.getByName(position_name).nice_name or self.bot.positions.getByName(position_name)[_name] 
                               for position_name in position_list]
        embed = discord.Embed(
            title="Choose your cameras!",
            description="We are voting for cameras in the " + ', '.join(nice_position_names) + f" position(s).  The most voted-for option(s) will go on the stream.  You can vote for as many as you want and you can change your vote until voting is over in {self.bot.settings.discord.voting.duration} seconds."
        )

        vote_duration = self.bot.settings.discord.voting.duration
        display_duration = self.bot.settings.discord.voting.display_duration
        filedata = self.create_grid_gif(eligible_cameras = cameras_touse, access_level=access_level)
        filename = "camgrid.gif"
        embed.set_image(url=f"attachment://{filename}")
        vote_storage = {}

        # Post the vote
        nice_name_map = {camera_name: self.bot.cameras.getByName(camera_name).nice_name for camera_name in cameras_touse}
        vote_view = CamVotingView(self.getCamVotingOptions(eligible_cameras = cameras_touse, 
                                                           selected_cameras = pre_selected_cameras,
                                                           access_level=access_level ),
                                  vote_storage,
                                  nice_name_map)

        self.poll_active = True
        message = await ctx.send(embed=embed, 
                                 file=discord.File(filedata, filename=filename), 
                                 delete_after=self.bot.settings.discord.voting.display_duration, 
                                 view=vote_view )

        # Schedule the vote tallying task
        self.tally_cam_votes.start(ctx, message.id, vote_storage, position_list)

    def getCamVotingOptions(self, access_level='Discord user', eligible_cameras=None, selected_cameras=None):
        public_camthumbs = getCameraThumbs(access_level)
        # Limit our options to only the specified cameras
        if eligible_cameras:
            public_camthumbs = {camname: public_camthumbs[camname] for camname in eligible_cameras}
        # Optionally pre-select cameras
        if selected_cameras is None:
            selected_cameras = []

        tagemoji = discord.PartialEmoji(name="tv~1", id=927254653383610388)
        options = [
            discord.SelectOption(
                label=camname if access_level == 'admin' else self.camera_name_to_nice_name(camname),
                value=camname,
                # default=(camname in selected_cameras)
                emoji = tagemoji if camname in selected_cameras else None
            )
            for camname in public_camthumbs.keys()
        ]
        return options


    @tasks.loop(count=1)
    async def tally_cam_votes(self, ctx, message_id, vote_storage, position_list):
        try: # Discord.py eats our exceptions unless we specifically catch them.
            duration = self.bot.settings.discord.voting.duration
            display_duration = self.bot.settings.discord.voting.display_duration

            # Initial message
            message = await ctx.send(f"Vote tally in progress.\n\n{duration}s remaining...")

            # Loop to update the message every X seconds
            update_interval = 3  # Adjust this value to change how often the message updates
            for remaining in range(duration, 0, -update_interval):
                # Tally the votes so far
                vote_count = {}
                for votes in vote_storage.values():
                    for vote in votes:
                        if vote in vote_count:
                            vote_count[vote] += 1
                        else:
                            vote_count[vote] = 1

                # Calculate total votes
                total_votes = sum(vote_count.values())

                # Sort votes by count, descending
                sorted_votes = sorted(vote_count.items(), key=lambda item: item[1], reverse=True)[:5]

                current_cameras_message = f"Current cameras (tagged with icon in poll options):\n"
                for position_name in self.bot.settings.discord.voting.positions:
                    position = self.bot.positions.getByName(position_name)
                    nice_position_name = position.nice_name
                    nice_camera_name = self.bot.cameras.getByName(position.active).nice_name
                    current_cameras_message += f"{nice_camera_name}\n"


                # Create the updated results message
                if total_votes == 0:
                    results_message = f"No votes yet.\n\n{remaining}s remaining..."
                else:
                    results_message = f"Top 5 results so far:\n"
                    for cam, count in sorted_votes:
                        percentage = (count / total_votes) * 100
                        cam_nice_name = self.camera_name_to_nice_name(cam)
                        results_message += f"{cam_nice_name}: {percentage:.2f}% of votes\n"
                    results_message += f"\n{remaining}s remaining..."

                # Edit the message with updated vote counts and remaining time
                await message.edit(content=current_cameras_message + '\n' + results_message)

                # Wait for the next update
                await asyncio.sleep(update_interval)

            # Final tally after time is up
            vote_count = {}
            for votes in vote_storage.values():
                for vote in votes:
                    if vote in vote_count:
                        vote_count[vote] += 1
                    else:
                        vote_count[vote] = 1

            total_votes = sum(vote_count.values())
            sorted_votes = sorted(vote_count.items(), key=lambda item: item[1], reverse=True)[:5]

            # Final results message
            if total_votes == 0:
                final_message = "Time's up; nobody voted."
            else:
                final_message = "Voting has ended! Here are the top 5 results:\n"
                for cam, count in sorted_votes:
                    percentage = (count / total_votes) * 100
                    cam_nice_name = self.camera_name_to_nice_name(cam)
                    final_message += f"{cam_nice_name}: {percentage:.2f}% of votes\n"

            await message.edit(content=final_message)
            await message.delete(delay=display_duration - duration)

            # Handle the results
            await self.handle_vote_results(ctx, sorted_votes, position_list)
            await self.reset_auto_poll()
            self.poll_active = False

        except Exception as e:
            log.error(f"Caught exception {e}: \n{format_exc()}")


    async def handle_vote_results(self, ctx, sorted_votes, position_list, access_level='Discord user'):
        for position_name in position_list:
            if self.bot.positions.positionIsLocked(position_name, access_level=access_level):
                continue

            eligible_cameras = self.bot.settings.discord.voting.get('voting_camera_limits',{}).get(position_name, [])
            for camera_name, votes in sorted_votes:
                log.debug(f"Considering {position_name} for {camera_name}...")
                if votes == 0:
                    log.debug(f"{camera_name} got no votes.")
                    break
                if camera_name not in eligible_cameras:
                    log.debug(f"{position_name} not eligible for {camera_name} only {eligible_cameras}")
                    continue

                log.info(f"Setting {camera_name} in position {position_name} by popular demand.")
                nice_camera_name = self.bot.cameras.getByName(camera_name).nice_name
                nice_position_name = self.bot.positions.getByName(position_name).nice_name
                await ctx.send(f"Setting {nice_camera_name} in position {nice_position_name} by popular demand.",
                               delete_after=self.bot.settings.discord.voting.display_duration - self.bot.settings.discord.voting.duration)
                requestCameraInPosition(camera_name, position_name, access_level=access_level)
                sorted_votes.remove((camera_name, votes))
                break

    def create_grid_single(self, access_level='Discord user', extension='JPEG', eligible_cameras=None):
        public_camthumbs = getCameraThumbs(access_level)
        if eligible_cameras:
            public_camthumbs = { camname: public_camthumbs[camname] for camname in eligible_cameras }

        images = [decode_image(thumbs[-1]) for thumbs in public_camthumbs.values()]
        if access_level == 'admin':
            text_labels = list(public_camthumbs.keys())
        else:
            text_labels = [self.camera_name_to_nice_name(camname) for camname in public_camthumbs.keys()]


        grid_image = create_image_grid(images, text_labels)
        bytes_io = BytesIO()
        grid_image.save(bytes_io, format=extension)
        bytes_io.seek(0)
        return bytes_io

    def create_grid_gif(self, access_level='Discord user', duration_ms=500, eligible_cameras=None):
        public_camthumbs = getCameraThumbs(access_level)
        if eligible_cameras:
            public_camthumbs = { camname: public_camthumbs[camname] for camname in eligible_cameras }


        # Always 3 frames
        gif_frames = 3
        for camname, thumbs in public_camthumbs.items():
            while len(thumbs) < gif_frames:
                thumbs.append(thumbs[-1])

        # Transpose the thumbs
        images = [
            [decode_image(thumbs[i]) for thumbs in public_camthumbs.values()]
            for i in range(gif_frames)
        ]

        if access_level == 'admin':
            text_labels = list(public_camthumbs.keys())
        else:
            text_labels = [self.camera_name_to_nice_name(camname) for camname in public_camthumbs.keys()]

        grid_images = [create_image_grid(images_b64, text_labels)
                       for images_b64 in images]

        # Convert grid images to BytesIO objects and then to PIL Images
        frames = []
        for grid_image in grid_images:
            bytes_io = BytesIO()
            grid_image.save(bytes_io, format='PNG')
            bytes_io.seek(0)
            frames.append(Image.open(bytes_io))

        # Save frames as a GIF
        gif_bytes_io = BytesIO()
        frames[0].save(gif_bytes_io, format='GIF', save_all=True, append_images=frames[1:], duration=duration_ms, loop=0)
        gif_bytes_io.seek(0)
        return gif_bytes_io
         
    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camgrid(self, ctx):
        """ Display a GIF of all cameras together. """
        gif_bytes_io = self.create_grid_gif(access_level='admin')
        await send_to_channel("Here's all the cameras.", filedata=gif_bytes_io, filename=f"camera_grid.gif", duration=60)

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def camgridjpg(self, ctx):
        """ Display a JPG of all cameras together. """
        gif_bytes_io = self.create_grid_single(access_level='admin')
        await send_to_channel("Here's all the cameras.", filedata=gif_bytes_io, filename=f"camera_grid.jpg", duration=60)

    @commands.command()
    @onlyChannel()
    @trolRol()
    async def setnicename(self, ctx, camera_name, *nice_name):
        self.bot.cameras.getByName(camera_name).nice_name = " ".join(nice_name)
        await ctx.send(f"{camera_name} is now called {' '.join(nice_name)} by the people who can't handle the truth.")

    # TODO: Maybe put this in common
    def nice_name_to_camera_name(self, nice_name: str):
        for camera_name, camera in self.bot.cameras.items():
            if camera.nice_name == nice_name:
                return camera_name
        return nice_name

    def camera_name_to_nice_name(self, camera_name: str):
        camera = self.bot.cameras.getByName(camera_name)
        if camera.nice_name:
            return camera.nice_name
        return camera_name


async def setup(bot):
    await bot.add_cog(VotingCog(bot))


