from discord.ext import commands
from discord import app_commands
from discord.app_commands import guild_only
import discord
import mongodb
import datetime
import pytz
import asyncio
import validators
from typing import Literal

from views.MatchmakingView import MatchmakingView, delete_mm_embed, get_mm_channel_for_region, get_role_for_ping_and_region
from views.ResultValidationView import  evaluate_winner, refreshElos, fetchBattleLog, handle_points_point_system, handle_points_rank_system
from views.RoleSelectionView import SelectRoleToDeleteMM, delete_mm
from utils import getPlayerForBsId, View, currentFolder
from cogs.BotAdmin import resetPlayer

  
class Commands(commands.Cog):
  def __init__(self, bot : commands.Bot):
    self.bot = bot
    self.mm_lock = asyncio.Lock()
    

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
        self.bot.logger.error(f"Unhandled error in \"{function}\" command: {error}")
        await interaction.response.send_message(f"❌ An unknown error occurred: {error}", ephemeral=True)
    
     
  @guild_only
  @app_commands.command(description="starts matchmaking")
  @app_commands.checks.cooldown(1, 60*5, key=lambda i: (i.user.id and i.user.id != 85342637082240))  # 5 minutes cooldown per user except for bot owner
  async def matchmaking(self, interaction: discord.Interaction, team_code: str):
    await interaction.response.defer(ephemeral=True)

    try:
        async with self.mm_lock:
            now = datetime.datetime.now(pytz.timezone("Europe/Berlin"))

            # Check if matchmaking is closed
            if currentFolder() == "BMM": 
              if now.replace(hour=21, minute=30, second=0, microsecond=0) <= now < now.replace(hour=22, minute=0, second=0, microsecond=0):
                  return await interaction.edit_original_response(content=f"⛔ Matchmaking is closed. Bot is restarting in {60 - now.minute} minutes!")

              # Check if the bot just restarted
              if now.replace(hour=22, minute=0, second=0, microsecond=0) <= now < now.replace(hour=22, minute=5, second=0, microsecond=0):
                  return await interaction.edit_original_response(content=f"⛔ Bot just restarted. Matchmaking will open in {5 - now.minute} minutes!")

            # Validate team code
            if not validators.url(f"https://link.brawlstars.com/invite/gameroom/en?tag={team_code.upper()}"):
                return await interaction.edit_original_response(content="⛔ Invalid Team Code!")

            # Fetch user and guild options
            user_options = mongodb.findUserOptions(interaction.user.id, interaction.guild.id)
            guild_options = mongodb.findGuildOptions(interaction.guild.id)

            # Validate team code length
            if len(team_code) > 10 or len(team_code) < 3:
                return await interaction.edit_original_response(content="⛔ Make sure to provide a valid join code or join link!")

            # Check if user has saved their Brawl Stars ID
            if not user_options["bs_id"]:
                return await interaction.edit_original_response(content="🖊️ Make sure to `/save_id` before using this command!")

            # Check if user is already in a match
            if user_options["in_match"] and user_options["in_match"] > datetime.datetime.now():
                return await interaction.edit_original_response(content="⛔ Finish and evaluate your running match before starting a new one!")

            # Check for enthusiasm level if required
            if guild_options["seperate_mm"] and "enthusiasm" not in user_options:
                return await interaction.edit_original_response(content="⛔ Please `/save_id` to determine your enthusiasm level (tryhard/casual)!")

            # Check for skill level role if required
            player_role = None
            if guild_options["seperate_mm_roles"]:
                for role in reversed(interaction.user.roles):
                    if role.id in guild_options["mm_roles"]:
                        player_role = role
                        break
                if not player_role:
                    return await interaction.edit_original_response(content="⛔ Please ask an admin to get a skill level role!")

            # Check for user timeout
            if "timeout" in user_options:
                timeout_time = pytz.timezone(guild_options["tz"]).localize(user_options["timeout"])
                if timeout_time > datetime.datetime.now(pytz.timezone(guild_options["tz"])):
                    return await interaction.edit_original_response(content=f"⛔ You have been timed out. You can resume playing at: {timeout_time.strftime('%d.%m.%Y, %H:%M')}.")

            # Check for role timeout
            if "roles_timeout" in guild_options:
                for role in interaction.user.roles:
                    if role.id in guild_options["roles_timeout"]:
                        return await interaction.edit_original_response(
                            content=f"⛔ Your role {role.mention} has been timed out. This role can resume playing at: {user_options['timeout'].strftime('%d.%m.%Y, %H:%M')}."
                        )

            # Check for maintenance lock
            lock = mongodb.getLock()
            if lock and "reason" in lock:
                return await interaction.edit_original_response(content=f"⛔ Matchmaking is locked for maintenance right now.\nReason: `{lock['reason']}`")

            # Determine lobby title
            title = "🏆 Matchmaking Lobby 🏆"
            if guild_options["seperate_mm"]:
                title = f"🏆 {user_options['enthusiasm'].title()} Lobby 🏆"
            if guild_options["seperate_mm_roles"]:
                title = f"🏆 {player_role.name.title()} Lobby 🏆"

            # Check if another matchmaking is already running
            enthusiasm = "Overall"
            if guild_options["seperate_mm"]:
                enthusiasm = user_options["enthusiasm"].title()
            if guild_options["seperate_mm_roles"]:
                enthusiasm = player_role.name.title()

            if mongodb.getGuildMM(interaction.guild.id, user_options["region"], enthusiasm.lower()):
                return await interaction.edit_original_response(content=f"⛔ Another mm for {user_options['region']} {enthusiasm} is already running.")

            # Log matchmaking start
            self.bot.logger.info(f"{interaction.user.name} starting {user_options['region']} {enthusiasm} mm in {interaction.guild.name}")

            # Get channels
            _, matchmakingChannels, matchesChannel, _, auditlogChannel = await self.bot.getChannels(interaction.guild)
            matchmakingChannel = get_mm_channel_for_region(matchmakingChannels, user_options["region"])

            if not matchmakingChannel:
                return await interaction.edit_original_response(content=f"⛔ {user_options['region']} mm channel does not exist in this server.")

            if not matchesChannel:
                return await interaction.edit_original_response(content="⛔ #matches-running channel does not exist in this server.")

            # Start matchmaking
            mongodb.setGuildMM(interaction.guild.id, user_options["region"], enthusiasm.lower())
            await interaction.edit_original_response(content="🚀 Starting mm...")

            # Create and send matchmaking embed
            embed = discord.Embed(title=title, description=f"⚔️ **Players Ready:** 1/6\nMake sure to have used `/save_id` to participate.", color=discord.Color.blurple())
            anonymous_queues = guild_options["anonymous_queues"]
            if not anonymous_queues:
                embed.add_field(name="Players waiting", value=interaction.user.mention)

            roles = await self.bot.getRoles(interaction.guild, True)
            regionPing = get_role_for_ping_and_region(roles, user_options["region"], True)

            await delete_mm_embed(matchmakingChannel, enthusiasm)
            await matchmakingChannel.send(regionPing.mention, embed=embed,
                view=MatchmakingView(
                    self.bot, team_code, matchesChannel, matchmakingChannel, auditlogChannel, interaction.user,
                    user_options["region"], enthusiasm, player_role, anonymous_queues, user_options["elo"], None
                )
            )

            await interaction.edit_original_response(content=f"Matchmaking started in {matchmakingChannel.mention}")

    except Exception as e:
        self.bot.logger.error(f"Error in matchmaking command: {e}")
        await interaction.edit_original_response(content=f"❌ An error occurred: {e}. Please try again later")

  @matchmaking.error
  async def matchmaking_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("matchmaking",interaction,error)
     
    
  @guild_only
  @app_commands.command(description="Starts private matchmaking with a private key.")
  async def private_mm(self, interaction: discord.Interaction, team_code: str, private_key: str):
      await interaction.response.defer(ephemeral=True)

      async with self.mm_lock:
          # Validate the private key
          private_room = mongodb.findPrivate(private_key, str(interaction.guild.id))
          if not private_room:
              return await interaction.followup.send(content="⛔ Invalid private key. No such private room exists.", ephemeral=True)

          # Time-based matchmaking restrictions
          now = datetime.datetime.now(pytz.timezone("Europe/Berlin"))
          if now.replace(hour=21, minute=30, second=0, microsecond=0) <= now < now.replace(hour=22, minute=0, second=0, microsecond=0):
              return await interaction.edit_original_response(content=f"⛔ Matchmaking is closed. Bot is restarting in {60 - now.minute} Minutes!")
          
          if now.replace(hour=22, minute=0, second=0, microsecond=0) <= now < now.replace(hour=22, minute=5, second=0, microsecond=0):
              return await interaction.edit_original_response(content=f"⛔ Bot just restarted. Matchmaking will open in {5 - now.minute} Minutes!")

          if not validators.url(f"https://link.brawlstars.com/invite/gameroom/en?tag={team_code.upper()}"):
            return await interaction.edit_original_response(content=f"⛔ Invalid Team Code!")

          
          # Nutzer Id fetchen
          user_options = mongodb.findUserOptions(interaction.user.id, interaction.guild.id)
          guild_options = mongodb.findGuildOptions(interaction.guild.id)
      
          if not user_options["bs_id"]:
            return await interaction.edit_original_response(content="🖊️ Make sure to `/save_id` before using this command!")
          
          if user_options["in_match"] and user_options.get("in_match") > datetime.datetime.now():
            return await interaction.edit_original_response(content="⛔ Finish and evaluate your running match before starting a new one!")
      
          if "timeout" in user_options:
              if pytz.timezone(guild_options["tz"]).localize(user_options["timeout"]) > datetime.datetime.now(pytz.timezone(guild_options["tz"])):
                  return await interaction.edit_original_response(content=f"⛔ You have been timed out. You can resume playing at: {user_options['timeout'].strftime('%d.%m.%Y, %H:%M')}.")
          
          if "roles_timeout" in guild_options:
            for role in interaction.user.roles:
              if role.id in guild_options["roles_timeout"]:
                  return await interaction.edit_original_response(content=f"⛔ Your role {role.mention} has been timed out. This role can resume playing at: {user_options['timeout'].strftime('%d.%m.%Y, %H:%M')}.")
                
          lock = mongodb.getLock()
          if lock and "reason" in lock:
            return await interaction.edit_original_response(content=f"⛔ Matchmaking is locked for maintenance right now.\nReason: `{lock['reason']}`")
          
          # Ensure no existing matchmaking for this private room
          existing_mm = mongodb.getGuildMM(interaction.guild.id, private_room["private_key"], "private")
          if existing_mm:
              return await interaction.followup.send(content="⛔ Matchmaking for this private room is already running.", ephemeral=True)

          # Announce matchmaking start
          title = f"🏆 {private_room['name'].title()} Lobby 🏆"
          self.bot.logger.info(f"{interaction.user.name} started private matchmaking for room '{private_room['name']}' with key '{private_key}'.")

      
          # Get the matchmaking channel
          _, matchmakingChannels, matchesChannel, _, auditlogChannel = await self.bot.getChannels(interaction.guild)
          matchmakingChannel = get_mm_channel_for_region(matchmakingChannels, user_options["region"])
          
          if not matchmakingChannel:
                  return await interaction.edit_original_response(content=f"⛔ {user_options['region']} mm channel does not exist in this server.")

          if not matchesChannel:
              return await interaction.edit_original_response(content="⛔ #matches-running channel does not exist in this server.")

          # Save matchmaking details to the database
          mongodb.setGuildMM(interaction.guild.id, user_options["region"], private_key)

          embed = discord.Embed(
              title=title,
              description=f"⚔️ **Players Ready:** 1/6\nThis is a private Lobby. Use `/private_join` to register using the private key.",
              color=discord.Color.blurple()
          )
          anonymous_queues = guild_options["anonymous_queues"]
          if not anonymous_queues:
            embed.add_field(name="Players waiting", value=interaction.user.mention)


          await matchmakingChannel.send(embed=embed, view=MatchmakingView(self.bot, team_code, matchesChannel, matchmakingChannel, auditlogChannel, interaction.user,
                                        user_options["region"], private_room["name"], None, anonymous_queues, user_options["elo"], private_key))
          await interaction.edit_original_response(content=f"✅ Private matchmaking started in {matchmakingChannel.mention}.")

  @private_mm.error
  async def private_mm_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
      await self.__handle_error("private_mm", interaction, error)
        
        
         
  @guild_only
  @app_commands.command(description="forces result if automatic detection fails")
  async def set_result(self, interaction: discord.Interaction, match_id: str, winner: Literal["team1 🔵", "team2 🔴"], score: Literal["2-1", "2-0"]):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    await interaction.response.defer()
    
    async with self.bot.validation_lock:    
      match = mongodb.findMatch(match_id)
      if not match:
          return await interaction.edit_original_response(content="Match Id was not found.")
        
      if match["validated"]:
          return await interaction.edit_original_response(content="Match has already been evaluated.")

      matchCount = 2 if score == "2-0" else 3
      
      if winner == "team1 🔵":
        winning_team, losing_team = match["team1"], match["team2"]
      else:
        winning_team, losing_team = match["team2"], match["team1"]

      self.bot.logger.info(f"Match {match_id}: Winning Team: {winning_team}, Losing Team: {losing_team}")
      match["team1"], match["team2"] = refreshElos(match["team1"], match["team2"], interaction.guild.id)
      elos_before_evaluation = [player["elo"] for player in match["team1"] + match["team2"]]
      self.bot.logger.debug(f"Elos before Evaluation of Match #{match_id} on Map {match['bs_map']} in {interaction.guild.name}:\n\t{elos_before_evaluation}")

      
      guild_options = mongodb.findGuildOptions(interaction.guild.id)
      bonusfactor = 2 if datetime.datetime.now(pytz.timezone(guild_options["tz"])).weekday() in [5, 6] and guild_options["doublePointsWeekend"] else 1
      bonusfactorNegativeEloPlayers = 2 if datetime.datetime.now(pytz.timezone(guild_options["tz"])).weekday() in [5, 6] and guild_options["doublePointsWeekendNegativeElo"] else 1
      
        
      if guild_options["ranks"]:
          handle_points_rank_system(winning_team, losing_team, match_id, 0.5 if match["private"] else 1)
      else:
          handle_points_point_system(matchCount, winning_team, losing_team, bonusfactor, bonusfactorNegativeEloPlayers, match_id, 0.5 if match["private"] else 1)

      match["validated"] = True
      match["winner"] = winning_team
      mongodb.saveMatch(match)
      
      # ELO Updates string erstellen
      eloupdateText = ""
      # Refresh the team elos before using them for audit log
      for i, player in enumerate(match["team1"] + match["team2"]):
          self.bot.logger.debug(f"Elo change für {player['bs_id']}: {elos_before_evaluation[i]}, {player['elo']}. #{match_id} - {match['bs_map']} - {interaction.guild.name}")
          elo_change = player["elo"] - elos_before_evaluation[i]
          eloupdateText += f"<@{player['discord_id']}> {'+' if elo_change > 0 else ''}{elo_change} ({elos_before_evaluation[i]} -> {player['elo']})\n"

      _, _, _, _, auditlogChannel = await self.bot.getChannels(interaction.guild)
      
      if auditlogChannel:
          await auditlogChannel.send(embed=discord.Embed(title=f"Match #{match_id} on map {match['bs_map']} was validated on Command /set_result and here are the elo updates:", description=eloupdateText, color=discord.Color.green()))
      
      await interaction.edit_original_response(content="✅ Match validated", view=None)

  @set_result.error
  async def set_result_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("set_result",interaction,error)

  
  @guild_only
  @app_commands.command(description="validates a match incase button doesn't respond")
  async def validate_result(self, interaction: discord.Interaction, match_id: str):
    await interaction.response.defer()
    
    async with self.bot.validation_lock:    
      match = mongodb.findMatch(match_id)
      if not match:
          return await interaction.edit_original_response(content="Match Id was not found.")
        
      if match["validated"]:
          return await interaction.edit_original_response(content="Match has already been evaluated.")
        
      if not interaction.user.id in [player["discord_id"] for player in match["team1"] + match["team2"]] and not ((str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) and not str(interaction.user.id) in self.bot.blockedAdmins):
          return await interaction.edit_original_response(content="You are not part of this match.")

      # Ergebnisprüfung
      battle_log = await fetchBattleLog(match["team1"][0]["bs_id"])
      if not battle_log:
          self.bot.logger.debug(f"Fetching battle log for Team 1 Player BS ID failed {match['team1'][0]['bs_id']}.")
          return await interaction.edit_original_response(content=f"Could not fetch the battle log for <@{match['team1'][0]['discord_id']}> with BS ID: `{match['team1'][0]['bs_id']}`.")

      match["team1"], match["team2"] = refreshElos(match["team1"], match["team2"], interaction.guild.id)
      elos_before_evaluation = [player["elo"] for player in match["team1"] + match["team2"]]
      self.bot.logger.debug(f"Elos before Evaluation of Match #{match_id} on Map {match['bs_map']} in {interaction.guild.name}:\n\t{elos_before_evaluation}")
      match_date = match["match_date"]
          
      winning_team, _, not_founds = evaluate_winner(battle_log, match["team1"], match["team2"], match["bs_map"], self.bot.logger, match_id, match_date, interaction.guild_id, match["private"])

      if not winning_team:
          if not_founds:
              not_founds_text = ""
              for user in not_founds:
                  not_founds_text += f"\n<@{user['discord_id']}> with BS ID: #{user['bs_id']}"
              self.bot.logger.debug(f"Map `{match['bs_map']}` found but the following players where not found.\n{not_founds_text}")
              return await interaction.edit_original_response(content=f"Map `{match['bs_map']}` found but the following players where not found.\n{not_founds_text}\n\nPlease save your correct id: `/save_id`")
          return await interaction.edit_original_response(content=f"Match with the registered players and map `{match['bs_map']}` was not found in the battle log.")
        
          
      # ELO Updates string erstellen
      eloupdateText = ""
      # Refresh the team elos before using them for audit log
      for i, player in enumerate(match["team1"] + match["team2"]):
          self.bot.logger.debug(f"Elo change für {player['bs_id']}: {elos_before_evaluation[i]}, {player['elo']}. #{match_id} - {match['bs_map']} - {interaction.guild.name}")
          elo_change = player["elo"] - elos_before_evaluation[i]
          eloupdateText += f"<@{player['discord_id']}> {'+' if elo_change > 0 else ''}{elo_change} ({elos_before_evaluation[i]} -> {player['elo']})\n"

      
      _, _, _, _, auditlogChannel = await self.bot.getChannels(interaction.guild)
      
      if auditlogChannel:
          await auditlogChannel.send(embed=discord.Embed(title=f"Match #{match_id} on map {match['bs_map']} was validated on Command /validate_result and here are the elo updates:", description=eloupdateText, color=discord.Color.green()))
            
      match["validated"] = True
      match["winner"] = winning_team
      mongodb.saveMatch(match)
      await interaction.edit_original_response(content="✅ Match validated", view=None)
      

  @validate_result.error
  async def validate_result_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("validate_result",interaction,error)

      
  
  @app_commands.command(description="Join a private room using the given private key.")
  async def private_join(self, interaction: discord.Interaction, private_key: str):
      await interaction.response.defer(ephemeral=True)

      private_room = mongodb.findPrivate(private_key, str(interaction.guild.id))
      if not private_room:
          return await interaction.followup.send(content="⛔ No private room found with the provided key.", ephemeral=True)

      if "members" not in private_room:
          private_room["members"] = []
      if interaction.user.id not in private_room["members"]:
          private_room["members"].append(interaction.user.id)
          if not mongodb.savePrivate(private_room):  # Save updated room data
              return await interaction.followup.send(content="❌ Failed to join the private room. Please try again.", ephemeral=True)
          else:
            await interaction.followup.send(content=f"✅ You have successfully joined the private room: `{private_room['name']}`.", ephemeral=True)
               
      # Send a success message to the user
      await interaction.followup.send(content=f"✅ You are already in this private room: `{private_room['name']}`.", ephemeral=True)

  @private_join.error
  async def private_join_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
    await self.__handle_error("private_join",interaction,error)
      
      
  @guild_only
  @app_commands.command(description="save your id (#) for result tracking")
  async def save_id(self, interaction: discord.Interaction, bs_id: str, region: Literal["EMEA", "NA", "SA", "APAC"], ping: Literal["ping 🔔", "no ping 🔕"]):
    await interaction.response.defer(ephemeral=True)
    user_options = mongodb.findUserOptions(interaction.user.id, interaction.guild.id)
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
 
    player, bs_id, wartung = getPlayerForBsId(bs_id)
    if wartung:
      return await interaction.edit_original_response(content=f"Brawl Stars API in Maintenance, try registering later!")
      
    if not player:
      await interaction.edit_original_response(content=f"Invalid ID: {bs_id}!")
    else:
      if guild_options["seperate_mm"]:
        if player['highestTrophies'] >= guild_options["minimum_trophies"] and player["3vs3Victories"] >= guild_options["minimum_3v3_wins"]:
          user_options["enthusiasm"] = "tryhard"
        else:
          user_options["enthusiasm"] = "casual"
        
      user_options["bs_id"] = bs_id 
      user_options["guild_id"] = interaction.guild_id      
      user_options["region"] = region 
      mongodb.saveUser(user_options)
      is_pinged = True if "ping 🔔" == ping else False
      roles = await self.bot.getRoles(interaction.guild, True)
      role = get_role_for_ping_and_region(roles, region, is_pinged)
      if role:
        try:
          await interaction.user.add_roles(role)
        except discord.errors.Forbidden:
          return await interaction.edit_original_response(content=f"ID: `{bs_id}` and Region `{region}` saved, but I don't have permissions to edit your roles. Make sure my top_role is above your top_role ⚠️")
          
        role_to_remove = get_role_for_ping_and_region(roles, region, not is_pinged)
        await interaction.user.remove_roles(role_to_remove)
        await interaction.edit_original_response(content=f"ID: `{bs_id}` and Region `{region}` with `{ping}` saved ✅")
      else:
        await interaction.edit_original_response(content=f"ID: `{bs_id}` and Region `{region}` saved, but I don't have permissions to create roles ⚠️")
        
  @save_id.error
  async def save_id_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("save_id_error",interaction,error)
    
        
        
  @guild_only
  @app_commands.command(description="delete a user from leaderboard")
  async def add_user(self, interaction: discord.Interaction, user: discord.Member, bs_id: str, region: Literal["EMEA", "NA", "SA", "APAC"], ping: Literal["ping 🔔", "no ping 🔕"]):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    await interaction.response.defer(ephemeral=True)
    user_options = mongodb.findUserOptions(user.id, interaction.guild.id)
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    
    player, bs_id, wartung = getPlayerForBsId(bs_id)
    if wartung:
      return await interaction.edit_original_response(content=f"Brawl Stars API in Maintenance, try registering later!")
    
    if not player:
      await interaction.edit_original_response(content=f"Invalid ID: {bs_id}!")
    
    else:
      if guild_options["seperate_mm"]:
        if player['highestTrophies'] >= guild_options["minimum_trophies"] and player["3vs3Victories"] >= guild_options["minimum_3v3_wins"]:
          user_options["enthusiasm"] = "tryhard"
        else:
          user_options["enthusiasm"] = "casual"
        
      user_options["bs_id"] = bs_id 
      user_options["guild_id"] = interaction.guild_id
      user_options["region"] = region        
      mongodb.saveUser(user_options)
      is_pinged = True if "ping 🔔" == ping else False
      roles = await self.bot.getRoles(interaction.guild, True)
      role = get_role_for_ping_and_region(roles, region, is_pinged)
      if role:
        try:
          await user.add_roles(role)
        except discord.errors.Forbidden:
          return await interaction.edit_original_response(content=f"ID: `{bs_id}` and Region `{region}` saved, but I don't have permissions to edit {user.mention}'s roles. Make sure my top_role is above user's top_role ⚠️")
        
        role_to_remove = get_role_for_ping_and_region(roles, region, not is_pinged)
        await user.remove_roles(role_to_remove)
        await interaction.edit_original_response(content=f"ID: `{bs_id}` and Region `{region}` with `{ping}` saved for user {user.mention} ✅", ephemeral=True)
      else:
        await interaction.edit_original_response(content=f"ID: `{bs_id}` and Region `{region}` saved, but I don't have permissions to create roles ⚠️")

  @add_user.error
  async def add_user_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("add_user",interaction,error)
     
     
     
  @guild_only
  @app_commands.command(description="delete a users account data")
  async def delete_user(self, interaction: discord.Interaction, user_to_delete: discord.Member = None, id_of_user_to_delete: int = None):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    await interaction.response.defer(ephemeral=True)
    
    if user_to_delete:
      deleted = mongodb.deleteUserByDiscordId(user_to_delete.id, interaction.guild.id)
      if deleted:
          return await interaction.edit_original_response(content=f"✅ Successfully deleted {user_to_delete.display_name} from leaderboard!")
      else:
          return await interaction.edit_original_response(content=f"⚠️ {user_to_delete.display_name} is not registered!")
    if id_of_user_to_delete:
      deleted = mongodb.deleteUserByDiscordId(id_of_user_to_delete, interaction.guild.id)
      if deleted:
          return await interaction.edit_original_response(content=f"✅ Successfully deleted user with id *{id_of_user_to_delete}* from leaderboard!")
      else:
          return await interaction.edit_original_response(content=f"⚠️ User with id *{id_of_user_to_delete}* is not registered!")
    else:
      return await interaction.edit_original_response(content=f"⚠️ Provide a user or a user id to delete!")

  @delete_user.error
  async def delete_user_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("delete_user",interaction,error)
            
  
  @guild_only
  @app_commands.command(description="resets a users stats")
  async def reset_user_stats(self, interaction: discord.Interaction, user_to_delete: discord.Member = None, id_of_user_to_delete: int = None):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    await interaction.response.defer(ephemeral=True)
    
    if user_to_delete:
      user_data = mongodb.findUserOptions(user_to_delete.id, interaction.guild.id)
      mongodb.saveUser(resetPlayer(user_data))
      return await interaction.edit_original_response(content=f"✅ Successfully reset the stats for {user_to_delete.display_name}!")
    if id_of_user_to_delete:
      user_data = mongodb.findUserOptions(id_of_user_to_delete, interaction.guild.id)
      mongodb.saveUser(resetPlayer(user_data))
      return await interaction.edit_original_response(content=f"✅ Successfully reset the stats for user with id *{id_of_user_to_delete}*!")
    else:
      return await interaction.edit_original_response(content=f"⚠️ Provide a user or a user id to delete!")

  @reset_user_stats.error
  async def reset_user_stats_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("reset_user_stats",interaction,error)
     
    
  @guild_only
  @app_commands.command(description="manually add or subtract elo points")
  async def add_points(self, interaction: discord.Interaction, points: int, user: discord.Member, user2: discord.Member, user3: discord.Member):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    await interaction.response.defer()
    
    users = set()
    users.add(user)
    users.add(user2)
    users.add(user3)
    
    for user in users:
      user_data = mongodb.findUserOptions(user.id, interaction.guild.id)
      if user_data:
          user_data["elo"] += points
          mongodb.saveUser(user_data)
          points_added = "+" + str(points) if points >= 0 else str(points)
          await interaction.channel.send(content=f"✅ Successfully updated {user.display_name}'s points! `{points_added}`")
      else:
          return await interaction.channel.send(content=f"⚠️ {user.display_name} is not registered!")

    await interaction.edit_original_response(content=f"✅ Points updated")
    
    
  @add_points.error
  async def add_points_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("add_points",interaction,error)



  @guild_only
  @app_commands.command(description="manually add or subtract wins")
  async def add_wins(self, interaction: discord.Interaction, win_amount: int, user: discord.Member, user2: discord.Member, user3: discord.Member):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    await interaction.response.defer()
    
    users = set()
    users.add(user)
    users.add(user2)
    users.add(user3)
    
    for user in users:
      user_data = mongodb.findUserOptions(user.id, interaction.guild.id)
      if user_data:
          user_data["wins"] += win_amount
          mongodb.saveUser(user_data)
          wins_added = "+" + str(win_amount) if win_amount >= 0 else str(win_amount)
          await interaction.channel.send(content=f"✅ Successfully updated {user.display_name}'s wins! `{wins_added}`")
      else:
          return await interaction.channel.send(content=f"⚠️ {user.display_name} is not registered!")

    await interaction.edit_original_response(content=f"✅ Wins updated")
    
    
  @add_wins.error
  async def add_wins_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("add_wins",interaction,error)


  @guild_only
  @app_commands.command(description="manually add or subtract matches_played")
  async def add_matches_played(self, interaction: discord.Interaction, match_amount: int, user: discord.Member, user2: discord.Member, user3: discord.Member):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")
      
    await interaction.response.defer()
    
    users = set()
    users.add(user)
    users.add(user2)
    users.add(user3)
    
    for user in users:
      user_data = mongodb.findUserOptions(user.id, interaction.guild.id)
      if user_data:
          user_data["matches_played"] += match_amount
          mongodb.saveUser(user_data)
          matches_added = "+" + str(match_amount) if match_amount >= 0 else str(match_amount)
          await interaction.channel.send(content=f"✅ Successfully updated {user.display_name}'s matches played count! `{matches_added}`")
      else:
          return await interaction.channel.send(content=f"⚠️ {user.display_name} is not registered!")

    await interaction.edit_original_response(content=f"✅ Match counts updated")
    
    
  @add_matches_played.error
  async def add_matches_played_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("add_matches_played",interaction,error)
     
     
  @guild_only
  @app_commands.command(description="timeout a user from playing matchmaking.")
  async def timeout(self, interaction: discord.Interaction, end_date: str, user: discord.Member = None, role: discord.Role = None):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")      
      
    await interaction.response.defer(ephemeral=True)
    
    # Parse the timeout end date
    end_date_input = None
    try:
        end_date_input = datetime.datetime.strptime(end_date, "%d.%m.%Y, %H:%M")
    except ValueError:
        try:
            end_date_input = datetime.datetime.strptime(end_date, "%d.%m.%Y")
        except ValueError:
            await interaction.edit_original_response(content=f"Invalid date format. Please use DD.MM.YYYY, HH:MM or DD.MM.YYYY")
            return

    if end_date_input is None:
        await interaction.edit_original_response(content=f"Invalid date format. Please use DD.MM.YYYY, HH:MM or DD.MM.YYYY")
        return
            
    if user:
      user_data = mongodb.findUserOptions(user.id, interaction.guild.id)

    
      if user_data:
          user_data["timeout"] = end_date_input
          mongodb.saveUser(user_data)
          return await interaction.edit_original_response(content=f"✅ {user.display_name} timed out until: `{end_date}`.")
        
      else:
          return await interaction.edit_original_response(content=f"⚠️ {user.display_name} is not registered!")
    elif role:
      guild_options = mongodb.findGuildOptions(interaction.guild.id)
      
      if not 'roles_timeout' in guild_options:
        guild_options['roles_timeout'] = []
      guild_options['roles_timeout'].append(role.id)
      mongodb.saveGuild(guild_options)
      return await interaction.edit_original_response(content=f"✅ {role.mention} timed out until: `{end_date}`.")
    else:
      return await interaction.edit_original_response(content=f"⚠️ Provide a user or a role to timeout!")
      
      
  @timeout.error
  async def timeout_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("timeout",interaction,error)



  @guild_only
  @app_commands.command(description="removes a timeout for user.")
  async def remove_timeout(self, interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.response.send_message(content=f"⛔ You are not allowed to use this command.")      
      
    await interaction.response.defer()
    
    if user:
      user_data = mongodb.findUserOptions(user.id, interaction.guild.id)
      if user_data:
          user_data["timeout"] = datetime.datetime.now() - datetime.timedelta(days=1)
          mongodb.saveUser(user_data)
          return await interaction.edit_original_response(content=f"✅ {user.display_name} not on timeout anymore.")
      else:
          return await interaction.edit_original_response(content=f"⚠️ {user.display_name} is not registered!")
    elif role:
      guild_options = mongodb.findGuildOptions(interaction.guild.id)
      if not 'roles_timeout' in guild_options:
        guild_options['roles_timeout'] = []
      if role.id in guild_options['roles_timeout']:
        guild_options['roles_timeout'].remove(role.id)
      mongodb.saveGuild(guild_options)
      return await interaction.edit_original_response(content=f"✅ {role.mention} not on timeout anymore.")
    else:
      return await interaction.edit_original_response(content=f"⚠️ Provide a user or a role to remove from timeout!")
      
  
  @remove_timeout.error
  async def remove_timeout_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("remove_timeout",interaction,error)
     
    
   
    
  @guild_only
  @app_commands.command(description="Deletes running matchmaking and allows starting a new one.")
  async def delete_mm(self, interaction: discord.Interaction, region: Literal["EMEA", "NA", "SA", "APAC"]):
    await interaction.response.defer(ephemeral=True)

    # Überprüfen, ob der Benutzer berechtigt ist
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.edit_original_response(content="⛔ You are not allowed to use this command.")

    guild_options = mongodb.findGuildOptions(interaction.guild.id)

    # Optionen sammeln
    roles = []
    if guild_options["seperate_mm_roles"]:
        roles = [{"name": interaction.guild.get_role(role_id).name, "id": role_id} for role_id in guild_options["mm_roles"]]
    elif guild_options["seperate_mm"]:
        roles = [{"name": "Tryhard", "id": "tryhard"}, {"name": "Casual", "id": "casual"}]
    else:
        return await delete_mm(self.bot, interaction, region, "Overall")
   
    # Dropdown-Menü anzeigen
    viewItems = [SelectRoleToDeleteMM(bot=self.bot, roles=roles, region=region, originalInteraction=interaction)]
    await interaction.edit_original_response(content="Please select a role to delete matchmaking for:", view=View(viewItems))
    

  @delete_mm.error
  async def delete_mm_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("delete_mm",interaction,error)
     
 
  @guild_only
  @app_commands.command(description="set tryhard/casual role for a user.")
  async def enthusiasm_change(self, interaction: discord.Interaction, user: discord.Member, enthusiasm: Literal["tryhard", "casual"]):
    await interaction.response.defer()
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.edit_original_response(content=f"⛔ You are not allowed to use this command.")
      
        
    user_data = mongodb.findUserOptions(user.id, interaction.guild.id)
    if user_data:
        user_data["enthusiasm"] = enthusiasm
        mongodb.saveUser(user_data)
        return await interaction.edit_original_response(content=f"✅ {user.display_name} is now a {enthusiasm}.")
    else:
        return await interaction.edit_original_response(content=f"⚠️ {user.display_name} is not registered!")

    
  @enthusiasm_change.error
  async def enthusiasm_change_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("enthusiasm_change",interaction,error)
     
       
  @guild_only
  @app_commands.command(description="removes a user from in match status.")
  async def remove_from_match_status(self, interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer()
    
    if not (str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) or str(interaction.user.id) in self.bot.blockedAdmins:
        return await interaction.edit_original_response(content=f"⛔ You are not allowed to use this command.")
        
    user_data = mongodb.findUserOptions(user.id, interaction.guild.id)
    if user_data:
        user_data["in_match"] = False
        mongodb.saveUser(user_data)
        return await interaction.edit_original_response(content=f"✅ {user.display_name} not in match anymore.")
    else:
        return await interaction.edit_original_response(content=f"⚠️ {user.display_name} is not registered!")

    
  @remove_from_match_status.error
  async def remove_from_match_status_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("remove_from_match_status",interaction,error)
     


  @guild_only
  @app_commands.command(description="view a users stats.")
  async def check_stats(self, interaction: discord.Interaction, user: discord.Member):
    user_data = mongodb.findUserOptions(user.id, interaction.guild.id) 
    guild_options = mongodb.findGuildOptions(interaction.guild.id)
    
    if not user_data["bs_id"]:
      not_registered_embed = discord.Embed(
        description=(f"### {user.mention}\nThis user has no registered BS ID"),
        color=discord.Color.red()
      )
      return await interaction.response.send_message(embed=not_registered_embed, ephemeral=True)
    
    in_match = 'Yes' if user_data['in_match'] and user_data["in_match"] > datetime.datetime.now() else 'No'
    winrate = round((user_data["wins"] / user_data["matches_played"]) * 100, 2) if user_data["matches_played"] else 0
    user_stats_embed = discord.Embed(
        description=(f"### {user.mention}\nElo: {user_data['elo']}\nMatches Played: {user_data['matches_played']}\nCurrently In Match: {in_match}"
                    + f"\nWinstreak: {user_data['winstreak']}\nWins: {user_data['wins']}\nWinrate: {winrate}%"),
        color=discord.Color.gold()
    )
    if guild_options["seperate_mm"]:
      if "enthusiasm" in user_data:
        user_stats_embed.add_field(name="Enthusiasm", value=user_data['enthusiasm'], inline=False)
        
    if guild_options["ranks"]:
      rank = user_data["rank"] if "rank" in user_data else "Bronze 1"
      user_stats_embed.add_field(name="Rank", value=rank, inline=False)
        
    user_stats_embed.add_field(name="Region", value=user_data['region'], inline=False)
    user_stats_embed.add_field(name="BS ID", value=f"#{user_data['bs_id']}", inline=False)
    
    privates_text = ""
    for private in mongodb.getAllPrivates(str(interaction.guild.id)):
      if "members" in private and user.id in private["members"]:
        privates_text += f"{private['name']} - Expires: {private['expiration_date'].strftime('%d.%m.%Y, %H:%M')}\n"
        
    if privates_text:
        user_stats_embed.add_field(name="Private Lobby Access", value=privates_text, inline=False)
      
    if "timeout" in user_data:
        user_stats_embed.add_field(name="On Timeout", value=f"You can resume playing at: {user_data['timeout'].strftime('%d.%m.%Y, %H:%M')}.", inline=False)
          
    if user.avatar:
        user_stats_embed.set_author(name="player stats", icon_url=user.avatar.url)
    else:
        user_stats_embed.set_author(name="player stats", icon_url="https://cdn.discordapp.com/embed/avatars/0.png")
        
    return await interaction.response.send_message(embed=user_stats_embed)

  @check_stats.error
  async def check_stats_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("check_stats",interaction,error)
             
       
async def setup(bot):
  await bot.add_cog(Commands(bot))
