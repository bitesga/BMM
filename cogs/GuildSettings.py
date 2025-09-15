from discord.ext import commands
import discord
from discord import app_commands
from discord.app_commands import guild_only
import mongodb
from typing import Literal

from cogs.BotAdmin import resetGuildElo

class GuildSettings(commands.Cog):
  
  def __init__(self, bot):
    self.bot = bot
         
           
  async def __handle_error(self, function, interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.NoPrivateMessage):
        await interaction.response.send_message("❌ This command cannot be run in private messages.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    else:
        self.bot.logger.error(f"Unhandled error in \"{function}\" command: {error}")
        await interaction.response.send_message(f"❌ An unknown error occurred: {error}", ephemeral=True)
        
         

  @app_commands.command(description="lists all guild settings.")
  async def list_settings(self, interaction: discord.Interaction):
    # Retrieve guild options from MongoDB
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    
    # Helper functions
    def format_boolean(value):
        return "✅ Enabled" if value else "❌ Disabled"

    def format_list(value):
        return ", ".join(value) if value else "None"

    # Create the embed
    embed = discord.Embed(
        title=f"{interaction.guild.name} Settings",
        description="",
        color=discord.Color.blurple()
    )

    # Populate the embed with settings
    embed.add_field(name="Time Zone", value=f"`{guild_options['tz']}`", inline=False)
    embed.add_field(name="Removed Maps", value=format_list(guild_options['removed_maps']), inline=False)
    embed.add_field(name="Added Maps", value=format_list(guild_options['added_maps']), inline=False)
    embed.add_field(
        name="Elo System",
        value="Using **Rank System**" if guild_options['ranks'] else "Using **Point System**",
        inline=False
    )
    embed.add_field(
        name="Threads Enabled",
        value=f"{format_boolean(guild_options['threads'])}: Threads for lobbys",
        inline=False
    )
    
    if not guild_options["ranks"]:
        embed.add_field(
            name="Double Points on Weekends (Points System)",
            value=f"{format_boolean(guild_options['doublePointsWeekend'])}: Double points during weekends",
            inline=False
        )
        embed.add_field(
            name="Double Points for Negative Elo",
            value=f"{format_boolean(guild_options['doublePointsWeekendNegativeElo'])}: Double points for negative elo players during weekends",
            inline=False
        )
        
    embed.add_field(name="Current Season", value=f"`{guild_options['season']}`", inline=False)
    embed.add_field(name="Next Reset Date", value=f"`{guild_options['next_reset']}`", inline=False)
    embed.add_field(
        name="Allow Downward Joins",
        value=f"{format_boolean(guild_options['downward_joins'])}: Higher-ranked players to join lower-ranked queues",
        inline=False
    )
    embed.add_field(
        name="Separate Matchmaking Queues",
        value=f"{format_boolean(guild_options['seperate_mm'])}: Separate queues by bs stats (tryhard/casual)",
        inline=False
    )
    if guild_options['seperate_mm']:
        minimum_trophies = guild_options["minimum_trophies"]
        minimum_3v3_wins = guild_options["minimum_3v3_wins"]
        embed.add_field(
            name="Tryhard Requirements",
            value=f"Trophies: {minimum_trophies}\n3v3 Wins: {minimum_3v3_wins}",
            inline=False
        ) 
        
    embed.add_field(
        name="Separate Matchmaking Roles",
        value=f"{format_boolean(guild_options['seperate_mm_roles'])}: Roles to separate matchmaking",
        inline=False
    )
    if guild_options['seperate_mm_roles']:
        roles = ", ".join([interaction.guild.get_role(int(role_id)).mention for role_id in guild_options["mm_roles"]])
        embed.add_field(
            name="Matchmaking Roles",
            value=roles,
            inline=False
        ) 
    
    embed.add_field(
        name="Leaderboard Player Limit",
        value=f"Sending up to `{guild_options['lb_limit']}` players per leaderboard",
        inline=False
    )
    embed.add_field(
        name="Leaderboard Roles",
        value=f"{format_boolean(guild_options['lb_all_roles'])}: Sending seperate LB for each role",
        inline=False
    )
    embed.add_field(
        name="Anonymous Queues",
        value=f"{format_boolean(guild_options['anonymous_queues'])}: Players anonymous in queues",
        inline=False
    )
    embed.add_field(
        name="Elo Boundary",
        value=f"`{guild_options['eloBoundary']}` maximum elo difference for matchmaking",
        inline=False
    )

    # Send the embed
    await interaction.response.send_message(embed=embed)

  @list_settings.error
  async def list_settings_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
    await self.__handle_error("list_settings", interaction, error)


  @guild_only       
  @app_commands.command(description="set timezone for your timeouts and lb updates")
  async def timezone(self, interaction: discord.Interaction, 
			timezone: Literal[
        "UTC", "CET", "JST", "EDT", "EST", "BRT", "PST", "GMT", "AEST", "SAST",
        "EAT", "AST", "WIB", "MSK", "CST", "IST", "AKST", "NZST", "WAT", "HST", "KST"
    	],
   ):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")      
        
    options = mongodb.findGuildOptions(interaction.guild.id)
    
    # Map the user input to the correct timezone strings
    timezone_mapping = {
        "UTC": "UTC",
        "CET": "Europe/Berlin",
        "JST": "Asia/Tokyo",
        "EDT": "US/Eastern",
        "EST": "US/Eastern",
        "BRT": "America/Sao_Paulo",
        "PST": "US/Pacific",
        "GMT": "Europe/London",
        "AEST": "Australia/Sydney",
        "SAST": "Africa/Johannesburg",
        "EAT": "Africa/Nairobi",
        "AST": "Asia/Riyadh",
        "WIB": "Asia/Jakarta",
        "MSK": "Europe/Moscow",
        "CST": "Asia/Shanghai",
        "IST": "Asia/Kolkata",
        "AKST": "US/Alaska",
        "NZST": "Pacific/Auckland",
        "WAT": "Africa/Lagos",
        "HST": "US/Hawaii",
        "KST": "Asia/Seoul",
    }

		# Map user input to the actual timezone
    pytz_timezone = timezone_mapping[timezone]
    
    if pytz_timezone == options["tz"]:
      return await interaction.response.send_message(f"🫢 Timezone {timezone} - {pytz_timezone} is already set.")

    options["tz"] = pytz_timezone
    mongodb.saveGuild(options)
    await interaction.response.send_message(f"✅ Timezone set to {timezone} - {pytz_timezone}.")

  @timezone.error
  async def timezone_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("timezone",interaction,error)
  
  
  @guild_only
  @app_commands.command(description="sets max elo difference to host")
  async def elo_boundary(self, interaction: discord.Interaction, limit: int):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    guild_options["eloBoundary"] = limit
    mongodb.saveGuild(guild_options)
    return await interaction.response.send_message(f"✅ Elo Boundary set to {limit}")

  @elo_boundary.error
  async def elo_boundary_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("elo_boundary",interaction,error)
     

  @guild_only
  @app_commands.command(description="sets next season reset day")
  async def set_season_end(self, interaction: discord.Interaction, next_reset_date: str):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    guild_options["next_reset"] = next_reset_date
    mongodb.saveGuild(guild_options)
    return await interaction.response.send_message(f"✅ Next Season ends on {next_reset_date}")

  @set_season_end.error
  async def set_season_end_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("set_season_end",interaction,error)
     
      
  @guild_only
  @app_commands.command(description="enables/disables all roles lbs")
  async def lb_all_roles(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["lb_all_roles"]:
        guild_options["lb_all_roles"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(content=f"🫡 Sending only the top roles lb for each region.")
    else:
        guild_options["lb_all_roles"] = True
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(f"✅ Sending seperate lb for each role and region.")

  @lb_all_roles.error
  async def lb_all_roles_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("lb_all_roles",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="sets max amount of players to display on lb")
  async def lb_player_limit(self, interaction: discord.Interaction, limit: int):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    guild_options["lb_limit"] = limit
    mongodb.saveGuild(guild_options)
    return await interaction.response.send_message(f"✅ Lb player limit set to {limit}")

  @lb_player_limit.error
  async def lb_player_limit_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("lb_player_limit",interaction,error)
     
       
     
  @guild_only
  @app_commands.command(description="enables/disables dbl point weekends for negative elo players")
  async def dbl_point_weekends_neg_elo(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["doublePointsWeekendNegativeElo"]:
        guild_options["doublePointsWeekendNegativeElo"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(content=f"🫡 Double Point Weekends for negative elo players disabled.")
    else:
        guild_options["doublePointsWeekendNegativeElo"] = True
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(f"✅ Double Point Weekends for negative elo players activated")

  @dbl_point_weekends_neg_elo.error
  async def dbl_point_weekends_neg_elo_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("dbl_point_weekends_neg_elo",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="enables/disables dbl point weekends")
  async def dbl_point_weekends(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["doublePointsWeekend"]:
        guild_options["doublePointsWeekend"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(content=f"🫡 Double Point Weekends disabled.")
    else:
        guild_options["doublePointsWeekend"] = True
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(f"✅ Double Point Weekends activated")

  @dbl_point_weekends.error
  async def dbl_point_weekends_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("dbl_point_weekends",interaction,error)
     
    
  @guild_only
  @app_commands.command(description="enables/disables threads")
  async def matchchannel_mode(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["threads"]:
        guild_options["threads"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(content=f"🫡 Matches will be sent in #matches-running.")
    else:
        guild_options["threads"] = True
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(f"✅ Matches will be in private threads")

  @matchchannel_mode.error
  async def matchchannel_mode_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("matchchannel_mode",interaction,error)



  @guild_only
  @app_commands.command(description="sets if players in queue are shown")
  async def anonymous_queues(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["anonymous_queues"]:
        guild_options["anonymous_queues"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(content=f":loudspeaker:  Players in queue are now visible.")
    else:
        guild_options["anonymous_queues"] = True
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(f":performing_arts:  Players in queue are now hidden.")

  @anonymous_queues.error
  async def anonymous_queues_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("anonymous_queues",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="enables/disables higher level players joining lower mms")
  async def downward_joins(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["downward_joins"]:
        guild_options["downward_joins"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(content=f"🫡 Downward Joins deactivated.")
    else:
        guild_options["downward_joins"] = True
        mongodb.saveGuild(guild_options)
        return await interaction.response.send_message(f"🔥 Downward Joins active")

  @downward_joins.error
  async def downward_joins_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("downward_joins",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="enables/disables mm seperation")
  async def seperate_mm(self, interaction: discord.Interaction, minimum_trophies: int, minimum_3v3_wins: int):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    await interaction.response.defer(ephemeral=True)
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["seperate_mm"]:
        guild_options["seperate_mm"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.edit_original_response(content=f"🫡 Matchmaking not seperated anymore")
    else:
        guild_options["seperate_mm"] = True
        guild_options["seperate_mm_roles"] = False
        guild_options["minimum_trophies"] = minimum_trophies
        guild_options["minimum_3v3_wins"] = minimum_3v3_wins
        for user in mongodb.findGuildUsers(interaction.guild.id):
            if "enthusiasm" in user:
                del user["enthusiasm"]
                mongodb.saveUser(user)
        mongodb.saveGuild(guild_options)
        return await interaction.edit_original_response(content=f"✅✌️ Seperating matchmaking with tryhard players having more than {minimum_trophies} 🏆 and more than {minimum_3v3_wins} 3v3 wins.")

  @seperate_mm.error
  async def seperate_mm_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("seperate_mm",interaction,error)


  @guild_only
  @app_commands.command(description="enables/disables mm seperation by up to 6 roles")
  async def seperate_mm_roles(self, interaction: discord.Interaction, good_player_role: discord.Role, player_role2: discord.Role,
    player_role3: discord.Role = None, player_role4: discord.Role = None, player_role5: discord.Role = None, player_role6: discord.Role = None):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    await interaction.response.defer(ephemeral=True)
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    if guild_options["seperate_mm_roles"]:
        guild_options["seperate_mm_roles"] = False
        mongodb.saveGuild(guild_options)
        return await interaction.edit_original_response(content=f"🫡 Matchmaking not seperated anymore")
    else:
        guild_options["seperate_mm_roles"] = True
        guild_options["seperate_mm"] = False
        roles = [good_player_role.id, player_role2.id]
        if player_role3:
            roles.append(player_role3.id)
        if player_role4:
            roles.append(player_role4.id)
        if player_role5:
            roles.append(player_role5.id)
        if player_role6:
            roles.append(player_role6.id)
        
        guild_options["mm_roles"] = roles
        self.bot.logger.info(f"Roles {guild_options['mm_roles']}")
        mongodb.saveGuild(guild_options)
        roleslisting = ", ".join(interaction.guild.get_role(role_id).mention for role_id in roles)
        return await interaction.edit_original_response(content=f"✌️ Seperating matchmaking using these roles: {roleslisting}.")

  @seperate_mm_roles.error
  async def seperate_mm_roles_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("seperate_mm_roles",interaction,error)

 

  @guild_only
  @app_commands.command(description="resets the elo.")
  async def reset_elo(self, interaction: discord.Interaction, new_season_name: str, next_reset_date: str):
    if not interaction.user.guild_permissions.administrator or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    await interaction.response.defer()
    
    try:
      await resetGuildElo(self.bot, interaction.guild, new_season_name, next_reset_date)
    except discord.errors.Forbidden:
      return await interaction.channel.send(f"Missing permissions for reseting elo in {interaction.guild.name}")
    return await interaction.edit_original_response(content=f"✅ Elo resetted, check the leaderboard")

  @reset_elo.error
  async def reset_elo_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("reset_elo",interaction,error)
     
     
     
  @guild_only
  @app_commands.command(description="toggles between the plain point system and the rank system")
  async def elo_system(self, interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    await interaction.response.defer()
    
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    modes = ["Ranks System", "Points System"] if guild_options["ranks"] else ["Points System", "Ranks System"]

    # Prompt the user for confirmation
    await interaction.edit_original_response(
            content=(
                f"You are about to toggle the elo system.\n"
                f"The system is currently using the **{modes[0]}**.\n\n"
                "⚠️ This will reset everyone's elo to 0.\n"
                "THE ELO RESET ACTION CANNOT BE UNDONE! ⚠️\n\n"
                "Type `CONFIRM` to proceed or `CANCEL` to cancel."
            )
        )

    def check(m: discord.Message):
        return m.author == interaction.user and m.channel == interaction.channel and m.content.lower() in ["confirm", "cancel"]

    try:
        # Wait for user input
        msg: discord.Message = await self.bot.wait_for("message", timeout=30.0, check=check)

        if msg.content.lower() == "confirm":
            guild_options["ranks"] = not guild_options["ranks"]
            mongodb.saveGuild(guild_options)
            await resetGuildElo(self.bot, interaction.guild)
            await interaction.followup.send(content=f"Elo of all players has been set to 0.")
            return await interaction.followup.send(f"✅ You are now using the **{modes[1]}**.")
        else:
            return await interaction.followup.send(content=f"❌ Action canceled. The system is still using the **{modes[0]}**.")

    except:
        await interaction.followup.send(content=f"⏳ You took too long to respond. The action has been canceled.")

  @elo_system.error
  async def elo_system_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
    await self.__handle_error("elo_system",interaction,error)
        
        
        
async def setup(bot):
  await bot.add_cog(GuildSettings(bot))