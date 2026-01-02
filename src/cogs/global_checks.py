import constants

def is_admin(author):
    return (any(role.name in constants.ADMINS for role in author.roles)) or (
        author.id in [int(140605120579764226), constants.poor_soul_id]
    )

def is_call_for_races(ctx):
     return ctx.channel.name in constants.call_for_races_channels

def is_call_for_multiworld(ctx):
    return ctx.channel.name in constants.call_for_races_channels

def allow_seed_rolling(ctx):
    return (ctx.channel.name == constants.call_for_races_channel) or (
        ctx.channel.category_id == get(ctx.guild.categories, name="races").id
    )
