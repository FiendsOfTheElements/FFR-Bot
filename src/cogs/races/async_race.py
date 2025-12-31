from datetime import datetime, timedelta
import logging
import re

import discord
from discord.utils import get
from discord.ext.commands import CommandError
from cogs.races.races_common import flagseedgen


class AsyncRace:
    """
    Represents an async race (in a tournamet, LL, or runner started)
    """

    def __init__(
        self,
        race_channel,
        name,
        owner,
        flags: str,
        start_time = None,
        end_time = None,
        race_role = None,
    ):
        self.race_channel = race_channel
        self.race_id = None
        self.race_thread = None
        self.spoiler_thread = None
        self.name = name
        self.owner = owner
        self.flags = flags
        self.start_time = start_time
        self.end_time = end_time
        self.race_role = race_role
        self.seed = None
        self.is_started = False
        self.is_finished = False
        self.announcement_message = None
        self.leaderboard_message = None
        self.leaderboard = []

    async def init_race(self, purge_role=False):
        """
        Initializes (and possibly starts) the async race        
        """
        if self.is_started or self.is_finished:
            logging.info(
                "Call to init_race while {%s} was already initialized", self.name
            )
            raise CommandError

        # create the race thread
        self.race_thread = await self.race_channel.create_thread(
            name=self.name, message=None, type=discord.ChannelType.public_thread, reason="bot generated thread for async race")

        self.spoiler_thread = await self.race_channel.create_thread(
            name=f"{self.name} - Spoilers", message=None, type=discord.ChannelType.private_thread, reason="bot generated spoiler thread for async"
        )

        await self.race_thread.add_user(self.owner)
        await self.spoiler_thread.add_user(self.owner)

        self.race_id = self.race_thread.id
                
        if self.start_time is None:
            await self.start_race()
        else:
            self.announcement_message = await self.race_thread.send(
                f"Async race {self.name} has been scheduled for <t:{self.start_time.timestamp()}:F>"
            )

        
    async def start_race(self, purge_role=False):
        """
        If the start time has passed, opens the race to submissions.
        This is done by posting the name and seed along with instructions in a
        pinned message, and then the "leaderboard" placeholder in a second message.
        """
        if self.is_started or self.is_finished:
            logging.info(
                "Call to start_race while {%s} was not in ready state", self.name
            )
            raise CommandError

        if (purge_role):
            role_members = [x for x in self.race_thread.guild.members if self.race_role in x.roles]
            for m in role_members:
                await m.remove_roles(self.race_role)

        self.seed = flagseedgen(self.flags)
        race_str = f"**{self.name}**\n\n"
        if self.end_time is not None:
            race_str += f"Async race has started. You have until <t:{self.end_time.timestamp()}:F> to submit your time.\n"
        else:
            race_str += "Async race has started. You have until this thread is closed to submit your time.\n"
        
        race_str += "To submit a time, use the command `?submit <time> <vod>`\n"
        race_str += "To forfeit, use the command `?forfeit` or `?ff`. No vod is required for a forfeit.\n"
        race_str += "GLHF to all the runners.\n\n"
        race_str = race_str + f"{self.seed}\n\n"
        
        if self.announcement_message is not None:
            await self.announcement_message.edit(content=race_str)
        else:
            self.announcement_message = await self.race_thread.send(race_str)

        self.leaderboard_message = await self.race_thread.send(
            "Number of participants: 0"
        )

        self.is_started = True

    async def end_race(self):
        """
        Closes the race to submissions. Replaces the leaderboard message with the final leaderboard
        results and pins it.
        """
        if not self.is_started or self.is_finished:
            logging.info(
                "call to end_race while {%s} was not in active state", self.name
            )
            raise CommandError

        finished_racers = [entry for entry in self.leaderboard if not entry.is_forfeit and not entry.is_spectator]
        finished_racers.sort(key=lambda x: x.time_delta)
        leaderboard_str = "Final Leaderboard:\n"
        for i, entry in enumerate(finished_racers):
            leaderboard_str = leaderboard_str + f"{i+1}. {str(entry)}\n"

        forfeits = [entry for entry in self.leaderboard if entry.is_forfeit and not entry.is_spectator]
        leaderboard_str = leaderboard_str + "\n\nForfeits:\n"
        for i, entry in enumerate(forfeits):
            leaderboard_str = leaderboard_str + f"{i+1}. {str(entry)}\n"

        # Grant the race role to all participants
        # participants = [entry.runner for entry in self.leaderboard]
        # for _, participant in enumerate(participants):
        #    role = get(self.race_thread.guild.roles, name=self.race_role)
        #    await participant.add_roles(role)

        # post the final leaderboard
        await self.race_channel.send(leaderboard_str)

        self.is_started = False
        self.is_finished = True

    async def submit(self, runner, runner_time, vod, is_forfeit):
        """
        Submits a time to the async. This sends a message to the owner and adds the runner to the spoiler thread, 
        but does not publish the time until the race has finished.
        """
        # Guard conditions
        if not self.is_started or self.is_finished:
            await self.owner.send(f"{self.name} is not open for time submissions")
            return
        if runner in self.leaderboard:
            await self.owner.send("You have already submitted a time for this race")
            return

        entry = AsyncLeaderboardEntry(runner, runner_time, vod, is_forfeit)
        self.leaderboard.append(entry)
        await self.spoiler_thread.add_user(runner)
        await self.leaderboard_message.edit(
            content=f"Number of participants: {len(self.leaderboard)}"
        )
        await self.owner.send(f"Time submitted for {self.name}: {str(entry)}")

    async def spectate(self, user):
        """
        Adds the user to the spoiler thread for this race
        """
        await self.spoiler_thread.add_user(user)

    def is_owner(self, user):
        """
        Returns true if the current user is the owner of this race
        """
        return user.id == self.owner.id

    def export_leaderboard(self):
        """
        Returns the leaderboard as a comma separated string
        """
        leaderboard_str = "Runner,Time,VOD\n"
        for entry in self.leaderboard:
            if (not entry.is_spectator):
                leaderboard_str = leaderboard_str + f"{entry.runner_name},{entry.runner_time if not entry.is_forfeit else "DNF"},{entry.vod}\n"
        return leaderboard_str
    
    def __eq__(self, other):
        if self.race_id is not None:
            return self.race_id == other.race_id
        return self.name == other.name and self.race_channel == other.race_channel

