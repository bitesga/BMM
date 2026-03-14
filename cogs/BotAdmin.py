from discord.ext import commands
import discord
from discord import app_commands
from discord.app_commands import guild_only
import json
import mongodb
import random
import string
import datetime, pytz
import asyncio
from utils import dynamic_guild_cooldown

botAdmins = [324607583841419276, 818879706350092298, 230684337341857792]

def resetPlayer(player):
  player["elo"] = 0
  player["wins"] = 0
  player["winstreak"] = 0
  player["matches_played"] = 0
  player["rank"] = "Bronze 1"
  return player

async def resetGuildElo(bot, guild: discord.Guild, new_season_name: str = None, next_reset_date: str = None):
  guild_options = await asyncio.to_thread(mongodb.findGuildOptions, guild.id)
  topPlayers = await asyncio.to_thread(mongodb.getTop3Global, guild.id)
  guild_options["top3_last_season"] = topPlayers[:3]
  players = await asyncio.to_thread(lambda: list(mongodb.findGuildUsers(guild.id)))
  for player in players:
    player = resetPlayer(player)
    await asyncio.to_thread(mongodb.saveUser, player)
  if new_season_name and next_reset_date:
    guild_options["season"] = new_season_name
    guild_options["next_reset"] = next_reset_date
  print(guild_options)
  await asyncio.to_thread(mongodb.saveGuild, guild_options)
  
  
  # Notify the server that the season has been reset
  try:
    announcementChannel, _, _, _, _ = await bot.getChannels(guild)
    modes = ["Ranks System", "Points System"] if guild_options["ranks"] else ["Points System", "Ranks System"]
    await announcementChannel.send(f"<:lb:1318628338906173490> **The season has been reset!** <:lb:1318628338906173490>\n" +
                                    f"elo for all players has been reset to 0 and leaderboard was cleared. Good luck in the new season, using the {modes[0]}! 🎉")
  except:
    pass
  
