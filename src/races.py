import asyncio
import random

from urllib.parse import parse_qs, urlparse
import urllib.request
import json
from io import StringIO

from discord import DiscordException
from discord.ext import commands
from discord.utils import get

from ffrrace import Race, RaceNotLockable
import logging

import constants

active_races = dict()
aliases = dict()
teamslist = dict()
allow_races_bool = True


def allow_seed_rolling(ctx):
    return (ctx.channel.name in constants.call_for_races_channels) or (
        ctx.channel.id in active_races.keys())


def is_call_for_races(ctx):
    return ctx.channel.name in constants.call_for_races_channels


def is_call_for_multiworld(ctx):
    return ctx.channel.name in constants.call_for_races_channels


def is_race_room(ctx):
    return ctx.channel.id in active_races.keys()


def is_race_started(toggle=True):
    async def predicate(ctx):
        try:
            race = active_races[ctx.channel.id]
        except KeyError:
            return False
        return race.started if toggle else not race.started

    return commands.check(predicate)


def is_runner(toggle=True):
    """
    True is the user is a runner false if a spectator
    :param ctx: context for the command
    :return: bool
    """

    async def predicate(ctx):
        rval = ctx.author.id in aliases[ctx.channel.id].keys()
        return rval if toggle else not rval

    return commands.check(predicate)


def is_team_leader(ctx):
    return ctx.author.id in teamslist[ctx.channel.id].keys()


def is_race_owner(ctx):
    race = active_races[ctx.channel.id]
    return ctx.author.id == race.owner


def allow_races(ctx):
    return allow_races_bool


def is_admin(ctx):
    user = ctx.author
    return (any(role.name in constants.ADMINS for role in user.roles)) or (
        user.id == int(140605120579764226))


