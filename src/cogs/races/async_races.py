import re
import logging
import pickle
import traceback
from datetime import datetime, timedelta
from typing import List, Optional

from discord.ext import commands
from discord.utils import get

import constants
from cogs.races.async_race import AsyncRace
from cogs.global_checks import is_admin

class StartAsyncFlags(commands.FlagConverter):
    name: str
    flags: str
    race_role: Optional[str]
    start_timestamp: Optional[int]
    end_timestamp: Optional[int]


class AsyncRaces(commands.Cog):

    def __init__(self, bot, redis_db):
        self.bot = bot
        self.redis_db = redis_db
        self.active_races = dict()
        try:
            self._load_data()
        except Exception as e:
            message = "Error loading saved races, maybe use command clear_db to wipe stored data"
            message += traceback.TracebackException.from_exception(e).format().split[:1900]
            self._send_error(message)
            logging.error("Error loading saved races, maybe use command clear_db to wipe stored data")
            logging.exception(e)

    def is_async_race(self, channel_id):
        return self.active_races.get(channel_id) is not None
    
    def get_race(self, channel_id):
        return self.active_races.get(channel_id)

    def remove_race(self, race):
        del self.active_races[race.race_id]
        self._delete_one(race.race_id)


    @commands.command(aliases=["ca"])
    async def createasync(self, ctx, *, flags: StartAsyncFlags):
        """
        Creates a new async race
        Race is created as a thread of the current channel
        """
        owner = ctx.message.author
        if not is_admin(owner):
            await owner.send("You do not have permission to create async races right now")
            await ctx.message.delete()
            return
        
        if flags.name is None:
            await owner.send("You did not submit a name.")
            await ctx.message.delete()
            return

        race = AsyncRace(
            ctx.channel,
            flags.name,
            owner,
            flags.flags,
            (
                datetime.fromtimestamp(flags.start_timestamp)
                if flags.start_timestamp
                else None
            ),
            (
                datetime.fromtimestamp(flags.end_timestamp)
                if flags.end_timestamp
                else None
            ),
            flags.race_role,
        )

        await race.init_race()
        self.active_races[race.race_id] = race
        self._save_one(race.race_id)
        await ctx.message.delete()


    @commands.command()
    async def startasync(self, ctx):
        thread_id = ctx.channel.id
        race = self.get_race(thread_id)
        if race is None:
            await ctx.author.send("The ?startasync command must be used in an active async race thread")
            await ctx.message.delete()
            return
        
        if not race.is_owner(ctx.author) and not is_admin(ctx.author):
            await ctx.author.send("Only the race owner or admin can start the async race ahead of the scheduled time")
            await ctx.message.delete()
            return
        
        race.start_race()
        self._save_one(race.race_id)


    @commands.command()
    async def endasync(self, ctx):
        thread_id = ctx.channel.id
        race = self.get_race(thread_id)
        if race is None:
            await ctx.author.send("The ?endasync command must be used in an active async race thread")
            await ctx.message.delete()
            return
        
        if ctx.author.id != race.owner.id and not is_admin(ctx.author):
            await ctx.author.send("Only the race owner or admin can end the async race ahead of the scheduled time")
            await ctx.message.delete()
            return

        race.end_race()
        self.remove_race(race)
    

    @commands.command()
    async def purgemembers(self, ctx):
        """
        Removes members from the role associated with the channel,
        works for asyncseedrole and challengeseedrole
        :param ctx: context of the command
        :return: None
        """
        if (self.is_async_race(ctx.channel.id)):
            # purge only on leaderboard races
            return

        user = ctx.message.author
        role = await self.getrole(ctx)

        if role in user.roles and role.name in constants.adminroles:
            if role.name == constants.challengeseedadmin:
                role = get(ctx.message.guild.roles, name=constants.challengeseedrole)
            elif role.name == constants.asyncseedadmin:
                role = get(ctx.message.guild.roles, name=constants.asyncseedrole)
            else:
                role = get(ctx.message.guild.roles, name=constants.ducklingrole)
            members = ctx.message.guild.members
            role_members = [x for x in members if role in x.roles]

            for x in role_members:
                await x.remove_roles(role)
        else:
            await user.send(
                "... Wait a second.. YOU AREN'T AN ADMIN! (note, you"
                " need the correct admin role and need to use this"
                " in the spoilerchat for the role you want to purge"
                " members from)"
            )

        await ctx.message.delete()

    @commands.command()
    async def submit(self, ctx, runnertime: str = None, vod: str = None):
        """
        Submits a runners time to an async race
        :param runnertime: time of the runner, in the format H:M:S, e.g. 2:32:12
        :param vod: link to the vod of the run, required for tournament asyncs
        :param ctx: context of the command
        :return: None
        """
        # check to see if this was submitted to an active race
        race = self.get_race(ctx.channel.id)
        if race is None:
            # if it is not an active race, try and submit it to the leaderboard
            await self.submit_leaderboard(ctx, runnertime)        
        else:
            await race.submit(ctx.author, runnertime, vod, False)
            self._save_one(race.race_id)


    async def submit_leaderboard(self, ctx, runnertime):
        """
        Submits a runners time to a standing leaderboard and gives the appropriate role
        :param runnertime: time of the runner, in the format H:M:S, e.g. 2:32:12
        :param ctx: context of the command
        :return: None
        """
        if (self.is_async_race(ctx.channel.id)):
            # submit only on leaderboard
            return
        
        user = ctx.message.author
        role = await self.getrole(ctx)
        if (
            role.name == constants.ducklingrole
            and constants.rolerequiredduckling not in [role.name for role in user.roles]
        ):
            await user.send("You're not a duckling!")
            await ctx.message.delete()
            return

        if runnertime is None:
            await user.send("You must include a time when you submit a time.")
            await ctx.message.delete()
            return

        if (
            role is not None
            and role not in user.roles
            and role.name in constants.nonadminroles
        ):
            try:
                # convert to seconds using this method to make sure the time is
                # readable and valid
                # also allows for time input to be lazy, ie 1:2:3 == 01:02:03 yet
                # still maintain a consistent style on the leaderboard
                t = datetime.strptime(runnertime, "%H:%M:%S")
            except ValueError:
                await user.send(
                    "The time you provided '"
                    + str(runnertime)
                    + "', this is not in the format HH:MM:SS"
                    "(or you took a day or longer)"
                )
                await ctx.message.delete()
                return

            delta = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
            username = re.sub("[()-]", "", user.display_name)
            leaderboard_msg = await self.getleaderboard(ctx)
            leaderboard_list = leaderboard_msg.content.split("\n")

            # the title is at the start and the forfeit # is after the hyphen at
            # the end of the last line
            title = leaderboard_list[0]
            forfeits = int(leaderboard_list[-1].split("-")[-1])

            # trim the leaderboard to remove the title and forfeit message
            leaderboard_list = leaderboard_list[2 : len(leaderboard_list) - 2]

            for i, _ in enumerate(leaderboard_list):
                leaderboard_list[i] = re.split("[)-]", leaderboard_list[i])[1:]

            # convert the time back to hours minutes and seconds for the
            # leaderboard
            totsec = delta.total_seconds()
            h = int(totsec // 3600)
            m = int((totsec % 3600) // 60)
            s = int((totsec % 3600) % 60)

            leaderboard_list.append([f" {username} ", f"{h}:{m:02d}:{s:02d}"])

            # sort the times
            leaderboard_list.sort(
                key=lambda x: datetime.strptime(x[1].strip(), "%H:%M:%S")
            )

            # build the string for the leaderboard
            new_leaderboard = title + "\n\n"
            for i, leaderboard in enumerate(leaderboard_list):
                new_leaderboard += (
                    str(i + 1) + ")" + leaderboard[0] + "-" + leaderboard[1] + "\n"
                )
            new_leaderboard += "\nForfeits - " + str(forfeits)

            await leaderboard_msg.edit(content=new_leaderboard)
            await user.add_roles(role)
            await (await self.getspoilerchat(ctx)).send(f"GG {user.mention}")
            await ctx.message.delete()
            await self.changeparticipants(ctx)
        else:
            await user.send("You already have the relevent role.")
            await ctx.message.delete()


    @commands.command()
    async def remove(self, ctx):
        """
        Removes people from the leaderboard and allows them to reenter a time
        This entire function is gross, it works but is messy
        :param ctx: context of the command
        :param players: @mentions of the players that will be removed from
                        the leaderboard
        :return: None
        """
        if (self.is_async_race(ctx.channel.id)):
            # remove only on leaderboard races
            return

        user = ctx.message.author
        if ctx.message.mentions is None:
            await user.send("You did not mention a player.")
            await ctx.message.delete()
            return

        channel = ctx.message.channel
        roles = ctx.message.guild.roles
        role = None
        channels = ctx.message.guild.channels
        challengeseed = get(channels, name=constants.challengeseedleaderboard)
        constants.asyncseed = get(channels, name=constants.asyncleaderboard)
        if channel == challengeseed:
            role = get(roles, name=constants.challengeseedadmin)
            remove_role = get(roles, name=constants.challengeseedrole)
            participantnumchannel = get(channels, name=constants.challengeseedchannel)
        if channel == constants.asyncseed:
            role = get(roles, name=constants.asyncseedadmin)
            remove_role = get(roles, name=constants.asyncseedrole)
            participantnumchannel = get(channels, name=constants.asyncchannel)
        if role in user.roles:
            leaderboard = channel.history(limit=100)
            async for x in leaderboard:
                if self.bot.user == x.author:
                    leaderboard = x
                    break

            leaderboard_list = leaderboard.content.split("\n")

            # the title is at the start and the forfeit # is after the hyphen at
            # the end of the last line
            title = leaderboard_list[0]
            forfeits = int(leaderboard_list[-1].split("-")[-1])

            # trim the leaderboard to remove the title and forfeit message
            leaderboard_list = leaderboard_list[2 : len(leaderboard_list) - 2]

            for i, _ in enumerate(leaderboard_list):
                leaderboard_list[i] = re.split("[)-]", leaderboard_list[i])[1:]

            players = ctx.message.mentions
            if not players:
                await user.send("You did not mention a player.")
                await ctx.message.delete()
                return

            for player in players:
                i = 0
                for i, _ in enumerate(leaderboard_list):
                    if leaderboard_list[i][0][
                        1 : len(leaderboard_list[i][0]) - 1
                    ] == re.sub("[()-]", "", player.display_name):
                        del leaderboard_list[i]
                        await player.remove_roles(remove_role)
                        await self.changeparticipants(
                            ctx, increment=False, channel=participantnumchannel
                        )
                        break

            # should already be sorted
            # leaderboard_list.sort(
            #   key=lambda x: datetime.strptime(x[1].strip(), "%H:%M:%S"))

            # build the string for the leaderboard
            new_leaderboard = title + "\n\n"
            for i, leaderboard in enumerate(leaderboard_list):
                new_leaderboard += (
                    str(i + 1) + ")" + leaderboard[0] + "-" + leaderboard[1] + "\n"
                )
            new_leaderboard += "\nForfeits - " + str(forfeits)

            await leaderboard.edit(content=new_leaderboard)
            await ctx.message.delete()


    @commands.Cog.listener()
    async def on_message(self, message):
        """
        on_message listener
        This is used to detect and delete any non-command message by a user from an active race.
        """
        if message.author.id == self.bot.user.id:
            # allow bot messages
            return

        race = self.get_race(message.channel.id)
        if not race:
            return

        # Allow owner messages
        if message.author.id == race.owner.id:
            return
        
        if message.content.startswith("?"):
            return

        await message.delete()

    @commands.command()
    async def createleaderboard(self, ctx, name):
        """
        Creates a leaderboard post with a title and the number of forfeits
        :param ctx: context of the command
        :param name: title of the leaderboard
        :return: None
        """

        user = ctx.message.author
        if name is None:
            await user.send("You did not submit a name.")
            await ctx.message.delete()
            return
        role = await self.getrole(ctx)

        # gross way of doing this, works for now
        if role in user.roles and role.name == constants.challengeseedadmin:
            await get(
                ctx.message.guild.channels, name=constants.challengeseedleaderboard
            ).send(name + "\n\nForfeits - 0")
            await get(
                ctx.message.guild.channels, name=constants.challengeseedchannel
            ).send("Number of participants: 0")

        elif role in user.roles and role.name == constants.asyncseedadmin:
            await get(ctx.message.guild.channels, name=constants.asyncleaderboard).send(
                name + "\n\nForfeits - 0"
            )
            await get(ctx.message.guild.channels, name=constants.asyncchannel).send(
                "Number of participants: 0"
            )

        elif role in user.roles and role.name == constants.ducklingadminrole:
            await get(
                ctx.message.guild.channels, name=constants.ducklingleaderboard
            ).send(name + "\n\nForfeits - 0")
            await get(ctx.message.guild.channels, name=constants.ducklingchannel).send(
                "Number of participants: 0"
            )

        else:
            await user.send(
                (
                    "... Wait a second.. YOU AREN'T AN ADMIN! (note, you"
                    " need the admin role for this channel)"
                )
            )

        await ctx.message.delete()

    async def forfeit(self, ctx):
        """
        Increments the number of forfeits and gives the appropriate
        role to the user
        :param ctx: context of the command
        :return: None
        """
        race = self.get_race(ctx.channel.id)
        if (race is not None):
            await race.submit(ctx.author, "00:00:00", "", True)
            return

        user = ctx.message.author
        role = await self.getrole(ctx)

        if (
            role is not None
            and role not in user.roles
            and role.name in constants.nonadminroles
        ):
            await user.add_roles(role)
            leaderboard = await self.getleaderboard(ctx)
            new_leaderboard = leaderboard.content.split("\n")
            forfeits = int(new_leaderboard[-1].split("-")[-1]) + 1
            new_leaderboard[-1] = "Forfeits - " + str(forfeits)
            seperator = "\n"
            new_leaderboard = seperator.join(new_leaderboard)

            await leaderboard.edit(content=new_leaderboard)
            await ctx.message.delete()
            await self.changeparticipants(ctx)
        else:
            await ctx.message.delete()


    async def spectate(self, ctx):
        """
        Gives the user the appropriate role
        :param ctx: context of the command
        :return: None
        """
        race = self.get_race(ctx.channel.id)
        if (race is not None):
            await race.spectate(ctx.author)
            return 
        
        user = ctx.message.author
        role = await self.getrole(ctx)
        if role is not None and role.name in constants.nonadminroles:
            await user.add_roles(role)
        await ctx.message.delete()


    async def getrole(self, ctx):
        """
        Returns the Role object depending on the channel the command is used in
        Acts as a check for making sure commands are executed in the correct
        spot as well
        :param ctx: context of the command
        :return: Role or None
        """

        user = ctx.message.author
        roles = ctx.message.guild.roles
        channel = ctx.message.channel
        channels = ctx.message.guild.channels
        challengeseed = get(channels, name=constants.challengeseedchannel)
        asyncseed = get(channels, name=constants.asyncchannel)
        ducklingseed = get(channels, name=constants.ducklingchannel)
        chalseedspoilerobj = get(channels, name=constants.challengeseedspoiler)
        asyseedspoilerobj = get(channels, name=constants.asyncspoiler)
        duckseedspoilerobj = get(channels, name=constants.ducklingspoiler)

        if channel == challengeseed:
            role = get(roles, name=constants.challengeseedrole)
        elif channel == asyncseed:
            role = get(roles, name=constants.asyncseedrole)
        elif channel == chalseedspoilerobj:
            role = get(roles, name=constants.challengeseedadmin)
        elif channel == asyseedspoilerobj:
            role = get(roles, name=constants.asyncseedadmin)
        elif channel == ducklingseed:
            role = get(roles, name=constants.ducklingrole)
        elif channel == duckseedspoilerobj:
            role = get(roles, name=constants.ducklingadminrole)
        else:
            await user.send("That command isn't allowed here.")
            return None

        return role


    async def getleaderboard(self, ctx):
        """
        Returns the leaderboard Message object depending on the channel the
        command is used in
        :param ctx: context of the command
        :return: Message or None
        """
        user = ctx.message.author
        channel = ctx.message.channel
        channels = ctx.message.guild.channels
        challengeseed = get(channels, name=constants.challengeseedchannel)
        asyncseed = get(channels, name=constants.asyncchannel)
        ducklingseed = get(channels, name=constants.ducklingchannel)

        if channel == challengeseed:
            leaderboard = get(
                channels, name=constants.challengeseedleaderboard
            ).history(limit=100)
        elif channel == asyncseed:
            leaderboard = get(channels, name=constants.asyncleaderboard).history(
                limit=100
            )
        elif channel == ducklingseed:
            leaderboard = get(channels, name=constants.ducklingleaderboard).history(
                limit=100
            )
        else:
            await user.send("That command isn't allowed here.")
            return None

        async for x in leaderboard:
            # assume that the first bot message we see is the leaderboard
            if self.bot.user == x.author:
                return x
            
        return None


    async def getspoilerchat(self, ctx):
        """
        Returns the spoiler Channel object depending on the channel the command
        is used in
        :param ctx: context of the command
        :return: Channel or None
        """

        user = ctx.message.author
        channel = ctx.message.channel
        channels = ctx.message.guild.channels
        challengeseed = get(channels, name=constants.challengeseedchannel)
        asyncseed = get(channels, name=constants.asyncchannel)
        ducklingseed = get(channels, name=constants.ducklingchannel)

        if channel == challengeseed:
            spoilerchat = get(channels, name=constants.challengeseedspoiler)
        elif channel == asyncseed:
            spoilerchat = get(channels, name=constants.asyncspoiler)
        elif channel == ducklingseed:
            spoilerchat = get(channels, name=constants.ducklingspoiler)
        else:
            await user.send("That command isn't allowed here.")
            return None

        return spoilerchat


    async def changeparticipants(self, ctx, increment=True, channel=None):
        """
        changes the participant number
        :param ctx: context of the command
        :param increment: sets if it is incremented or decremented
        :return: None
        """

        participants: List[Message] = (
            ctx.message.channel if channel is None else channel
        ).history(limit=100)
        async for x in participants:
            if x.author == self.bot.user:
                participants = x
                break
        num_partcipents = int(participants.content.split(":")[1])
        if increment:
            num_partcipents += 1
        else:
            num_partcipents -= 1
        new_participants = "Number of participants: " + str(num_partcipents)
        await participants.edit(content=new_participants)


    async def periodic_race_update(self):
        """
        Meant to be called periodically from the asyncio loop. This
        function checks to see if there are any pending races that need to be started,
        or active races that have an end time set.
        """
        current_time = datetime.now()
        logging.info("Heartbeat check")

        # check for active races that should end
        for race in self.active_races.values():
            if (
                not race.is_started
                and race.start_time is not None
                and race.start_time < current_time
            ):
                await race.start_race()
                await self._save_one(race)
            if (
                race.is_started
                and race.end_time is not None
                and race.end_time < current_time
            ):
                await race.end_race()
                self.remove_race(race)
                

    def _load_data(self):
        logging.info("loading saved races")
        temp = dict(self.redis_db.hgetall('races'))
        for k, v in temp.items():
            self.active_races[k.decode("utf-8")] = pickle.loads(v)
        for race in self.active_races.values():
            logging.debug(race)

    def _save_one(self, id):
        logging.info(f"saving race {id}")
        race = self.active_races[id]
        self.redis_db.hset("races",
                           id, pickle.dumps(race,
                                            protocol=pickle.HIGHEST_PROTOCOL))
        logging.info("saved")
        self._verify_save(id)

    def _delete_one(self, id):
        logging.info(f"deleting race {id}")
        self.redis_db.hdel("races", id)
        logging.info("deleted")

    def _verify_save(self, id):
        original = self.active_races[id]
        saved = pickle.loads(self.redis_db.hget("races", id))
        logging.debug(f"original: {original}")
        logging.debug(f"saved: {saved}")
        logging.debug(saved == original)

    async def _send_error(self, message):
        poor_soul = self.bot.get_user(constants.poor_soul_id)
        await poor_soul.send(message)

