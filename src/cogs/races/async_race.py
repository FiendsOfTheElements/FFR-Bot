from datetime import datetime, timedelta
import io
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
        self.spoiler_leaderboard_message = None
        self.leaderboard = []

    @classmethod
    async def from_dict(cls, data, bot):
        """
        Creates an AsyncRace object from the dictionary representation in redis
        """
        channel = await bot.fetch_channel(data["race_channel_id"])
        owner = await bot.fetch_user(data["owner_id"])
        race = cls(
            channel, data["name"], owner, data["flags"],
            data["start_time"], data["end_time"], data["race_role"]
        )

        # set the rest of the fields
        race.race_id = data["race_id"]
        race.race_thread = channel.get_thread(data["race_thread_id"])
        race.spoiler_thread = channel.get_thread(data["spoiler_thread_id"])
        race.seed = data["seed"]
        race.is_started = data["is_started"]
        race.is_finished = data["is_finished"]
        race.announcement_message = await race.race_thread.fetch_message(data["announcement_message_id"])
        if data["leaderboard_message_id"] is not None:
            race.leaderboard_message = await race.race_thread.fetch_message(data["leaderboard_message_id"])
        if data.get("spoiler_leaderboard_message_id") is not None:
            race.spoiler_leaderboard_message = await race.spoiler_thread.fetch_message(data["spoiler_leaderboard_message_id"])
        race.leaderboard = data["leaderboard"]
        return race

    def to_dict(self): 
        return {
            "race_channel_id": self.race_channel.id,
            "race_id": self.race_id,
            "race_thread_id": self.race_thread.id,
            "spoiler_thread_id": self.spoiler_thread.id,
            "name": self.race.name,
            "owner_id": self.owner.id,
            "flags": self.flags,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "race_role": self.race_role,
            "seed": self.seed,
            "is_started": self.is_started,
            "is_finished": self.is_finished,
            "announcement_message_id": self.announcement_message.id,
            "leaderboard_message_id": self.leaderboard_message.id if self.leaderboard_message else None,
            "spoiler_leaderboard_message_id": self.spoiler_leaderboard_message.id if self.spoiler_leaderboard_message else None,
            "leaderboard": self.leaderboard
        }    

    async def init_race(self):
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
            name=f"[Spoiler] - {self.name}", message=None, type=discord.ChannelType.private_thread, reason="bot generated spoiler thread for async", invitable=False,
        )

        await self.race_thread.add_user(self.owner)
        await self.spoiler_thread.add_user(self.owner)

        # if role is set, add all members with that role to the race
        if (self.race_role is not None):
            roles = self.race_thread.guild.roles
            role = next((r for r in roles if r.name == self.race_role), None)
            if role is not None:
                for member in role.members:
                    await self.race_thread.add_user(member)

        self.race_id = self.race_thread.id
                
        if self.start_time is None:
            await self.start_race()
        else:
            self.announcement_message = await self.race_thread.send(
                f"Async race {self.name} has been scheduled for <t:{int(self.start_time.timestamp())}:F>"
            )

        
    async def start_race(self):
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
            
        self.seed = flagseedgen(self.flags)
        race_str = f"**{self.name}**\n\n"
        if self.end_time is not None:
            race_str += f"Async race has started. You have until <t:{int(self.end_time.timestamp())}:F> to submit your time.\n"
        else:
            race_str += "Async race has started. You have until this thread is closed to submit your time.\n"
        
        race_str += "To submit a time, use the command `?submit <time> <vod>`\n"
        race_str += "To forfeit, use the command `?forfeit` or `?ff`. No vod is required for a forfeit.\n"
        race_str += "To spectate, use the command `?spectate` or `?spec`.\n\n"
        race_str += "GLHF to all the runners.\n\n"
        race_str = race_str + f"{self.seed}\n\n"

        if self.announcement_message is not None:
            await self.announcement_message.edit(content=race_str)
        else:
            self.announcement_message = await self.race_thread.send(race_str)

        if self.race_role is not None:
            role = get(self.race_thread.guild.roles, name=self.race_role)
            if role is not None:
                await self.race_thread.send(role.mention)
        
        self.leaderboard_message = await self.race_thread.send(
            "Number of participants: 0"
        )

        self.spoiler_leaderboard_message = await self.spoiler_thread.send(
            "Current Leaderboard:\nNo finishers yet!"
        )
        await self.spoiler_leaderboard_message.pin()

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
        leaderboard_str = leaderboard_str + self._build_leaderboard_string()

        # post the final leaderboard
        await self.race_thread.send(leaderboard_str)

        # send the CSV export to the owner
        leaderboard_csv = self.export_leaderboard()
        file_data = io.BytesIO(leaderboard_csv.encode('utf-8'))
        await self.owner.send(f"Here is the CSV export of the final leaderboard for {self.name}:", file=discord.File(fp=file_data, filename=f"{self.name}_leaderboard.csv"))

        self.is_started = False
        self.is_finished = True

    async def cancel_race(self):
        """
        Cancels a scheduled race
        """
        if self.is_started or self.is_finished:
            logging.info("Cannot cancel started races, they must be ended instead")
            return

        await self.spoiler_thread.delete()
        await self.race_thread.send("This race has been cancelled.")
        self.is_finished = True

    async def submit(self, runner, runner_time, vod, is_forfeit):
        """
        Submits a time to the async. This sends a message to the owner and adds the runner to the spoiler thread, 
        but does not publish the time until the race has finished.
        """
        # Guard conditions
        if not self.is_started or self.is_finished:
            await runner.send(f"{self.name} is not open for time submissions")
            return
        if runner.id in self.leaderboard:
            await runner.send("You have already submitted a time for this race")
            return
        if vod is None and not is_forfeit:
            await runner.send("You must provide a VOD link when submitting a time")
            return
        
        try:
            if not is_forfeit:
                if runner_time.count(":") == 1:
                    # allow for MM:SS format
                    runner_time = "00:" + runner_time

                datetime.strptime(runner_time, "%H:%M:%S")
        except ValueError:
            await runner.send("The time you provided '"
                    + str(runner_time)
                    + "' is not in the format HH:MM:SS")
            return
        
        entry = AsyncLeaderboardEntry(runner, runner_time, vod, is_forfeit)
        self.leaderboard.append(entry)
        
        # Spoiler thread updates
        await self.spoiler_thread.add_user(runner)
        await self.spoiler_thread.send(f"GG {runner.mention}")
        if self.spoiler_leaderboard_message is not None:
            await self.spoiler_leaderboard_message.edit(
                content="Current Leaderboard:\n" + self._build_leaderboard_string(show_bins=False)
            )
        else:
            self.spoiler_leaderboard_message = await self.spoiler_thread.send(
                "Current Leaderboard:\n" + self._build_leaderboard_string(show_bins=False)
            )
            await self.spoiler_leaderboard_message.pin()

        # Leaderboard updates
        await self.leaderboard_message.edit(
            content=f"Number of participants: {len(self.leaderboard)}"
        )
        await self.owner.send(f"Time submitted for {self.name}: {str(entry)}")

    async def spectate(self, user):
        """
        Adds the user to the spoiler thread for this race
        """
        entry = AsyncLeaderboardEntry(user, "00:00:00", None, False, True)
        self.leaderboard.append(entry)
        await self.spoiler_thread.add_user(user)
        await self.spoiler_thread.send(f"{user.mention} is now spectating!")

    def is_owner(self, user):
        """
        Returns true if the current user is the owner of this race
        """
        return user.id == self.owner.id

    def export_leaderboard(self):
        """
        Returns the leaderboard as a comma separated string
        """
        leaderboard_str = "Runner,Time,VOD,Bin\n"
        leaderboard_str = leaderboard_str + self._build_leaderboard_string(comma_separated=True)
        return leaderboard_str

    def _build_leaderboard_string(self, comma_separated=False, show_bins=True):
        finished_racers = [entry for entry in self.leaderboard if not entry.is_forfeit and not entry.is_spectator]
        finished_racers.sort(key=lambda x: x.time_delta)
        leaderboard_str = ""
        if len(finished_racers) == 0 and not comma_separated:
            leaderboard_str = leaderboard_str + "No finishers!\n"
        else:            
            bin_end_time = -1
            bin_number = 1
            for i, entry in enumerate(finished_racers):
                # we want to bin the users here as well, based on finish time.
                if bin_end_time == -1:
                    # first bin
                    bin_end_time = entry.time_delta.total_seconds() + 60  # 1 minute bins
                elif entry.time_delta.total_seconds() > bin_end_time and bin_number < 6:
                    # runner is in the next bin of six possible bins
                    bin_number += 1
                    bin_end_time = entry.time_delta.total_seconds() + 60 # 1 minute bins

                if comma_separated:
                    leaderboard_str = leaderboard_str + f"{entry.runner_name},{entry.runner_time},{entry.vod if entry.vod else ''},{bin_number}\n"
                else:
                    if show_bins:
                        leaderboard_str = leaderboard_str + f"{i+1}. {str(entry)} (Bin {bin_number})\n"
                    else:
                        leaderboard_str = leaderboard_str + f"{i+1}. {str(entry)}\n"                            

        forfeits = [entry for entry in self.leaderboard if entry.is_forfeit and not entry.is_spectator]
        if len(forfeits) > 0:
            if not comma_separated:
                leaderboard_str = leaderboard_str + "\nForfeits:\n"
            for i, entry in enumerate(forfeits):
                if comma_separated:
                    leaderboard_str = leaderboard_str + f"{entry.runner_name},DNF,,\n"
                else:
                    leaderboard_str = leaderboard_str + f"{i+1}. {str(entry)}\n"

        return leaderboard_str


    def to_dict(self): 
        return {
            "race_channel_id": self.race_channel.id,
            "race_id": self.race_id,
            "race_thread_id": self.race_thread.id,
            "spoiler_thread_id": self.spoiler_thread.id,
            "name": self.name,
            "owner_id": self.owner.id,
            "flags": self.flags,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "race_role": self.race_role,
            "seed": self.seed,
            "is_started": self.is_started,
            "is_finished": self.is_finished,
            "announcement_message_id": self.announcement_message.id,
            "leaderboard_message_id": self.leaderboard_message.id if self.leaderboard_message else None,
            "spoiler_leaderboard_message_id": self.spoiler_leaderboard_message.id if self.spoiler_leaderboard_message else None,
            "leaderboard": self.leaderboard
        }    
    
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
        self.runner_id = runner.id
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
        entry_str = f"{self.runner_name} - {h}:{m:02d}:{s:02d}"
        if self.vod:
            entry_str = entry_str + f" - <{self.vod}>"

        return entry_str

    def __eq__(self, other):
        if (isinstance(other, AsyncLeaderboardEntry)):
            return self.runner_id == other.runner_id
        elif (isinstance(other, int)):
            return self.runner_id == other
        return False

    def _get_time_delta(self, runner_time: str):
        t = datetime.strptime(runner_time, "%H:%M:%S")
        return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
