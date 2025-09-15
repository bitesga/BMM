from discord.ext import commands, tasks
import discord, asyncio
from discord import app_commands
from discord.app_commands import guild_only
import mongodb
from datetime import datetime, timedelta
import pytz
from utils import logger
import json


# Load elo system texts
with open("elosystems.json", "r", encoding="UTF-8") as f:
    elosystems = json.load(f)

  
async def update_leaderboard(bot, guild):    
    try:
        _, _, _, leaderBoardChannel, _ = await bot.getChannels(guild)
    except:
        logger.warning(f"No leaderboard channel found or created for guild: {guild.name}")
        return None
    
    if not leaderBoardChannel:
        return logger.warning(f"⚠️ Leaderboard Channel was not found and could not be created.")
        
    await leaderBoardChannel.purge(limit=50, check=lambda m: True)
    guild_options = mongodb.findGuildOptions(guild.id)
    
    role_name = ""
    for region in ["EMEA", "SA", "NA", "APAC"]:
        if guild_options["seperate_mm_roles"]:
            roles = guild_options["mm_roles"] if guild_options["lb_all_roles"] else [guild_options["mm_roles"][0]]
            for role_id in roles: 
                role_name = guild.get_role(role_id).name if guild.get_role(role_id) else f"<@&{role_id}>"
                top_players = list(mongodb.getTopEloPlayers(guild.id, region, role_id=role_id, limit=guild_options["lb_limit"]))
                
                for i in range(int(len(top_players) / 100) + 1):
                    # Prüfe, ob es genug Spieler für die nächste Seite gibt
                    if len(top_players) <= i * 100:
                        break

                    leaderboard_message = ""
                    for idx, player in enumerate(top_players[i * 100 : i * 100 + 100], start=1):
                        user = bot.get_user(player.get("discord_id", "Unknown"))
                        player_name = user.display_name if user else "Unknown Player"
                        elo = player.get("elo", 0)
                        leaderboard_message += f"{idx + 100 * i}. {player_name} : {elo}\n"

                    # Erstelle ein Embed für die aktuelle Seite
                    embed = discord.Embed(
                        title=f"🏆 {region} {role_name} {i+1} 🏆",
                        description=leaderboard_message,
                        color=discord.Color.gold(),
                    )
                    await leaderBoardChannel.send(embed=embed)
                    
                    await asyncio.sleep(1)
            
        elif guild_options["seperate_mm"]:
            roles = ["tryhard", "casual"] if guild_options["lb_all_roles"] else ["tryhard"]
            for enthusiasm in ["tryhard", "casual"]:
                top_players = list(mongodb.getTopEloPlayers(guild.id, region, enthusiasm=enthusiasm, limit=guild_options["lb_limit"]))
                
                for i in range(int(len(top_players) / 100) + 1):
                    # Prüfe, ob es genug Spieler für die nächste Seite gibt
                    if len(top_players) <= i * 100:
                        break

                    leaderboard_message = ""
                    for idx, player in enumerate(top_players[i * 100 : i * 100 + 100], start=1):
                        user = bot.get_user(player.get("discord_id", "Unknown"))
                        player_name = user.display_name if user else "Unknown Player"
                        elo = player.get("elo", 0)
                        leaderboard_message += f"{idx + 100 * i}. {player_name} : {elo}\n"

                    # Erstelle ein Embed für die aktuelle Seite
                    embed = discord.Embed(
                        title=f"🏆 {region} {enthusiasm.title()} {i+1} 🏆",
                        description=leaderboard_message,
                        color=discord.Color.gold(),
                    )
                    await leaderBoardChannel.send(embed=embed)
                    
                    await asyncio.sleep(1)
        else:     
            top_players = list(mongodb.getTopEloPlayers(guild.id, region, limit=guild_options["lb_limit"]))
            
            for i in range(int(len(top_players) / 100) + 1):
                # Prüfe, ob es genug Spieler für die nächste Seite gibt
                if len(top_players) <= i * 100:
                    break

                leaderboard_message = ""
                for idx, player in enumerate(top_players[i * 100 : i * 100 + 100], start=1):
                    user = bot.get_user(player.get("discord_id", "Unknown"))
                    player_name = user.display_name if user else "Unknown Player"
                    elo = player.get("elo", 0)
                    leaderboard_message += f"{idx + 100 * i}. {player_name} : {elo}\n"

                # Erstelle ein Embed für die aktuelle Seite
                embed = discord.Embed(
                    title=f"🏆 {region} {i+1} 🏆",
                    description=leaderboard_message,
                    color=discord.Color.gold(),
                )
                await leaderBoardChannel.send(embed=embed)
                    
                await asyncio.sleep(1)

        


    # Füge das Last-Update-Embed hinzu
    embed=discord.Embed(title="", description="", color=discord.Color.gold())
    
    last_update = datetime.now(pytz.timezone(guild_options["tz"])).strftime(f"%d.%m.%Y, %H:%M {guild_options['tz']} timezone.")
    embed.set_footer(text=f"last update: {last_update}")
        
    elo_text = "rankSystem" if guild_options["ranks"] else "pointSystem"
    embed.description += f'\n\n**{elosystems[elo_text]["name"]}**\n{elosystems[elo_text]["value"]}'
    
    
    season = guild_options["season"] if guild_options["season"] else "Beta Season"
    next_reset = guild_options["next_reset"] if guild_options["next_reset"] else (datetime.now() + timedelta(days=60)).strftime(f"01.%m.%Y")
    embed.add_field(
        name=season,
        value=f"Stats will be resetted on {next_reset}.",
        inline=False
    )
    
    
    if guild_options["top3_last_season"]:
        top3_text = ""
        top3_emojis = ["🥇", "🥈", "🥉"]
        for idx, player in enumerate(guild_options["top3_last_season"]):
            top3_text += f"{top3_emojis[idx]} <@{player['discord_id']}> {player['elo']}"
        
        embed.add_field(
            name="<:lb:1318628338906173490> Top 3 Last Season",
            value=top3_text,
            inline=False
        )
    
    # Sende noch das Double Point Embed wenn messages vorhanden sind
    messages = [message async for message in leaderBoardChannel.history(limit=10)]
    if messages:
        await leaderBoardChannel.send(embed=embed)
        if datetime.now(pytz.timezone(guild_options["tz"])).weekday() in [5, 6] and not guild_options["ranks"]:
            if guild_options["doublePointsWeekend"]:
                await leaderBoardChannel.send(embed=discord.Embed(
                            title=f"🚀 Elo Inflation Weekend is active 🚀",
                            description="Double Plus points for your wins!",
                            color=discord.Color.orange()))
            
            elif guild_options["doublePointsWeekendNegativeElo"]:
                await leaderBoardChannel.send(embed=discord.Embed(
                            title=f"🚀 Elo Inflation Weekend for players with negative elo is active 🚀",
                            description="Double Plus points for your wins if you have negative elo!",
                            color=discord.Color.orange()))
            

    else:
        await leaderBoardChannel.send("No Played Matches found for this Server 🫣")
    return leaderBoardChannel



