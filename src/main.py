import asyncio
import logging
import traceback

import os
import redis

from discord.ext import commands
from discord.utils import get

import discord

from cogs.misc import MiscCommandCog
from cogs.races.races import Races
from cogs.races.async_races import AsyncRaces
from cogs.races.races_common import RacesCommon
from cogs.roles import Roles
from voting.polls import Polls
from cogs.report import Report

import constants


# format logging
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

description = "FFR discord bot"

bot = commands.Bot(
    command_prefix="?", description=description, case_insensitive=True, intents=intents
)

redis_pool = redis.ConnectionPool(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    decode_responses=False,
)

redis_races = redis.StrictRedis(connection_pool=redis_pool)
redis_polls = redis.StrictRedis(connection_pool=redis_pool)


@bot.event
async def on_ready():
    await bot.tree.sync()
    for guild in bot.guilds:
        cmds = bot.tree.get_commands(guild=guild)
        if cmds:
            await bot.tree.sync(guild=guild)

    logging.info("discord.py version: %s", discord.__version__)
    logging.info("Logged in as")
    logging.info(bot.user.name)
    logging.info(bot.user.id)
    logging.info("------")


@bot.event
async def on_command_error(ctx, error):
    poor_soul = bot.get_user(constants.poor_soul_id)
    if isinstance(error, discord.ext.commands.errors.CommandNotFound):
        raise error
    error_msg = "".join(traceback.TracebackException.from_exception(error).format())[:1950]
    await poor_soul.send("Error in FFRBot!!")
    await poor_soul.send(error_msg)
    raise error

# used to clear channels for testing purposes

# @bot.command(pass_context = True)
# async def purge(ctx):
#     channel = ctx.message.channel
#     await bot.purge_from(channel, limit=100000)

def handle_exit(client, loop):
    # taken from https://stackoverflow.com/a/50981577
    loop.run_until_complete(client.logout())
    for t in asyncio.Task.all_tasks(loop=loop):
        if t.done():
            t.exception()
            continue
        t.cancel()
        try:
            loop.run_until_complete(asyncio.wait_for(t, 5, loop=loop))
            t.exception()
        except asyncio.InvalidStateError:
            pass
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            pass

async def periodic(interval_sec, coro_name, *args, **kwargs): 
    while True:
        # wait for the given interval
        await asyncio.sleep(interval_sec)
        # await the target
        await coro_name(*args, *kwargs)

async def main(client, token):
    await bot.add_cog(MiscCommandCog(bot))
    races = Races(bot, redis_races)    
    async_races = AsyncRaces(bot, redis_races)
    # schedule the async update to run periodically
    asyncio.create_task(periodic(30, async_races.periodic_race_update))

    await bot.add_cog(RacesCommon(bot, races, async_races))
    await bot.add_cog(races)
    await bot.add_cog(async_races)
    await bot.add_cog(Roles(bot))
    await bot.add_cog(Polls(bot, redis_polls))
    await bot.add_cog(Report(bot))

    async with client:
        await client.start(token)


with open("token.txt", "r") as f:
    token = f.read()
token = token.strip()

asyncio.run(main(bot, token))
