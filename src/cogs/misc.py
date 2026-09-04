import re
from math import ceil
from random import random, choice
from discord.ext import commands
import constants

class MiscCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    async def whoami(self, ctx):
        await ctx.author.send(ctx.author.id)
        await ctx.message.delete()

    @commands.command()
    async def sync(self, ctx, context=None):
        if (ctx.author.id != constants.poor_soul_id):
            await ctx.author.send("You don't have permission to use this command.")
            return
        
        await self.bot.tree.sync(guild=ctx.guild)    
        await ctx.author.send("Synced commands for this guild")
        if context == "*":
            await self.bot.tree.sync()
            await ctx.author.send("Synced commands globally")

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
        msg = await ctx.message.channel.send(textresult)
        if sum(result) == 8:
            await msg.add_reaction("<:jshydell:1373079716004630609>")


    @commands.command()
    async def coin(self, ctx):
        coinres = ""
        if random() >= 0.5:
            coinres = "Heads"
        else:
            coinres = "Tails"
        await ctx.message.channel.send(f"Coin landed on: **{format(coinres)}**")

    @commands.command(aliases=["8ball"])
    async def eightball(self, ctx, *, question=None):
        if not question or not question.endswith("?"):
            await ctx.message.channel.send("Magic 8-ball says: **Please ask a yes/no question ending with a '?'**")
            return
        
        eightball_responses = [
            "It is certain.",
            "It is decidedly so.",
            "Without a doubt.",
            "Yes - definitely.",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don't count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful.",
            "Absolutely, positively, unequivocally, definitely maybe.",
            "Don't ask questions you don't want to know the answer to.",
            "Yes, but only if you're lucky.",
            "Signs point to yes, but you need a nap first.",
            "No... but don't take it personally.",
            "Maybe, but only if you're wearing a hat.",
            "I'm not sure, but I think you should ask again later.",
            "Absolutely... as long as you don't cheat.",
            "The universe says not today.",
            "Lu... pa... ?",
        ]
        await ctx.message.channel.send(
            f"Magic 8-ball says: **{choice(eightball_responses)}**"
        )