import mongodb
import asyncio
import discord
import datetime
import pytz
import random

from utils import LinkButton, View
from views.ResultValidationView import ResultValidationView
from cogs.Maps import getCompetitiveMaps

globalMatchmakingLog = asyncio.Lock() 


async def safe_defer(interaction: discord.Interaction, ephemeral: bool = True):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
        return True
    except discord.NotFound:
        return False
    except Exception:
        return False


async def safe_followup(interaction: discord.Interaction, content: str, ephemeral: bool = True):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content=content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content=content, ephemeral=ephemeral)
        return True
    except Exception:
        return False
  
 
def get_mm_channel_for_region(channels, region):
  if region == "EMEA":
    return channels[0]
  if region == "NA":
    return channels[1]
  if region == "SA":
    return channels[2]
  else:
    return channels[3]
  
def get_role_for_ping_and_region(roles, region, mentionable=False):
  if region == "EMEA":
    return roles[0] if mentionable else roles[1]
  if region == "NA":
    return roles[2] if mentionable else roles[3]
  if region == "SA":
    return roles[4] if mentionable else roles[5]
  else:
    return roles[6] if mentionable else roles[7]

 
async def delete_mm_embed(channel: discord.TextChannel, enthusiasm: str):
  if enthusiasm == "Overall":
    enthusiasm = "Matchmaking"
  history = [message async for message in channel.history(limit=20)]
      
  for message in history:
    if message.embeds:
        if message.embeds[0].title:
          if message.embeds[0].title.lower() == f"🏆 {enthusiasm} Lobby 🏆".lower():
              await message.delete()

            
