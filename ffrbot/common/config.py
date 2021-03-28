from .redis_client import *
from discord.ext.commands import Bot
import discord
from typing import *
from pymongo import MongoClient
from .mongo_classes import *
import logging

__db: MongoClient
__bot: Bot
__cache: Dict[Union[str, int], Any] = dict()


def init(db: MongoClient, bot: Bot) -> None:
    global __db
    global __bot
    __db = db
    __bot = bot


def init_guild(guild: discord.Guild) -> None:
    configs = __db.guilds.configs
    config = {
        "id": guild.id,
    }
    logging.info(config)
    id = configs.insert_one(config)
    logging.info(id)


def get_guild_config(guild_id: int) -> GuildConfig:
    config = __db.guilds.configs.find_one({"id": guild_id})
    logging.info(config)
    return config


def get_admin_role_ids(guild_id: int) -> List[int]:
    try:
        ids = get_guild_config(guild_id)["admin_role_ids"]
    except KeyError:
        ids = []
    return ids


def add_admin_role_ids(guild_id: int, new_admins: List[int]) -> None:
    __db.guilds.configs.update_one(
        {"id": guild_id},
        {"$addToSet": {"admin_role_ids": {"$each": new_admins}}},
    )


def remove_admin_role_ids(guild_id: int, stale_admins: List[int]) -> None:
    __db.guilds.configs.update_one(
        {"id": guild_id},
        {"$pullAll": {"admin_role_ids": stale_admins}},
    )


def get_polls_category_id() -> int:
    return int(
        __db.get_str(Namespace.ADMIN_CONFIG, AdminKeys.POLLS_CATEGORY) or "-1"
    )


def set_polls_category_id(value: int) -> None:
    __db.set_str(Namespace.ADMIN_CONFIG, AdminKeys.POLLS_CATEGORY, str(value))


def get_role_requests_channel_id() -> int:
    r_val = int(
        __db.get_str(Namespace.ADMIN_CONFIG, AdminKeys.ROLE_REQUESTS_CHANNEL)
        or "-1"
    )
    return r_val


def set_role_requests_channel_id(value: int) -> None:
    __db.set_str(
        Namespace.ADMIN_CONFIG, AdminKeys.ROLE_REQUESTS_CHANNEL, str(value)
    )


def get_race_org_channel_id() -> int:
    return int(
        __db.get_str(Namespace.RACE_CONFIG, RaceKeys.ORG_CHANNEL_ID) or "-1"
    )


def set_race_org_channel_id(value: int) -> None:
    __db.set_str(Namespace.RACE_CONFIG, RaceKeys.ORG_CHANNEL_ID, str(value))


def get_race_results_channel_id() -> int:
    return int(
        __db.get_str(Namespace.RACE_CONFIG, RaceKeys.RESULTS_CHANNEL_ID) or ""
    )


def set_race_results_channel_id(value: int) -> None:
    __db.set_str(
        Namespace.RACE_CONFIG, RaceKeys.RESULTS_CHANNEL_ID, str(value)
    )


def set_guild_id(value: int) -> None:
    __db.set_str(Namespace.ADMIN_CONFIG, AdminKeys.GUILD_ID, str(value))


def get_guild_id() -> int:
    return int(
        __db.get_str(Namespace.ADMIN_CONFIG, AdminKeys.GUILD_ID) or "-1"
    )


def get_guild() -> discord.Guild:
    guild_id = get_guild_id()
    if guild_id in __cache.keys():
        return cast(discord.Guild, __cache[guild_id])
    else:
        # we cast here since we assert that the bot is in a guild
        guild = cast(discord.Guild, __bot.get_guild(int(get_guild_id())))
        assert guild is not None
        __cache[guild_id] = guild
        return guild
