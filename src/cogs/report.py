import logging
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
        channel = self._get_moderation_channel(interaction)
        if not channel:
            channel = interaction.channel
        thread: discord.Thread = await channel.create_thread(
            name=f"Report by {interaction.user.name} - {random.randint(0, 999)}",
            message=msg,
            auto_archive_duration=duration,
        )

        pinged_members = self._get_moderator_members(interaction)
        if not pinged_members:
            await interaction.response.send_message(
                "No moderators found to ping. Please ensure there are members with the moderator role in the server.",
                ephemeral=True,
            )
            raise ValueError("No moderators found to ping for report.")

        await thread.add_user(interaction.user)
        await interaction.response.send_message(
            f"A new thread called {thread.mention} has been opened for this report.",
            ephemeral=True,
        )

        if interaction.guild.chunked is False:
            await interaction.guild.chunk(cache=True)

        for member in pinged_members:
            await thread.add_user(member)

        await thread.send(
            f"{interaction.user.mention} has opened an report.\n\n**Description:** {self.description.value}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def _get_moderator_members(self, interaction: Interaction):
        mod_members = discord.utils.get(
            interaction.guild.roles, name=constants.mod_role
        ).members
        arbiter = discord.utils.get(
            interaction.guild.roles, name=constants.arbitor_role
        )
        if not arbiter:
            return mod_members

        return [member for member in mod_members if arbiter not in member.roles and member.name not in constants.do_not_ping]

    def _get_moderation_channel(self, interaction: Interaction):
        """
        Returns the channel where reports should be sent.
        If no specific channel is set, it returns the current channel.
        """
        mod_channel = discord.utils.get(
            interaction.guild.channels, name=constants.moderation_channel
        )
        if mod_channel:
            return mod_channel
        return None

class Report(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.persistent_views_added = False

    @app_commands.command(
        description="Adds a message that allows users to create a private thread to open an report."
    )
    async def report(
        self,
        interaction: discord.Interaction,
    ):
        """
        Adds a message that allows users to create a private thread to open an report.
        """
        mod_role = discord.utils.get(interaction.guild.roles, name=constants.mod_role)
        if not mod_role:
            await interaction.response.send_message(
                "The server must have a mod role for this feature to work.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            content=(
                f"Thank you for reporting. This interaction will open a private thread with the {mod_role.mention} and admin team where you can elaborate on the issue.\n\n"
                'Click "Yes" to start the report. If you did not intend to do this, simply click "Dismiss message" at the bottom of this response. Thanks!'
            ),
            ephemeral=True,
            view=OpenReportThread(),
            allowed_mentions=discord.AllowedMentions(roles=False),
        )
