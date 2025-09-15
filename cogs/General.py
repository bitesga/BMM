from discord.ext import commands
import discord
from discord import app_commands
from discord.app_commands import guild_only
import asyncio
from mongodb import findGuildOptions, saveGuild

from utils import LinkButton, View

class General(commands.Cog):
  
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
        
         
  @app_commands.command(description="want to give something back? cool. learn how.")
  async def tip(self, interaction: discord.Interaction):
    viewItems = [LinkButton("Paypal", "https://paypal.me/RoyalGamerBs", "<:paypal:1226193285526327376>")]
    embed = discord.Embed(title="", description="""Hey, we are a young development team and - among other things - developed this Discord PL bot here.
                          If you want to support us, feel free to leave a tip. 💕

													Important! Please only if you can afford it and you are not harming yourself! We appreciate every small donation. 🙂
             
													Thank you for your interest in our bot and we hope you enjoy using it. 🔥""", color=discord.Color.pink())
    await interaction.response.send_message(embed=embed, view=View(viewItems))
 
  @tip.error
  async def tip_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("tip",interaction,error)            
     
  
  
  @app_commands.command(description="display user commands")
  async def help(self, interaction: discord.Interaction):
    helpEmbed = discord.Embed(title="User Commands", description="""
- `/save_id` to register and set your region
- `/check_stats` to view a users stats
- `/matchmaking` to start a matchmaking
- `/maps` to checkout the mappool
- `/validate_result` makes the bot validate a match if btn doesnt react
- `/list_settings` displays guild settings
- `/tips` to get a donations link""", color=discord.Color.pink())
    await interaction.response.send_message(embed=helpEmbed)

  @help.error
  async def help_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("help",interaction,error)            
     
     

  @app_commands.command(description="display admin commands")
  async def help_admin(self, interaction: discord.Interaction):
    helpEmbed = discord.Embed(title="Admin Commands", description="""
ℹ️ For `/add_points`, `/add_wins`, `/add_matches_played`, `/add_winstreak` pass the same user multiple times if you want to edit only one or two.
  """, color=discord.Color.pink())
    
    helpEmbed.add_field(name="Guild Settings", value="""                   
- `/timezone` sets server timezone
- `/dbl_point_weekends` enables/disables dbl point wkends
- `/dbl_point_weekends_neg_elo` enables/disables dbl point wkends for negative elo players
- `/matchchannel_mode` switches matches in #matches-running/threads
- `/unlimited_lb` enables/disables unlimited lb (will send all players in leaderboard and not only top 50 per region)
- `/elo_boundary` sets max elo difference to host
- `/seperate_mm` enables/disables matchmaking seperation
- `/seperate_mm_roles` enables/disables seperation by up to 6 roles
- `/downward_joins` enables/disables higher level players joining lower mms
- `/anonymous_queues` sets if players in queue are shown
- `/elo_system` toggles between the plain point system and the rank system""")
    
    helpEmbed.add_field(name="Moderation", value="""
- `/install` creates all bot channels and resends tutorial     
- `/uninstall` deletes all mm channels and roles and removes the bot from server
- `/add_user` registers a user
- `/delete_user` unregisters a user
- `/remove_from_match_status` frees a user if stuck in match
- `/delete_mm` deletes ongoing matchmaking
- `/timeout` forbids a user from playing until given date (format: DD.MM.YYYY, HH:MM)
- `/remove_timeout` allows user to play again
- `/add_points` adds or substracts points to given users elos.
- `/add_wins` adds or substracts wins count of given users.
- `/add_matches_played` adds or substracts to the match count of given users. 
- `/add_winstreak` adds or substracts to winstreak count of given users. 
  (pass the same user multiple times if you want to edit only one or two)
- `/enthusiasm_change` sets tryhard/casual status to user
- `/set_result` forces a result for a match
""")
    
    helpEmbed.add_field(name="Maps", value="""
- `/map_add` adds a map to mappool
- `/map_remove` removes a map from mappool
- `/reset_maps` resets to standard mappool""")
    
    helpEmbed.add_field(name="Leaderboard", value="""
- `/lb_all_roles` toggles if all roles get there lb or only the top role
- `/lb_player_limit` sets maximum amount of players for lb per region and role""")
    
    await interaction.response.send_message(embed=helpEmbed)

  @help_admin.error
  async def help_admin_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("help_admin",interaction,error)           

     
  @guild_only
  @app_commands.command(description="creates all needed pl channels")
  async def install(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
          return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")
        
    await interaction.response.defer(ephemeral=True)
    await self.bot.getChannels(interaction.guild, create=True)
    await interaction.edit_original_response(content=f"channels created ✅")
 
  @install.error
  async def install_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("install",interaction,error)    
     
     
  @guild_only
  @app_commands.command(description="deletes all channels and roles and leaves the server")
  async def uninstall(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    guild_options = findGuildOptions(interaction.guild.id)
    await interaction.response.defer(ephemeral=True)
    try:
      guild_options = await self.bot.delete_all_roles(interaction.guild, guild_options)
      guild_options = await self.bot.delete_all_channels(interaction.guild, guild_options)
    except discord.errors.Forbidden:
      return await interaction.edit_original_response(content=f"⚠️ I have no permissions to delete roles or channels!")
     
    saveGuild(guild_options) 
    
    # Zusätzliche Löschung der Kanäle
    for category in interaction.guild.categories:
      if "matchmaking" in category.name.lower() and category.text_channels and "bot-announcements" in category.text_channels[0].name:
        for channel in category.text_channels:
          await channel.delete()
        await category.delete()  
        
    await interaction.edit_original_response(content=f"✅ Successfully deleted all my matches and roles and leaving this server in 3 seconds.")
    await asyncio.sleep(3)
    await interaction.guild.leave()
    
  @uninstall.error
  async def uninstall_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("uninstall",interaction,error)
     
           
async def setup(bot):
  await bot.add_cog(General(bot))