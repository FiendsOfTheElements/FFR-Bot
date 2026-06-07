import asyncio
import io
import re
from math import ceil
from random import random
import discord
from discord.ext import commands
from singing_tts import BUILTIN_MELODIES, song_to_bytes, synthesize_song

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

    @commands.command(name="singbuiltin")
    async def sing_builtin(self, ctx: commands.Context, name: str = "twinkle"):
        """
        Sing one of the built-in melodies.

        Usage:
        !singbuiltin twinkle          — post as MP3
        !singbuiltin happy_birthday   — post as MP3
        !singbuiltin ode_to_joy vc    — play in voice channel
        """
        if name not in BUILTIN_MELODIES:
            names = ", ".join(f"`{k}`" for k in BUILTIN_MELODIES)
            await ctx.reply(f"Unknown melody. Available: {names}")
            return

        await ctx.typing()
        melody = BUILTIN_MELODIES[name]
        label  = f"🎵 {name.replace('_', ' ').title()}"

        try:
            await self.build_and_send_attachment(ctx, melody, label)
        except Exception as e:
            await ctx.reply(f"❌ Error: `{e}`")

    async def build_and_send_attachment(self, ctx: commands.Context, melody, label: str):
        """Synthesize a melody and post it as an MP3 attachment."""
        audio = await asyncio.to_thread(synthesize_song, melody)
        mp3   = await asyncio.to_thread(song_to_bytes, audio, "mp3")
        file  = discord.File(io.BytesIO(mp3), filename="song.mp3")
        await ctx.reply(f"{label} 🤖🎤", file=file)
