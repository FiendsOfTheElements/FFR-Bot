import re
from math import ceil
from random import random
from discord.ext import commands

class MiscCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    async def whoami(self, ctx):
        await ctx.author.send(ctx.author.id)
        await ctx.message.delete()


    @commands.command()
    async def roll(self, ctx, dice):
        match = re.match(r"((\d{1,3})?d\d{1,9})", dice)
        if match is None:
            await ctx.message.channel.send(
                "Roll arguments must be in the form [N]dM ie. 3d6, d8"
            )
            return
        rollargs = match.group().split("d")

        try:
            rollargs[0] = int(rollargs[0])
        except BaseException:
            rollargs[0] = 1
        rollargs[1] = int(rollargs[1])
        result = [ceil(random() * rollargs[1]) for i in range(rollargs[0])]
        textresult = f"{format(match.group())} result: **{sum(result)}**"
        await ctx.message.channel.send(textresult)


    @commands.command()
    async def coin(self, ctx):
        coinres = ""
        if random() >= 0.5:
            coinres = "Heads"
        else:
            coinres = "Tails"
        await ctx.message.channel.send(f"Coin landed on: **{format(coinres)}**")
