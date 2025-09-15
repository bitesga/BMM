import discord
from discord.ext import commands
import mongodb

from views.MatchmakingView import delete_mm_embed, get_mm_channel_for_region


async def delete_mm(bot, interaction: discord.Interaction, region, selected_role: str):
    deleted_count = mongodb.deleteGuildMM(interaction.guild.id, region, selected_role.lower())
    role_text = f" {selected_role}" if selected_role != "Overall" else ""
    if not deleted_count:
        return await interaction.edit_original_response(
            content=f"⛔ No matchmaking found to delete for `{region}{role_text}`.", view=None
        )

    _, matchmakingChannels, _, _, _ = await bot.getChannels(interaction.guild)
    matchmakingChannel = get_mm_channel_for_region(matchmakingChannels, region)
    if matchmakingChannel:
        await delete_mm_embed(matchmakingChannel, selected_role.title())

    return await interaction.edit_original_response(
        content=f"✅ Matchmaking cleared for `{region}{role_text}`.", view=None
    )
        
class SelectRoleToDeleteMM(discord.ui.Select):
    def __init__(self, bot: commands.Bot, roles, region, originalInteraction):
        options = [
            discord.SelectOption(label=role["name"], value=role["id"])
            for role in roles
        ]

        super().__init__(
            placeholder="Select a role to delete matchmaking for",
            options=options
        )
        self.bot = bot
        self.roles = roles
        self.region = region
        self.originalInteraction = originalInteraction


    async def callback(self, interaction: discord.Interaction):
        selectedRoleId = self.values[0]
        selectedRole = next((role for role in self.roles if str(role["id"]) == str(selectedRoleId)), None)
        await delete_mm(self.bot, self.originalInteraction, self.region, selectedRole["name"])
