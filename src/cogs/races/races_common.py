import random
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from discord.ext import commands

from cogs.races.races import is_race_room
import constants

def flagseedgen(url):
    parsed = urlparse(url)
    query_string = parse_qs(parsed.query)
    seed = random.randint(0, 4294967295)
    hex_seed = "{0:-0{1}x}".format(seed, 8)
    query_string['s'] = hex_seed
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query_string, doseq=True), parsed.fragment))


class RacesCommon(commands.Cog):
    """
    Class to manage races, and coordinate common commands    
    """

    def __init__(self, bot, races, async_races):
        self.bot = bot
        # Races manager will also create and hold onto the two other races
        self.races = races
        self.async_races = async_races


    @commands.command(aliases=["s", "spec"])
    async def spectate(self, ctx):
        if is_race_room(ctx):
            await self.races.spectate(ctx, -1)
            return
        await self.async_races.spectate(ctx)

    @commands.command(aliases=["ff", "dnf"])
    async def forfeit(self, ctx):
        if is_race_room(ctx):
            await self.races.forfeit(ctx)
            return
        await self.async_races.forfeit(ctx)

    @commands.command(
        aliases=["ff1url", "ff1roll", "ffrroll", "rollseedurl", "roll_ffr_url_seed"]
    )
    async def ffrurl(self, ctx, url):
        if not ctx.channel.name in constants.call_for_races_channels and not is_race_room(ctx):
            return

        user = ctx.author
        if url is None:
            await user.send("You need to supply the url to roll a seed for.")
            return
        
        msg = await ctx.channel.send(
            flagseedgen(url)
        )
        if (is_race_room(ctx)):
            await msg.pin()

    @commands.command()
    async def ff1seed(self, ctx):
        if not ctx.channel.name in constants.call_for_races_channels and not is_race_room(ctx):
            return

        await ctx.channel.send("{0:-0{1}x}".format(random.randint(0, 4294967295), 8))