class AsyncLeaderboardEntry:
    """
    Entry in the leaderboard for an async race
    """

    def __init__(self, runner, runner_time: str, vod: str, is_forfeit=False, is_spectator=False):
        """
        runner_name - name of the submitter to the leaderboard
        time - runners time in HH:MM:SS format
        vod - link to the vod for this run
        is_forfeit - True if this entry is a forfeit / DNF, false otherwise
        """
        self.runner = runner
        self.runner_name = re.sub("[()-]", "", runner.display_name)
        self.runner_time = runner_time
        self.time_delta = self._get_time_delta(runner_time)
        self.vod = vod
        self.is_forfeit = is_forfeit
        self.is_spectator = is_spectator

    def __str__(self):
        if self.is_forfeit:
            return f"{self.runner_name} - Forfeit"

        totsec = self.time_delta.total_seconds()
        h = int(totsec // 3600)
        m = int((totsec % 3600) // 60)
        s = int((totsec % 3600) % 60)
        # convert the time back to hours minutes and seconds for the
        # leaderboard
        entry_str = f"{self.runner_name} - {h:%d}:{m:%02d}:{s:%02d}"
        if self.vod:
            entry_str = entry_str + f"- {self.vod}"

        return entry_str

    def __eq__(self, other):
        return self.runner.id == other.runner.id

    def _get_time_delta(self, runner_time: str):
        t = datetime.strptime(runner_time, "%H:%M:%S")
        return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
