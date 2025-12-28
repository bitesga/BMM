import os, discord, json
from discord.ext import commands, tasks
import asyncio
from mongodb import resetInMatchAndLockedStatus, findGuildOptions, saveGuild
from datetime import datetime
import pytz
from utils import logger, loadEnv

      
class BMM(commands.Bot):
  
  
  def __init__(self, intents):
    super().__init__(command_prefix="----------", intents=intents, activity=discord.Activity(type=discord.ActivityType.playing, name="Discord PL!"))
    self.logger = logger
    # Load admins set
    with open("admins.json", "r", encoding="UTF-8") as f:
        admins = json.load(f)
    self.admins = admins
    # Load blocked admins set
    with open("blockedAdmins.json", "r", encoding="UTF-8") as f:
        blockedAdmins = json.load(f)
    self.blockedAdmins = blockedAdmins
    # Load whitelisted servers
    with open("allowed.json", "r", encoding="UTF-8") as f:
        allowedGuilds = json.load(f)
    self.allowedGuilds = allowedGuilds
    self.validation_lock = asyncio.Lock()


  def getOverwrite(self, guild, role1, role2):
    return {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        role1: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        role2: discord.PermissionOverwrite(read_messages=True, send_messages=False),
    }
    
  
  async def getRoles(self, guild: discord.Guild, create=True):
    guild_options = findGuildOptions(guild.id)

    roles = {}
    # Überprüfe vorhandene Rollen basierend auf gespeicherten IDs
    for region in ["EMEA", "NA", "SA", "APAC"]:
        for ping_type in ["ping", "no_ping"]:
            key = f"{region}_{ping_type}"
            role_id = guild_options.get(key)
            roles[key] = guild.get_role(role_id) if role_id else None

    # Wenn Rollen erstellt werden sollen
    if create:
        for region in ["EMEA", "NA", "SA", "APAC"]:
            for ping_type, mentionable in [("ping", True), ("no_ping", False)]:
                key = f"{region}_{ping_type}"
                emoji = "🔔" if mentionable else "🔕"

                if not roles[key]:  # Rolle existiert nicht
                    try:
                        role = await guild.create_role(name=f"{emoji} {region}", mentionable=mentionable)
                        guild_options[key] = role.id
                        roles[key] = role
                    except Exception as e:
                        self.logger.warning(f"Failed to create role {key}: {str(e)}")

        # Speichere die aktualisierten guild_options
        saveGuild(guild_options)

    # Gib die Rollen zurück
    return [roles.get(f"EMEA_ping"), roles.get(f"EMEA_no_ping"), roles.get(f"NA_ping"), roles.get(f"NA_no_ping"),
            roles.get(f"SA_ping"), roles.get(f"SA_no_ping"), roles.get(f"APAC_ping"), roles.get(f"APAC_no_ping"),]
  
        
  async def getChannels(self, guild: discord.Guild, create=False):    
    guild_options = findGuildOptions(guild.id)
    
    
    # Only Read permission definieren
    onlyRead = {
      guild.default_role: discord.PermissionOverwrite(send_messages=False),
      self.user: discord.PermissionOverwrite(send_messages=True)
    }
    
    # Kategorie finden
    matchmakingCategory = discord.utils.get(guild.categories, id=guild_options.get("matchmakingCategory"))

    # Channels suchen
    announcementChannel = guild.get_channel(guild_options.get("bot-announcements"))
    hostMatchChannel = guild.get_channel(guild_options.get("pl-bot-chat"))
    emea_mm_channel = guild.get_channel(guild_options.get("emea-mm"))
    na_mm_channel = guild.get_channel(guild_options.get("na-mm"))
    sa_mm_channel = guild.get_channel(guild_options.get("sa-mm"))
    apac_mm_channel = guild.get_channel(guild_options.get("apac-mm"))
    matchesChannel = guild.get_channel(guild_options.get("matches-running"))
    leaderboardChannel = guild.get_channel(guild_options.get("leaderboard"))
    issuesReportChannel = guild.get_channel(guild_options.get("issue-report"))
    auditlogChannel = guild.get_channel(guild_options.get("audit-log"))
    tutorialChannel = guild.get_channel(guild_options.get("how-to-play"))

         
    if create: 
      emea_ping_role, emea_no_ping_role, na_ping_role, na_no_ping_role, sa_ping_role, sa_no_ping_role, apac_ping_role, apac_no_ping_role = tuple(await self.getRoles(guild, True))
      
      guild_options = findGuildOptions(guild.id)
    
      if not matchmakingCategory:
        matchmakingCategory = await guild.create_category_channel("Matchmaking")
        guild_options["matchmakingCategory"] = matchmakingCategory.id
      if not announcementChannel:
        announcementChannel = await matchmakingCategory.create_text_channel("bot-announcements", overwrites=onlyRead, topic="Current Infos about Maintenances, Bugs, New Features!")
        guild_options["bot-announcements"] = announcementChannel.id
      if not hostMatchChannel:
        hostMatchChannel = await matchmakingCategory.create_text_channel("pl-bot-chat", topic="Run your pl commands here")
        await hostMatchChannel.send("Run your commands here.")
        guild_options["pl-bot-chat"] = hostMatchChannel.id
        
      if not emea_mm_channel:
        emea_mm_channel = await matchmakingCategory.create_text_channel("emea-mm", overwrites=self.getOverwrite(guild, emea_ping_role, emea_no_ping_role), topic="join matchmaking here")
        if not emea_ping_role or not emea_no_ping_role:
          await emea_mm_channel.send("Could not create or set the EMEA roles to see this channel.")
        guild_options["emea-mm"] = emea_mm_channel.id
      if not na_mm_channel:
        na_mm_channel = await matchmakingCategory.create_text_channel("na-mm", overwrites=self.getOverwrite(guild, na_ping_role, na_no_ping_role), topic="join matchmaking here")
        if not na_ping_role or not na_no_ping_role:
          await na_mm_channel.send("Could not create or set the NA roles to see this channel.")
        guild_options["na-mm"] = na_mm_channel.id
      if not sa_mm_channel:
        sa_mm_channel = await matchmakingCategory.create_text_channel("sa-mm", overwrites=self.getOverwrite(guild, sa_ping_role, sa_no_ping_role), topic="join matchmaking here")
        if not sa_ping_role or not sa_no_ping_role:
          await sa_mm_channel.send("Could not create or set the SA roles to see this channel.")
        guild_options["sa-mm"] = sa_mm_channel.id
      if not apac_mm_channel:
        apac_mm_channel = await matchmakingCategory.create_text_channel("apac-mm", overwrites=self.getOverwrite(guild, apac_ping_role, apac_no_ping_role), topic="join matchmaking here")
        if not apac_ping_role or not apac_no_ping_role:
          await apac_mm_channel.send("Could not create or set the APAC roles to see this channel.")
        guild_options["apac-mm"] = apac_mm_channel.id
        
      if not matchesChannel:
        matchesChannel = await matchmakingCategory.create_text_channel("matches-running", overwrites=onlyRead, topic="view running matches and join your lobby")
        guild_options["matches-running"] = matchesChannel.id
      if not leaderboardChannel:
        leaderboardChannel = await matchmakingCategory.create_text_channel("leaderboard", overwrites=onlyRead, topic="check the leaderboard to post your search")
        guild_options["leaderboard"] = leaderboardChannel.id
      if not issuesReportChannel:
        issuesReportChannel = await matchmakingCategory.create_text_channel("issue-report", topic="post any problems here")
        await issuesReportChannel.send("Report any problems here.")
        guild_options["issue-report"] = issuesReportChannel.id
      if not auditlogChannel:
        auditlogChannel = await matchmakingCategory.create_text_channel("audit-log", overwrites=onlyRead, topic="review changes here")
        await auditlogChannel.send("Results and Elo changes will be displayed here.")
        guild_options["audit-log"] = auditlogChannel.id
        
      
      if not tutorialChannel:
        tutorialChannel = await matchmakingCategory.create_text_channel("how-to-play", overwrites=onlyRead, topic="Tutorial to get you going!")
        await self._create_tutorial(matchesChannel, tutorialChannel, hostMatchChannel)
        guild_options["how-to-play"] = tutorialChannel.id
      
      saveGuild(guild_options)

    return announcementChannel, [emea_mm_channel, na_mm_channel, sa_mm_channel, apac_mm_channel], matchesChannel, leaderboardChannel, auditlogChannel
  
  
  async def _create_tutorial(self, matchesChannel, tutorialChannel, hostMatchChannel):
    image_folder = "tutorialPhotos/" 
    tutorial_message = (
          "This is the **How to Play** channel! \n\n"
          "This is where you’ll find instructions for interacting with the Brawl Matchmaking bot. "
          
      )
    await tutorialChannel.send(tutorial_message)

    save_id_message = (
          "## **Step 1: register.**\n"
          "This is done by saving your ID with the /save_id [yourID] [region] [ping] command, as demostrated below. Set your region and toggle your ping role, by using this command."
      )
    
    await tutorialChannel.send(
    content=save_id_message,
    file=discord.File(f"{image_folder}save_id.png")
    )

    mm_message = (
          "## **Step 2: start or join matchmaking**\n"
          "If no matches are currently running, you can start a new one with the /matchmaking [team code] command.\n"
          f"Create a friendly room in Brawl Stars, copy the room code, and enter it as an argument into the command. Please use this command in {hostMatchChannel.mention}.\n"
          "This will start a new matchmaking queue."
      )

    await tutorialChannel.send(
    content=mm_message,
    file=discord.File(f"{image_folder}start_mm.png")
    )

    mm_message2 = (
          f"Optionally, you can join a running match from the matches in the mm channels.\n"
      )
    
    await tutorialChannel.send(
    content=mm_message2,
    file=discord.File(f"{image_folder}matchmaking.png")
    )

    match_message = (
          "## **Step 3: join your lobby**\n"
          f"Once the lobby is full, all the information about your match will be posted in {matchesChannel.mention}, and you will be mentioned.\n"
          "Please join the lobby assigned to you with the \"Join Lobby\" button. Make sure the lobby is playing the correct map and is in draft mode.\n"
          "Then, play out your match."
      )
    
    await tutorialChannel.send(
    content=match_message,
    file=discord.File(f"{image_folder}match.png")
    )

    val_message = (
          "## **Step 4: validate your match**\n"
          f"Once the match is finished, please click on the \"Check Result\" button in {matchesChannel.mention}.\n"
          "After the bot has validated that your match has been played out, you will be awarded or subtracted ELO, and the match is over.\n"
      )
    
    await tutorialChannel.send(
    content=val_message,
    file=discord.File(f"{image_folder}matchvalidation.png")
    )

    val_message = (
          "## **Step 5: repeat!**\n"
          "We hope you have fun playing the Brawl Matchmaking. Good luck in your matches!"
      )
    await tutorialChannel.send(val_message)


  async def delete_all_roles(self, guild: discord.Guild, guild_options):
    roles = await self.getRoles(guild, True)
    for role in roles:
      if role:
        await role.delete()

    for role_key in ["EMEA_ping", "EMEA_no_ping", "NA_ping", "NA_no_ping", "SA_ping", "SA_no_ping", "APAC_ping", "APAC_no_ping"]:
        if role_key in guild_options:
            del guild_options[role_key]
    return guild_options

      
  async def delete_all_channels(self, guild: discord.Guild, guild_options):
    for channel_name in ["bot-announcements", "pl-bot-chat", "emea-mm", "na-mm", "sa-mm", "apac-mm", "matches-running", "leaderboard", "issue-report", "audit-log", "how-to-play"]:
        if channel_name in guild_options:
          channel = guild.get_channel(guild_options[channel_name])
          if channel:
            await channel.delete()
          del guild_options[channel_name]

    if "matchmakingCategory" in guild_options:
      matchmakingCategory = discord.utils.get(guild.categories, id=guild_options.get("matchmakingCategory"))
      if matchmakingCategory:
        await matchmakingCategory.delete()
      del guild_options["matchmakingCategory"]
    return guild_options
    

  async def on_ready(self):
    self.logger.info("Bot rasiert alles")
    for f in os.listdir('./cogs'):
      if f.endswith('.py'):
        await bot.load_extension(f'cogs.{f[:-3]}')
    await self.tree.sync()
        
    self.leave_guilds.start()  # Task direkt beim Initialisieren starten
    self.refresh_admins.start()
    self.refresh_blocked_admins.start()
    resetInMatchAndLockedStatus()

    
    now = datetime.now(pytz.timezone("Europe/Berlin"))
    for guild in self.guilds:
      try:
        _, matchmakingChannels, matchesChannel, _, _ = await self.getChannels(guild)
          
        for mmch in matchmakingChannels:
          if mmch:
            await mmch.purge(limit=10, check=lambda m: True)
            if now.hour == 22:
              await mmch.send("I am back for new matchmakings 🚀")
        if matchesChannel:
          history = [message async for message in matchesChannel.history(limit=1)]
          last_message = history[0] if history else None  # Get the most recent message
          if now.hour == 22 and not last_message or last_message and not "Excited for upcoming matches" in last_message.content:
              await matchesChannel.send("Excited for upcoming matches <a:Elmofire:1324453688164487219>")
      except discord.errors.Forbidden:
        self.logger.warning(f"No permission to clean server {guild.name}")
      except Exception as e:
        self.logger.warning(f"Unknown error cleaning {guild.name}: {str(e)}")
            
    
  
  # Refresh the list of allowed guilds every minute and leave not wled ones
  @tasks.loop(minutes=1)
  async def leave_guilds(self):
    
    with open("allowed.json", "r", encoding="UTF-8") as f:
        allowedGuilds = json.load(f)
    self.allowedGuilds = allowedGuilds
    
    for guild in self.guilds:
      if not str(guild.id) in self.allowedGuilds:
        await guild.leave()
        self.logger.info(f"Left unauthorized server: {guild.name}") 
     
  
  # Refresh the list of admins every minute
  @tasks.loop(minutes=1)
  async def refresh_admins(self):
    self.logger.info("starting admin refresh")
      
    with open("admins.json", "r", encoding="UTF-8") as f:
        admins = json.load(f)
    self.admins = admins
    self.logger.info("admin list refreshed")
    
  
  # Refresh the list of blocked admins every minute
  @tasks.loop(minutes=1)
  async def refresh_blocked_admins(self):
    self.logger.info("starting blocked admin refresh")
      
    with open("blockedAdmins.json", "r", encoding="UTF-8") as f:
        blockedAdmins = json.load(f)
    self.blockedAdmins = blockedAdmins
    self.logger.info("blocked admin list refreshed")
    
    
  # Leave Guilds on Join or create the channels
  async def on_guild_join(self, guild: discord.Guild):
    with open("allowed.json", "r", encoding="UTF-8") as f:
        allowedGuilds = json.load(f)    
    self.allowedGuilds = allowedGuilds
    
    generalChannel = self.getGeneralChannel(guild)
    if not str(guild.id) in self.allowedGuilds:
      await generalChannel.send("This server did not buy this bot. Visit https://discord.gg/txfCgDfDDf to see the prices and contact the support. Until then, bye 👋")
      self.logger.info(f"Left unauthorized server: {guild.name}") 
      await guild.leave()
      return 
    
    await asyncio.sleep(3)
      
    await generalChannel.send("Hi, please make sure to put my role 'Brawl Matchmaking' as high as possible in the role list, so that I can edit member roles.",
    file=discord.File(f"tutorialPhotos/rolelist.png"))
    
    await asyncio.sleep(3)
      
    # Matchmaking Kanäle erstellen 
    await self.getChannels(guild, create=True)


  def getGeneralChannel(self, guild) -> discord.TextChannel:
    general_info_channel = None
    if guild.system_channel:
      general_info_channel = guild.system_channel
    if not general_info_channel:
      for text_channel in guild.text_channels:
        if "general" in text_channel.name:
          general_info_channel = text_channel
    if not general_info_channel:
      general_info_channel = guild.text_channels[0]
    return general_info_channel
     

intents = discord.Intents.all()
bot = BMM(intents=intents)
envData = loadEnv()
bot.run(envData['TOKEN'])
