import random

import discord
from discord import app_commands
from discord.ext import commands
from discord.interactions import Interaction

import constants

class OpenReportThread(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.red, row=2)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OpenReportModal())

class OpenReportModal(discord.ui.Modal, title="Open Report"):
    description = discord.ui.TextInput(
        label="Summary",
        placeholder="Please provide a brief summary of your report to help the moderation team understand the issue.",
        min_length=10,
        max_length=200,
        required=True,
        row=1,
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: Interaction) -> None:
        duration = 24 * 60

        msg = None
        thread: discord.Thread = await interaction.channel.create_thread(
            name=f"Report {interaction.user.name} {random.randint(0, 999)}", message=msg,
            auto_archive_duration=duration)

        pinged_members = discord.utils.get(interaction.guild.roles, name=constants.mod_role).members + discord.utils.get(interaction.guild.roles, name=constants.admin_role).members
        await thread.add_user(interaction.user)
        await interaction.response.send_message(
            f"A new thread called {thread.mention} has been opened for this report.", ephemeral=True)

        if interaction.guild.chunked is False:
            await interaction.guild.chunk(cache=True)

        for member in pinged_members:
            await thread.add_user(member)

        await thread.send(
            f"{interaction.user.mention} has opened an report.\n\n**Description:** {self.description.value}",
            allowed_mentions=discord.AllowedMentions.none()
        )

class Report(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.persistent_views_added = False

    @app_commands.command(description="Adds a message that allows users to create a private thread to open an report.")
    async def report(
            self,
            interaction: discord.Interaction,
    ):
        """
        Adds a message that allows users to create a private thread to open an report.
        """
        mod_role = discord.utils.get(interaction.guild.roles, name=constants.mod_role)
        admin_role = discord.utils.get(interaction.guild.roles, name=constants.admin_role)
        if not mod_role or not admin_role:
            await interaction.response.send_message(
                "The server must have a mod and admin role for this feature to work.", ephemeral=True)
            return
        
        await interaction.response.send_message(
            content=(
                f"This will open a private thread to {mod_role.mention} and {admin_role.mention}, are you sure you want to do that?\n\n"
                "This message will stop working after one minute.\n"
                "If you did not intend to do this, simply click \"Dismiss message\" at the bottom of this response. Thanks!"
            ),
            ephemeral=True,
            view=OpenReportThread(),
            allowed_mentions=discord.AllowedMentions(roles=False)
        )