class Races(commands.Cog):

    def __init__(self, bot, redis_db):
        self.bot = bot
        self.twitchids = dict()
        self.redis_db = redis_db
        self.loaddata()

    def loaddata(self):
        temp_twitchids = dict(self.redis_db.hgetall('twitchids'))
        for k, v in temp_twitchids.items():
            self.twitchids[k.decode('utf-8')] = v.decode('utf-8')
        logging.info('Loading saved Twitch ids')
        logging.debug('twitch ids:' + str(self.twitchids))

    @commands.command(aliases=['sr'])
    @commands.check(is_call_for_races)
    @commands.check(allow_races)
    async def startrace(self, ctx, *, name=None):
        if name is None:
            await ctx.author.send("you forgot to name your race")
            return
        message_str = "A new race has been started!\nJoin this race with the" \
            + " ?join command, @ any people that will be on your team if playing coop."

        racethread = await ctx.channel.create_thread(
            name=name,
            message=ctx.message,
            reason="bot generated thread for a race"
        )
        race = Race(racethread.id, name)
        active_races[racethread.id] = race
        race.channel = racethread
        race.message = await racethread.send(message_str)
        aliases[racethread.id] = dict()  # for team races
        teamslist[racethread.id] = dict()
        race.owner = ctx.author.id
        # just trying to hack around the permission bug we've been dealing
        # with throughout 2023. cause unknown but maybe this helps?
        await race.message.pin()
        await asyncio.sleep(5)

    @commands.command(aliases=['ap', 'multiworld', 'archipelago'])
    @commands.check(is_call_for_multiworld)
    @commands.check(allow_races)
    async def startmultiworld(self, ctx, *, name=None):
        if name is None:
            await ctx.author.send("you forgot to name your multiworld")
            return

        racethread = await ctx.channel.create_thread(
            name=name,
            message=ctx.message,
            reason="bot generated thread for a multiworld,"
        )

        race = Race(racethread.id, name, lockable=True)
        active_races[racethread.id] = race
        race.channel = racethread

        race.message = await racethread.send(
            "join this multiworld with the ?join command, @ any"
            + " people that will be on your team if playing coop. "
        )
        aliases[racethread.id] = dict()  # for team races
        teamslist[racethread.id] = dict()
        race.owner = ctx.author.id

    @commands.command(aliases=['cr'])
    @is_race_started(toggle=False)
    @commands.check(is_race_owner)
    @commands.check(is_race_room)
    async def closerace(self, ctx):
        await ctx.channel.send('deleting this race in 5 minutes')
        await self.removeraceroom(ctx, 300)

    @commands.command()
    @is_race_started(toggle=False)
    @commands.check(is_race_owner)
    @commands.check(is_race_room)
    async def lockrace(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            race.lockRace()
            edited_message = (
                "Race: " + race.name + " is now locked! "
            )
            await race.message.edit(content=edited_message)
            await ctx.channel.send('Race is now locked. New players cannot be added.')
        except RaceNotLockable:
            await ctx.channel.send('This race cannot be locked')

    @commands.command()
    @is_race_started(toggle=False)
    @commands.check(is_race_owner)
    @commands.check(is_race_room)
    async def unlockrace(self, ctx):
        race = active_races[ctx.channel.id]
        if (race.islocked):
            race.unlockRace()
            edited_message = (
                "join this multiworld/race with the ?join command, @ any"
                + " people that will be on your team if playing coop. "
            )
            await race.message.edit(content=edited_message)
            await ctx.channel.send('This race is now unlocked. New players can join again.')
        else:
            await ctx.channel.send('Race is already unlocked.')

    @commands.command(aliases=["enter"])
    async def join(self, ctx, id=None, name=None):
        try:
            await ctx.message.delete()
        except DiscordException:
            # Fails on newer discord tokens
            pass

        if ctx.channel.id not in active_races.keys():
            await ctx.author.send(
                "Join command must be used in an active race channel or thread"
            )
            return

        if id is None:
            id = ctx.channel.id
        id = int(id)
        try:
            if active_races[id].started is True:
                await ctx.channel.send("This race has already started")
                return
            if active_races[id].islocked is True:
                await ctx.channel.send("This race is locked. No new racers can join.")
                return
        except KeyError:
            await ctx.author.send("That id doesnt exist")
            return

        if name is None:
            name = ctx.author.display_name

        race = active_races[id]
        race.addRunner(ctx.author.id, name)
        aliases[id][ctx.author.id] = ctx.author.id
        teamslist[id][ctx.author.id] = dict(
            [("name", name), ("members", [[ctx.author.display_name,
                                           ctx.author.id]])])
        tagpeople = "Welcome! " + ctx.author.mention
        for r in ctx.message.mentions:
            aliases[id][r.id] = ctx.author.id
            teamslist[id][ctx.author.id]["members"].append([r.display_name, r.id])
            tagpeople += r.mention + " "
        await race.channel.send(tagpeople)

    @commands.command(aliases=['quit'])
    @is_race_started(toggle=False)
    @is_runner()
    @commands.check(is_race_room)
    async def unjoin(self, ctx):
        try:
            race = active_races[ctx.channel.id]
        except KeyError:
            await ctx.author.send("KeyError in unjoin command")
            return

        if race.runners[ctx.author.id]["ready"] is True:
            race.readycount -= 1
        race.removeRunner(ctx.author.id)
        await ctx.channel.send(ctx.author.display_name
                               + " has left the race and is now cheering "
                               + "from the sidelines.")
        del aliases[ctx.channel.id][ctx.author.id]

        try:
            del teamslist[ctx.channel.id][ctx.author.id]
        except KeyError:
            pass
        try:
            for team in teamslist[ctx.channel.id].values():
                if ([ctx.author.display_name, ctx.author.id] in
                        team["members"]):
                    team["members"].remove(
                        [ctx.author.display_name, ctx.author.id])
                    break
        except KeyError:
            pass
        await self.startcountdown(ctx)

    @commands.command(aliases=['s'])
    @commands.check(is_call_for_races)
    async def spectate(self, ctx, id):
        try:
            race = active_races[int(id)]
        except KeyError:
            return
        await ctx.message.delete()
        if id:
            await race.channel.send("%s is now cheering you on from the"
                                    + " sidelines" % ctx.author.mention)

    @commands.command(aliases=['r'])
    @is_race_started(toggle=False)
    @is_runner()
    @commands.check(is_race_room)
    async def ready(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            race.ready(ctx.author.id)
            await ctx.channel.send(
                ctx.author.display_name
                + " is READY! "
                + str(len(race.runners) - race.readycount)
                + " remaining.")
        except KeyError:
            ctx.channel.send("Key Error in 'ready' command")
            return
        await self.startcountdown(ctx)

    @commands.command(aliases=['ur'])
    @is_race_started(toggle=False)
    @is_runner()
    @commands.check(is_race_room)
    async def unready(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            race.unready(ctx.author.id)
            await ctx.channel.send(
                ctx.author.display_name + " is no longer READY. " + str(
                    len(race.runners) - race.readycount) + " remaining.")
        except KeyError:
            ctx.channel.send("Key Error in 'ready' command")
            return

    @commands.command(aliases=['e'])
    @commands.check(is_race_room)
    async def entrants(self, ctx):
        try:
            race = active_races[ctx.channel.id]
        except KeyError:
            await ctx.channel.send("Key Error in 'entrants' command")
            return
        msg = race.getUpdate()
        await ctx.channel.send(msg)

    @commands.command()
    @is_race_started()
    @is_runner()
    @commands.check(is_race_room)
    async def done(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            msg = race.done(aliases[race.id][ctx.author.id])
            await ctx.channel.send(msg)
            if (race.isFinsihed()):
                await self.endrace(ctx, msg)
        except KeyError:
            await ctx.channel.send("Key Error in 'done' command")

    @commands.command(aliases=['unforfeit'])
    @is_race_started()
    @is_runner()
    @commands.check(is_race_room)
    async def undone(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            msg = race.undone(aliases[race.id][ctx.author.id])
            await ctx.channel.send(msg)
        except KeyError:
            await ctx.channel.send("Key Error in 'undone' command")

    @commands.command()
    @is_race_started()
    @is_runner()
    @commands.check(is_race_room)
    async def forfeit(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            msg = race.forfeit(aliases[race.id][ctx.author.id])
            await ctx.channel.send(msg)
            if (all(r["etime"] is not None for r in race.runners.values())):
                await self.endrace(ctx, msg)
        except KeyError:
            await ctx.channel.send("Key Error in the 'forfeit' command")

    @commands.command(aliases=['t'])
    @commands.check(is_race_room)
    @is_race_started(toggle=True)
    async def time(self, ctx):
        try:
            time = active_races[ctx.channel.id].getTime()
            await ctx.channel.send(time)
        except KeyError:
            await ctx.channel.send("Key Error in the 'time' command")

    @commands.command(aliases=['tl'])
    @is_race_started(toggle=False)
    @commands.check(is_race_room)
    async def teamlist(self, ctx):
        try:
            rstring = "Teams:\n"
            race = active_races[ctx.channel.id]
            for team in teamslist[race.id].values():
                rstring += team["name"] + ":"
                for member in team["members"]:
                    rstring += " " + member[0] + ","
                rstring = rstring[:-1]
                rstring += "\n"
            await ctx.channel.send(rstring)
        except KeyError:
            await ctx.channel.send("Key Error in 'teams' command")

    @commands.command(aliases=['ta'])
    @is_race_started(toggle=False)
    @commands.check(is_team_leader)
    @commands.check(is_race_room)
    async def teamadd(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            for player in ctx.message.mentions:
                aliases[race.id][player.id] = ctx.author.id
                teamslist[race.id][ctx.author.id]["members"].append(
                    [player.display_name, player.id])
        except KeyError:
            await ctx.channel.send("Key Error in 'teamadd' command")

    @commands.command(aliases=['tr'])
    @is_race_started(toggle=False)
    @commands.check(is_team_leader)
    @commands.check(is_race_room)
    async def teamremove(self, ctx):
        try:
            race = active_races[ctx.channel.id]
            for player in ctx.message.mentions:
                del aliases[race.id][player.id]
                teamslist[race.id][ctx.author.id]["members"].remove(
                    [player.display_name, player.id])
        except KeyError:
            await ctx.channel.send("Key Error in 'teamremove' command")

    @commands.check(is_call_for_races)
    async def races(self, ctx):
        rval = "Current races:\n"
        for race in active_races.values():
            rval += "name: " + race.name + " - id: " + str(race.id) + "\n"
        await ctx.channel.send(rval)

    async def endrace(self, ctx, msg):
        rresults = get(ctx.message.guild.channels, name=constants.race_results)
        await rresults.send(msg + "\n===================================")
        await self.removerace(ctx)

    async def startcountdown(self, ctx):
        race = active_races[ctx.channel.id]
        multi = await self.multistream(race, all=True, discord=True, ctx=ctx)
        if (race.readycount != len(race.runners)):
            return
        edited_message = (
            "Race: " + race.name + " has started! "
            + "\nWatch the race at: "
            + (race.restream if race.restream is not None else multi)
        )
        await race.message.edit(content=edited_message)
        for i in range(10):
            await ctx.channel.send(str(10 - i))
            await asyncio.sleep(1)
        await ctx.channel.send("go!")
        race.start()

    @commands.command()
    @commands.check(is_race_room)
    async def restream(self, ctx, streamid=None):
        try:
            race = active_races[ctx.channel.id]
        except KeyError:
            ctx.channel.send(
                "this isnt a race channel, cant set restream here")
            return
        race.restream = streamid
        await ctx.channel.send("restream set to: " + race.restream)
        edited_message = (
            "join this race with the ?join command,"
            + " @ any people that will be on your team if "
            + "playing coop. "
            + "\nWatch the race at: "
            + race.restream
        )

        await race.message.edit(content=edited_message)

    async def removerace(self, ctx, time=0):
        await asyncio.sleep(time)
        race = active_races[ctx.channel.id]
        channel = race.channel
        del active_races[ctx.channel.id]
        del aliases[channel.id]
        del teamslist[channel.id]

    @commands.command(
        aliases=["ff1url", "ff1roll", "ffrroll", "rollseedurl", "roll_ffr_url_seed"]
    )
    @commands.check(allow_seed_rolling)
    async def ffrurl(self, ctx, url):
        user = ctx.author
        if url is None:
            await user.send("You need to supply the url to roll a seed for.")
            return

        parsed = urlparse(url)
        flags = parse_qs(parsed.query)["f"][0]

        msg = await ctx.channel.send(
            self.flagseedgen(
                flags,
                parsed.hostname,
            )
        )
        await msg.pin()

    def flagseedgen(self, flags, site):
        seed = random.randint(0, 4294967295)
        url = "<https://" + site

        url += (
            "/Randomize?s="
            + ("{0:-0{1}x}".format(seed, 8))
            + "&f="
            + flags
        )

        url += ">"
        return url

    @commands.command()
    @commands.check(allow_seed_rolling)
    async def ff1seed(self, ctx):
        await ctx.channel.send("{0:-0{1}x}"
                               .format(random.randint(0, 4294967295), 8))

    @commands.command()
    async def multireadied(self, ctx, raceid: str = None):
        user = ctx.message.author

        if raceid is None:
            await user.send("You need to supply the "
                            + "race id to get the multistream link.")
            return
        link = await self.multistream(raceid)
        if link is None:
            await ctx.channel.send('There is no race with that 5 character '
                                   + 'id, try remove "srl-" from the room id.')
        else:
            await ctx.channel.send(link)

    @commands.command()
    async def multi(self, ctx, raceid: str = None):
        user = ctx.message.author
        try:
            if raceid is None:
                race = active_races[ctx.channel.id]
            else:
                race = active_races[int(raceid)]
            link = await self.multistream(race, all=True, discord=True,
                                          ctx=ctx)
            await ctx.channel.send(link)

        except (KeyError, ValueError):
            if raceid is None:
                await user.send("You need to supply the race " +
                                "id to get the multistream link.")
                return
            link = await self.multistream(raceid, all=True, discord=False)
            if link is None:
                await ctx.channel.send("There is no race with"
                                       + " that 5 character id")
            else:
                await ctx.channel.send(link)

    async def multistream(self, race, all: bool = False,
                          discord: bool = False, ctx=None):
        srl_tmp = r"http://api.speedrunslive.com/races/{}"
        ms_tmp = r"http://multistre.am/{}/"
        if discord:
            runners = []
            no_twitch_id = []
            for team in teamslist[race.id].values():
                for runner in team["members"]:
                    try:
                        if (self.twitchids[str(runner[1])] != ''):
                            runners.append(self.twitchids[str(runner[1])])
                    except KeyError:
                        no_twitch_id.append(runner[0])
            ms_tmp = ms_tmp.format(r'/'.join(runners))
            if len(no_twitch_id) != 0:
                ms_tmp += "\nRunners without a set"\
                          + " twitch Id: \n" + ", ".join(no_twitch_id)
            return ms_tmp
        race = race.strip()[-5:]
        srlurl = srl_tmp.format(race)
        data = ""
        with urllib.request.urlopen(srlurl) as response:
            data = response.read()

        data = data.decode()
        srlio = StringIO(data)
        srl_json = json.load(srlio)
        try:
            entrants = [
                srl_json['entrants'][k]['twitch']
                for k in srl_json['entrants'].keys() if (
                    srl_json[
                        'entrants'][
                        k][
                        'statetext'] == "Ready") or all]
        except KeyError:
            return None
        entrants_2 = r'/'.join(entrants)
        ret = ms_tmp.format(entrants_2)
        return ret

    @commands.command()
    async def twitchid(self, ctx, id=''):
        self.twitchids[str(ctx.author.id)] = id
        self.redis_db.hset('twitchids', str(
            ctx.author.id).encode('utf-8'), id.encode('utf-8'))
        await ctx.channel.send('twitch id set to: '
                               + self.twitchids[str(ctx.author.id)])

    @commands.command()
    async def stream(self, ctx):
        for player in ctx.message.mentions:
            try:
                await ctx.channel.send(r'https://www.twitch.tv/{}'
                                       .format(self.twitchids[str(player.id)]))
            except KeyError:
                await ctx.channel.send(player.mention + " has not set their"
                                       + " twitchid\nset it with the following"
                                       + " command:\n`?twitchid "
                                       + "your_twitch_username`")

    # Admin Commands

    @commands.command()
    @commands.check(is_admin)
    @is_race_started(toggle=False)
    @commands.check(is_race_room)
    async def forcestart(self, ctx):
        await self.startcountdown(ctx)

    @commands.command()
    @commands.check(is_admin)
    @commands.check(is_race_room)
    async def forceclose(self, ctx):
        await self.removeraceroom(ctx)

    @commands.command()
    @commands.check(is_admin)
    @is_race_started()
    @commands.check(is_race_room)
    async def forceend(self, ctx):
        race = active_races[ctx.channel.id]
        for runner in race.runners.keys():
            if race.runners[runner]["etime"] is None:
                race.forfeit(runner)
        results = race.finishRace()
        await self.endrace(ctx, results)

    @commands.command()
    @commands.check(is_admin)
    @commands.check(is_race_room)
    async def forceremove(self, ctx):
        try:
            race = active_races[ctx.channel.id]
        except KeyError:
            return
        players = ctx.message.mentions
        for player in players:
            await player.remove_roles(race.role)
            race.removeRunner(player.id)
            del aliases[ctx.channel.id][player.id]

            try:
                del teamslist[ctx.channel.id][player.id]
            except KeyError:
                pass
            try:
                for team in teamslist[ctx.channel.id].values():
                    if any(player.id in x for x in team["members"]):
                        team["members"].remove(
                            [player.display_name, player.id])
                        break
            except KeyError:
                pass

    @commands.command()
    @commands.check(is_admin)
    async def toggleraces(self, ctx):
        global allow_races_bool
        allow_races_bool = not allow_races_bool
        await ctx.channel.send("races "
                               + ("enabled" if allow_races_bool
                                  else "disabled"))