class Leaderboard(commands.Cog):
  
  def __init__(self, bot):
    self.bot = bot
    self.refresh_leaderboard.start()


  @tasks.loop(minutes=3)
  async def refresh_leaderboard(self):
    
    logger.info("Starting leaderboard refresh task.")
    for guild in self.bot.guilds:
        self.bot.logger.info(f"updating {guild.name}")
        try:
            if str(guild.id) not in self.bot.allowedGuilds:
                continue

            await update_leaderboard(self.bot, guild)
            await asyncio.sleep(3)
            
        except discord.errors.Forbidden:
            logger.warning(f"No permission to update lb in server {guild.name}")
        
        except Exception as e:
            logger.error(f"An error occurred while updating lb in guild: {guild.name} (ID: {guild.id}). Error: {e}", exc_info=True)


  @guild_only
  @app_commands.command(description="update leaderboard leaderboard")
  async def update_leaderboard(self, interaction: discord.Interaction):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
    
    try:
        leaderboardChannel: discord.TextChannel = await update_leaderboard(self.bot, interaction.guild)
        if leaderboardChannel:
            return await interaction.response.send_message(content=f"✅ {leaderboardChannel.mention} successfully updated.")
        return await interaction.response.send_message(content=f"⚠️ Leaderboard Channel was not found and could not be created.")
    except discord.errors.Forbidden:
        self.bot.logger.warning(f"No permission to update lb in this server.")

  @update_leaderboard.error
  async def update_leaderboard_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("update_leaderboard",interaction,error)
     
     
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

async def setup(bot):
  await bot.add_cog(Leaderboard(bot))
