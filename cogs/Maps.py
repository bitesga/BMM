from discord.ext import commands
import discord
from discord import app_commands
from discord.app_commands import guild_only
import mongodb
import requests
import asyncio
from utils import simplify, dynamic_guild_cooldown


validModes = ["Gem Grab", "Brawl Ball", "Heist", "Wipeout", "Knockout", "Bounty", "Hot Zone", "Siege"]
mapList = None


async def get_valid_map_list():
    global mapList
    if mapList is not None:
        return mapList

    try:
        response = await asyncio.to_thread(requests.get, "https://api.brawlapi.com/v1/maps", timeout=10)
        full_map_list = response.json().get("list", [])
    except Exception:
        full_map_list = []

    parsed_list = []
    valid_modes_simplified = set(map(simplify, validModes))
    for mapData in full_map_list:
        if simplify(mapData["gameMode"]["name"]) in valid_modes_simplified:
            parsed_list.append(mapData["name"])

    mapList = parsed_list
    return mapList
    
    
async def getCompetitiveMaps(bot, guild_id):
    avatare_guild: discord.Guild = bot.get_guild(1252935099130056734)
    bmm_maps_channel = avatare_guild.get_channel(1354889224926531695)
    history = [message async for message in bmm_maps_channel.history(limit=20)]
    maptext = history[0].content
    maps = maptext.split("\n- ")
    
    guild_options = await asyncio.to_thread(mongodb.findGuildOptions, guild_id)
    
    for removed in guild_options["removed_maps"]:
        maps = [m for m in maps if simplify(m) != simplify(removed)]

    maps.extend([m for m in guild_options["added_maps"] if simplify(m) not in [simplify(existing) for existing in maps]])
    
    return list(set(maps[1:]))

async def getMappoolEmbed(bot, guild_id):
    maps = await getCompetitiveMaps(bot, guild_id)
    mappool_embed = discord.Embed(
        title="🗺️ Mappool 🗺️",
        description="- "+ "\n- ".join(maps),
        color=discord.Color.blue() 
    )
    try:
        mappool_embed.add_field(name="Probability for each map:", value=f"{round(100 / len(maps), 2)}%")
    except:
        pass
    return mappool_embed

class Maps(commands.Cog):
  
  def __init__(self, bot):
    self.bot = bot
    
  # Delete player ID
  @guild_only
  @app_commands.command(description="displays maps")
  @dynamic_guild_cooldown(seconds=15)
  async def maps(self, interaction: discord.Interaction):
    mappool_embed = await getMappoolEmbed(self.bot, interaction.guild.id)
    return await interaction.response.send_message(embed=mappool_embed)

  @maps.error
  async def maps_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("maps",interaction,error)
     
     
  # Delete player ID
  @guild_only
  @app_commands.command(description="add a map to the mappool")
  @dynamic_guild_cooldown(seconds=15)
  async def map_add(self, interaction: discord.Interaction, map: str):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")      
    
    guild_options = await asyncio.to_thread(mongodb.findGuildOptions, interaction.guild.id)
    valid_map_list = await get_valid_map_list()
    
    if not any(simplify(map) == simplify(valid_map) for valid_map in valid_map_list):
        return await interaction.response.send_message(content=f"❓ This Map does not exist.")

    # Echten Namen finden für Konsistenz
    real_map = next(valid_map for valid_map in valid_map_list if simplify(map) == simplify(valid_map))

    # Entfernen aus removed_maps, hinzufügen zu added_maps (vereinfacht vergleichen)
    if any(simplify(real_map) == simplify(m) for m in guild_options["removed_maps"]):
        guild_options["removed_maps"] = [m for m in guild_options["removed_maps"] if simplify(m) != simplify(real_map)]
    if not any(simplify(real_map) == simplify(m) for m in guild_options["added_maps"]):
        guild_options["added_maps"].append(real_map)

    await asyncio.to_thread(mongodb.saveGuild, guild_options)
    mappool_embed = await getMappoolEmbed(self.bot, interaction.guild.id)
    return await interaction.response.send_message(f"✅ Map {map} added successfully", embed=mappool_embed)

  @maps.error
  async def maps_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("map_add",interaction,error)
     
  
  # Delete player ID
  @guild_only
  @app_commands.command(description="removes a map from mappool")
  @dynamic_guild_cooldown(seconds=15)
  async def map_remove(self, interaction: discord.Interaction, map: str):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")      
        
    guild_options = await asyncio.to_thread(mongodb.findGuildOptions, interaction.guild.id)
    valid_map_list = await get_valid_map_list()
    
    if not any(simplify(map) == simplify(valid_map) for valid_map in valid_map_list):
        return await interaction.response.send_message(content=f"❓ This Map does not exist.")

    real_map = next(valid_map for valid_map in valid_map_list if simplify(map) == simplify(valid_map))

    if simplify(real_map) not in [simplify(m) for m in guild_options["removed_maps"]]:
        guild_options["removed_maps"].append(real_map)
    
    guild_options["added_maps"] = [m for m in guild_options["added_maps"] if simplify(m) != simplify(real_map)]

    await asyncio.to_thread(mongodb.saveGuild, guild_options)
    
    mappool_embed = await getMappoolEmbed(self.bot, interaction.guild.id)
    return await interaction.response.send_message(f"✅ Map {real_map} removed successfully", embed=mappool_embed)

  @maps.error
  async def maps_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("map_remove",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="resets to core mappool")
  @dynamic_guild_cooldown(seconds=15)
  async def reset_maps(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")      
    
    guild_options = await asyncio.to_thread(mongodb.findGuildOptions, interaction.guild.id)
    
    guild_options["removed_maps"] = []
    guild_options["added_maps"] = []
    await asyncio.to_thread(mongodb.saveGuild, guild_options)
    
    mappool_embed = await getMappoolEmbed(self.bot, interaction.guild.id)
    return await interaction.response.send_message(f"✅ Maps resetted successfully", embed=mappool_embed)

  @reset_maps.error
  async def reset_maps_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("reset_maps",interaction,error)
     
     
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
  await bot.add_cog(Maps(bot))