class MatchmakingView(discord.ui.View):
    def __init__(self, bot, team_code, matchesChannel, matchmakingChannel, auditlogChannel, host, region, enthusiasm, player_role, anonymous_queues, host_elo, private_key):
        super().__init__(timeout=600)
        self.bot = bot
        self.team_code = team_code
        self.host = host
        self.matchesChannel = matchesChannel
        self.started = False
        self.message = None
        self.matchmakingChannel = matchmakingChannel
        self.auditlogChannel = auditlogChannel
        self.lock = asyncio.Lock()  # Lock für Synchronisierung
        self.logger = bot.logger
        self.region = region
        self.enthusiasm = enthusiasm
        if self.enthusiasm == "Overall":
            self.lobby_name = "Matchmaking"
        else:
            self.lobby_name = self.enthusiasm
        self.lobby_role = player_role
        self.ready_users = [host]
        self.anonymous_queues = anonymous_queues
        self.host_elo = host_elo
        self.private_key = private_key
        

    async def update_embed(self, message: discord.Message):
        """
        Aktualisiere das Embed basierend auf der Anzahl der Spieler.
        """
            
        embed = discord.Embed(
            title=f"🏆 {self.lobby_name} Lobby 🏆",
            description=f"⚔️ **Players Ready:** {len(self.ready_users)}/6\nMake sure to have used `/save_id` to participate.",
            color=discord.Color.blurple()
        )
        if not self.anonymous_queues:
            embed.add_field(name="Players waiting", value=", ".join(user.mention for user in self.ready_users))

        try:
            await message.edit(embed=embed, view=self)
        except Exception as e:
            return self.logger.error(f"An error occurred while updating mm embed in {self.matchmakingChannel.guild.name}: {str(e)}")   
        

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        if not await safe_defer(interaction, ephemeral=True):
            return

        try:
            async with self.lock:  # Synchronisation starten
                if len(self.ready_users) >= 6:
                    return await safe_followup(interaction, content="⛔ The lobby is already full!", ephemeral=True)

                user_options = mongodb.findUserOptions(interaction.user.id, interaction.guild.id)
                guild_options = mongodb.findGuildOptions(interaction.guild.id)
                
                if "timeout" in user_options:
                    if pytz.timezone(guild_options["tz"]).localize(user_options["timeout"]) > datetime.datetime.now(pytz.timezone(guild_options["tz"])):
                        return await safe_followup(interaction, content=f"⛔ You have been timed out. You can resume playing at: {user_options['timeout'].strftime('%d.%m.%Y, %H:%M')}.", ephemeral=True)

                if "roles_timeout" in guild_options:
                    for role in interaction.user.roles:
                        if role.id in guild_options["roles_timeout"]:
                            return await safe_followup(
                                interaction,
                                content=f"⛔ Your role {role.mention} has been timed out. This role can resume playing at: {user_options['timeout'].strftime('%d.%m.%Y, %H:%M')} {guild_options['tz']} timezone.",
                                ephemeral=True)
        
                if not user_options or not user_options.get("bs_id"):
                    return await safe_followup(interaction, content="⛔ You need to save your ID using `/save_id` to join the lobby.", ephemeral=True)
            
            
                if self.private_key:
                    private_room = mongodb.findPrivate(self.private_key, str(interaction.guild.id))
                    if not private_room or "members" not in private_room or interaction.user.id not in private_room["members"]:
                        return await safe_followup(interaction, content="⛔ You need to join this private room using `/private_join` and the private key to join this lobby.", ephemeral=True)
                else:
                    if abs(user_options["elo"] - self.host_elo) > guild_options["eloBoundary"]:
                        if not (user_options["elo"] > self.host_elo and guild_options["downward_joins"]):
                            return await safe_followup(interaction, content=f"⛔ Your elo is more than {guild_options['eloBoundary']} points away from the host's elo, so you can't join this mm!", ephemeral=True)
                    
                    
                    if guild_options["seperate_mm"]:
                        if not "enthusiasm" in user_options:
                            return await safe_followup(interaction, content="⛔ Please `/save_id` to determine your enthusiasm level (tryhard/casual)!", ephemeral=True)
                    
                        if not user_options["enthusiasm"].title() == self.enthusiasm.title() and not (guild_options["downward_joins"] and user_options["enthusiasm"] == "tryhard"):
                            return await safe_followup(interaction, content=f"⛔ Your enthusiasm level is {user_options['enthusiasm']}, so you can not join this {self.enthusiasm} lobby!", ephemeral=True)
                
                    player_role = None 
                    if guild_options["seperate_mm_roles"]:
                        for role in reversed(interaction.user.roles):
                            if role.id in guild_options["mm_roles"]:
                                player_role = role
                                break
                        if not player_role:
                            return await safe_followup(interaction, content="⛔ Please ask an admin to get a skill level role!", ephemeral=True)
                        if guild_options["downward_joins"]:
                            if not player_role >= self.lobby_role:
                                return await safe_followup(interaction, content=f"⛔ Your role {player_role.mention} is below the lobby role {self.lobby_role.mention}, so you can not join!", ephemeral=True)
                        else:      
                            if not player_role == self.lobby_role:
                                return await safe_followup(interaction, content=f"⛔ Your role is {player_role.mention}, so you can not join this {self.lobby_role.mention} lobby!", ephemeral=True)
                
                if interaction.user in self.ready_users:
                    return await safe_followup(interaction, content="⛔ You are already in the lobby!", ephemeral=True)
                
                if user_options.get("in_match") and user_options.get("in_match") > datetime.datetime.now():
                    return await safe_followup(interaction, content=
                        "⛔ You can't join this matchmaking, as you are in a match already.", ephemeral=True
                    )
                
                self.ready_users.append(interaction.user)
                await self.update_embed(interaction.message)
                await safe_followup(interaction, content="✅ You joined the matchmaking lobby!", ephemeral=True)
            
                # Lobby voll -> Teams erstellen
                if len(self.ready_users) == 6:
                        if not self.started:  # Doppelte Prüfung innerhalb des Locks
                            self.started = True
                            async with globalMatchmakingLog:
                                return await self.start_matchmaking(self.matchesChannel, self.matchmakingChannel)
        except Exception as e:
            self.logger.error(f"Join button error in {self.matchmakingChannel.guild.name}: {str(e)}")
            await safe_followup(interaction, content="⛔ Something went wrong while joining. Please try again.", ephemeral=True)
                
            

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        if not await safe_defer(interaction, ephemeral=True):
            return
        if interaction.user not in self.ready_users:
            return await safe_followup(interaction, content="⛔ You are not in the lobby!", ephemeral=True)

        self.ready_users.remove(interaction.user)
        await self.update_embed(interaction.message)
        await safe_followup(interaction, content="✅ You left the matchmaking lobby.", ephemeral=True)
        
        if interaction.user == self.host:
            host_left_message = discord.Embed(
                title=f"🏆 {self.lobby_name} Lobby 🏆",
                description=f"**😞 Host left the Matchmaking 😞**\nStart a new matchmaking by using `/matchmaking`.",
                color=discord.Color.red()
            )
            mongodb.deleteGuildMM(self.matchesChannel.guild.id, self.region, self.enthusiasm.lower())
            
            if self.message:
                await self.message.edit(embed=host_left_message, view=None) 
            else:
                await delete_mm_embed(self.matchmakingChannel, self.enthusiasm)
                return await self.matchmakingChannel.send(embed=host_left_message)
            
            
        
      
      
    async def start_matchmaking(self, matchesChannel: discord.TextChannel, matchmakingChannel: discord.TextChannel):
        """
        Startet das Matchmaking, wenn die Lobby voll ist.
        """
        self.logger.info(f"Starting matchmaking in {matchesChannel.guild.name}...")

        mongodb.deleteGuildMM(matchesChannel.guild.id, self.region, self.enthusiasm.lower())
        guild_options = mongodb.findGuildOptions(matchesChannel.guild.id)

        for item in self.children:
            item.disabled = True

        ready_users = list(self.ready_users)
        
        def freeUsers(ready_users):
            for user in ready_users:
                user_info = mongodb.findUserOptions(user.id, matchesChannel.guild.id)
                user_info["in_match"] = False
                mongodb.saveUser(user_info)

        players = []
        for user in ready_users:
            user_info = mongodb.findUserOptions(user.id, matchesChannel.guild.id)
            if guild_options["seperate_mm_roles"]:
                user_info["role"] = str(self.lobby_role.id)
            user_info["in_match"] = datetime.datetime.now() + datetime.timedelta(minutes=10)
            mongodb.saveUser(user_info)
            players.append(user_info)

        # Create Random Teams
        random.shuffle(players)
        team1 = players[:3]
        team2 = players[3:]

        # Karte auswählen
        maps = await getCompetitiveMaps(self.bot, matchesChannel.guild.id)
        if not maps:
            no_maps_message = discord.Embed(
                title=f"🏆 {self.lobby_name} Lobby 🏆",
                description=f"**❓ Mappool is empty ❓**\nYour admin deleted all the maps from mappool.",
                color=discord.Color.red()
            )
            
            if self.message:
                return await self.message.edit(embed=no_maps_message, view=None) 
            else:
                await delete_mm_embed(self.matchmakingChannel, self.enthusiasm)
                return await matchmakingChannel.send(embed=no_maps_message)
        
        selected_map = random.choice(maps)

        # Thread erstellen oder Nachricht senden
        if guild_options["threads"]:       
            # Embed für Matchmaking-Abschluss
            matchmaking_completed_message = discord.Embed(
                title=f"🏆 {self.lobby_name} Lobby 🏆",
                description=f"**🚀 Matchmaking Completed 🚀**\nYour lobby is created as thread\nStart a new one by using `/matchmaking`.",
                color=discord.Color.green()
            )
            
            # Thread erstellen
            try:
                matchesChannel = await matchesChannel.create_thread(
                    name=f"Lobby - {self.host.display_name}",
                    type=discord.ChannelType.private_thread,
                    auto_archive_duration=60
                )
                self.logger.info(f"Thread created successfully: {matchesChannel.name} in guild {matchesChannel.guild.name}.")
            except Exception as e:
                self.logger.error(f"Failed to create thread in channel {matchesChannel.name}: {str(e)}")
                freeUsers(ready_users)
                return await matchmakingChannel.send("⛔ Failed to create thread channel")
            
            # Spieler zum Thread hinzufügen
            for user in ready_users:
                try:
                    await asyncio.sleep(2)
                    await matchesChannel.add_user(user)
                    self.logger.info(f"Added user {user.display_name} ({user.id}) to thread {matchesChannel.name}.")
                except Exception as e:
                    self.logger.error(f"Error adding user {user.id} ({user.display_name}) to thread {matchesChannel.name}: {str(e)}")
                    freeUsers(ready_users)
                    await matchesChannel.send(f"⛔ Error adding user {user.id} ({user.display_name}) to thread {matchesChannel.name}: {str(e)}")
        else:        
            # Embed für Matchmaking-Abschluss ohne Thread
            matchmaking_completed_message = discord.Embed(
                title=f"🏆 {self.lobby_name} Lobby 🏆",
                description=f"**🚀 Matchmaking Completed 🚀**\nYour lobby is in {matchesChannel.mention}\nStart a new one by using `/matchmaking`.",
                color=discord.Color.green()
            )
            self.logger.info(f"Matchmaking lobby will be managed in {matchesChannel.name}.")
            
        # Nachricht aktualisieren oder senden
        try:
            if self.message:
                await self.message.edit(embed=matchmaking_completed_message, view=None)
                self.logger.info(f"Updated existing matchmaking message in {matchesChannel.guild.name}.")
            else:
                await delete_mm_embed(self.matchmakingChannel, self.enthusiasm)
                await matchmakingChannel.send(embed=matchmaking_completed_message)
                self.logger.info(f"Sent new matchmaking completed message in {matchmakingChannel.guild.name}.")
        except discord.errors.NotFound:
            self.logger.warning("Message to edit was not found; sending a new message.")
            await delete_mm_embed(self.matchmakingChannel, self.enthusiasm)
            await matchmakingChannel.send(embed=matchmaking_completed_message)
        except Exception as e:
            self.logger.error(f"Error updating or sending matchmaking completion message: {str(e)}")

        # Ergebnisse posten
        try:
            matchmaking_string = f"## {selected_map}\n"
            team1_mentions = "\n🔵 ".join(matchesChannel.guild.get_member(user["discord_id"]).mention for user in team1)
            team2_mentions = "\n🔴 ".join(matchesChannel.guild.get_member(user["discord_id"]).mention  for user in team2)
            matchmaking_string += f"🔵 {team1_mentions}\n"
            matchmaking_string += f"🔴 {team2_mentions}"

            view_items = [
                LinkButton(self.team_code.upper(), f"https://link.brawlstars.com/invite/gameroom/en?tag={self.team_code.upper()}", "<:BrawlStar:1216305064231174185>")
            ]
            
            await asyncio.sleep(2)
            msg = await matchesChannel.send(matchmaking_string, view=View(view_items))
        except Exception as e:
            self.logger.error(f"An error occurred while sending matchmaking results in {matchesChannel.guild.name}: {str(e)}")
            freeUsers(ready_users)
            return await matchmakingChannel.send("⛔ An error occurred while posting the matchmaking results.")

        # Match speichern und Validierungsnachricht senden
        try:
            match_date = datetime.datetime.now(datetime.timezone.utc)
            mongodb.saveMatch({"match_id": str(msg.id), "team1": team1, "team2": team2, "bs_map": selected_map, "match_date": match_date, "validated": False, "private": self.private_key})
            message = await matchesChannel.send(
                embed=discord.Embed(
                    title=f"🏆 Match #{msg.id} Result Validation 🏆",
                    description=f"Click the button below to validate the match result.\nIn case the button does not react, use `/validate_result {msg.id}` or let an admin force a result by using `/set_result`\nResults must be submitted within 30 minutes.",
                    color=discord.Color.blurple()
                ),
                view=ResultValidationView(self.bot, team1, team2, selected_map, self.logger, msg.id, match_date, matchesChannel.guild.id, self.auditlogChannel, guild_options["threads"], self.private_key)
            )

            if guild_options["threads"]:
                await message.pin()
        except Exception as e:
            self.logger.error(f"An error occurred while saving match or sending result validation message: {str(e)}")
            freeUsers(ready_users)
            return await matchmakingChannel.send(f"⛔ An error occurred while saving match or sending result validation message: {str(e)}")

        

    async def on_timeout(self):
        """
        Funktion, die ausgeführt wird, wenn die Lobby nach Timeout geschlossen wird.
        """

        
        mongodb.deleteGuildMM(self.matchesChannel.guild.id, self.region, self.enthusiasm.lower())
    
        self.logger.info(f"Matchmaking in {self.matchesChannel.guild.name} {self.region} timed out with mm status {self.started} and ready players {len(self.ready_users)}")
        
        timeout_message = discord.Embed(
            title=f"🏆 {self.lobby_name} Lobby 🏆",
            description="**⏳ Matchmaking Timed Out ⏳**\nStart a new one by using `/matchmaking`.",
            color=discord.Color.red()
        )
        if self.message and not self.started:
            try:
                await self.message.edit(embed=timeout_message, view=None) 
            except:
                await delete_mm_embed(self.matchmakingChannel, self.enthusiasm)
                await self.matchmakingChannel.send(embed=timeout_message) 
            
        elif not self.started:
            await delete_mm_embed(self.matchmakingChannel, self.enthusiasm)
            await self.matchmakingChannel.send(embed=timeout_message) 
            