def generate_private_key(length=12):
    """Generate a random private key."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def is_unique_private_key(private_key, guild_id):
    """Check if a private key already exists in the database."""
    return mongodb.findPrivate(private_key, guild_id) is None  

class BotAdmin(commands.Cog):
  
  def __init__(self, bot):
    self.bot = bot
      
     
  @guild_only
  @app_commands.command(description="create a private room")
  @dynamic_guild_cooldown(seconds=15)
  async def private_room(self, interaction: discord.Interaction, name: str, server_id: str):
    if interaction.user.id not in botAdmins:
      if interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(content="⛔ Please ask Shegyo or Royal to use this.")
      return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")

    await interaction.response.defer()
    
    guild_options = await asyncio.to_thread(mongodb.findGuildOptions, interaction.guild.id)

    # Generate a unique private key
    private_key = generate_private_key()
    while not await asyncio.to_thread(is_unique_private_key, private_key, server_id):
        private_key = generate_private_key()
    
    # Create the private room data
    private_room_data = {
        "name": name,
        "private_key": private_key,
        "guild_id" : server_id,
        "expiration_date" : datetime.datetime.now(pytz.timezone(guild_options["tz"])) + datetime.timedelta(days=30)
    }

    # Save to database
    if await asyncio.to_thread(mongodb.savePrivate, private_room_data):
        return await interaction.followup.send(content=f"✅ Private room `{name}` created successfully with key: `{private_key}` in Server with id {server_id}.\nView it by using `/check_stats`")
    else:
        return await interaction.followup.send(content="❌ Failed to create private room. Please try again.")

  @private_room.error
  async def private_room_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("private_room",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="block an admin from using admin commands")
  @dynamic_guild_cooldown(seconds=15)
  async def admin_block(self, interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in botAdmins:
      if interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(content="⛔ Please ask Shegyo or Royal to use this.")
      return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")

    await interaction.response.defer()

    with open("blockedAdmins.json", "r", encoding="UTF-8") as f:
        blockedAdmins = json.load(f)

    if str(user.id) in blockedAdmins:
        return await interaction.followup.send(content=f"⛔ {user.mention} is already blocked!", file=discord.File("blockedAdmins.json"))

    blockedAdmins[str(user.id)] = user.display_name
    with open("blockedAdmins.json", "w", encoding="UTF-8") as f:
        json.dump(blockedAdmins, f, indent=2)

    await interaction.followup.send(content=f"✅ {user.mention} added to admin block list!", file=discord.File("blockedAdmins.json"))

  @admin_block.error
  async def admin_block_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("admin_block",interaction,error)
     
  
  @guild_only
  @app_commands.command(description="remove an admin from the block list")
  @dynamic_guild_cooldown(seconds=15)
  async def admin_block_remove(self, interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in botAdmins:
      if interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(content="⛔ Please ask Shegyo or Royal to use this.")
      return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")

    await interaction.response.defer()

    with open("blockedAdmins.json", "r", encoding="UTF-8") as f:
        blockedAdmins = json.load(f)

    if not str(user.id) in blockedAdmins:
        return await interaction.followup.send(content=f"⛔ {user.mention} is not a blocked admin!", file=discord.File("blockedAdmins.json"))

    del blockedAdmins[str(user.id)]
    with open("blockedAdmins.json", "w", encoding="UTF-8") as f:
        json.dump(blockedAdmins, f, indent=2)

    await interaction.followup.send(content=f"✅ {user.mention} removed from admin block list!", file=discord.File("blockedAdmins.json"))

  @admin_block_remove.error
  async def admin_block_remove_remove_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("admin_block_remove",interaction,error)      
     
     
  @guild_only
  @app_commands.command(description="add a user to the admin list")
  @dynamic_guild_cooldown(seconds=15)
  async def admin_add(self, interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in botAdmins:
      if interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(content="⛔ Please ask Shegyo or Royal to use this.")
      return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")

    await interaction.response.defer()

    with open("admins.json", "r", encoding="UTF-8") as f:
        admins = json.load(f)

    if str(user.id) in admins:
        return await interaction.followup.send(content=f"⛔ {user.mention} is already admin!")

    admins[str(user.id)] = user.display_name
    with open("admins.json", "w", encoding="UTF-8") as f:
        json.dump(admins, f, indent=2)

    await interaction.followup.send(content=f"✅ {user.mention} added to admin list!", file=discord.File("admins.json"))

  @admin_add.error
  async def admin_add_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("admin_add",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="remove a user from the admin list")
  @dynamic_guild_cooldown(seconds=15)
  async def admin_remove(self, interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in botAdmins:
      if interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(content="⛔ Please ask Shegyo or Royal to use this.")
      return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")

    await interaction.response.defer()

    with open("admins.json", "r", encoding="UTF-8") as f:
        admins = json.load(f)

    if not str(user.id) in admins:
        return await interaction.followup.send(content=f"⛔ {user.mention} is not an admin!", file=discord.File("admins.json"))

    del admins[str(user.id)]
    with open("admins.json", "w", encoding="UTF-8") as f:
        json.dump(admins, f, indent=2)

    await interaction.followup.send(content=f"✅ {user.mention} removed from admin list!", file=discord.File("admins.json"))

  @admin_remove.error
  async def admin_remove_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("admin_remove",interaction,error)      
        

  @app_commands.command(description="delete category and all its channels")
  @dynamic_guild_cooldown(seconds=15)
  async def dcat(self, interaction: discord.Interaction, name: str):
      if interaction.user.id not in botAdmins:
          return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")

      await interaction.response.defer(ephemeral=True)

      for category in interaction.guild.categories:
        if name == category.name:
          for ch in category.text_channels:
            await ch.delete()
          await category.delete()
     
      await interaction.edit_original_response(content=f"✅ Cats and Channels deleted")
    
  @dcat.error
  async def dcat_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("dcat",interaction,error)
     
     
    #Locks matchmaking
  @app_commands.command(description="locks matchmaking until unlocked.")
  @dynamic_guild_cooldown(seconds=15)
  async def lock_mm(self, interaction: discord.Interaction, reason: str):
    if not interaction.user.id in botAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    await asyncio.to_thread(mongodb.setLock, reason)
    return await interaction.response.send_message(content=f"⛔ Matchmaking locked.")

  @lock_mm.error
  async def lock_mm_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("lock_mm",interaction,error)

    # Unlocks matchmaking
  @app_commands.command(description="unlock matchmaking")
  @dynamic_guild_cooldown(seconds=15)
  async def unlock_mm(self, interaction: discord.Interaction):
    if not interaction.user.id in botAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    await asyncio.to_thread(mongodb.deleteLock)
    return await interaction.response.send_message(content=f"✅ Matchmaking unlocked.")

  @unlock_mm.error
  async def unlock_mm_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("unlock_mm",interaction,error)
     
     
    
  @app_commands.command(description="sends bot announcement to all servers.")
  @dynamic_guild_cooldown(seconds=15)
  async def announce(self, interaction: discord.Interaction, msg: str):
    if not interaction.user.id in botAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    await interaction.response.defer()
    for guild in self.bot.guilds:
      try:
        announcementChannel, _, _, _, _ = await self.bot.getChannels(guild)
        if announcementChannel:
          formatted_message = msg.replace('<br>', '\n')
          await announcementChannel.send(f"### 🗣️ Announcement to all servers by {interaction.user.display_name}\n\n{formatted_message}")
      except discord.errors.Forbidden:
        await interaction.channel.send(f"Missing permissions for sending announce to {guild.name}")
      except Exception as e:
        print(f"Unknown error announcing in {guild.name}: {str(e)}")
        await interaction.channel.send(f"Unknown error announcing in {guild.name}: {str(e)}")
    return await interaction.edit_original_response(content=f"✅ Message sent:\n\n {formatted_message}")

  @announce.error
  async def announce_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("announce",interaction,error)
     
     
  async def __handle_error(self, function, interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
      await interaction.response.send_message(f"❌ {str(error)}", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.NoPrivateMessage):
        await interaction.response.send_message("❌ This command cannot be run in private messages.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    else:
        print(f"Unhandled error in \"{function}\" command: {error}")
        await interaction.response.send_message(f"❌ An unknown error occurred: {error}", ephemeral=True)
      
        
async def setup(bot):
  await bot.add_cog(BotAdmin(bot))