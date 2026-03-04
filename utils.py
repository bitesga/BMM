import discord
from discord import app_commands
import requests
import json
import logging
import os
import re
import time

"""
Load correct env
"""
def currentFolder():
  # Aktuellen Ordner Basename extrahieren
  return os.path.basename(os.getcwd())

def loadEnv():
  env_file_name = "env.json" if currentFolder() == "BMM" else "envtest.json"
  
  # Env laden
  with open(f"data/{env_file_name}", "r") as f:
    envData = json.load(f)
  return envData
  
envData = loadEnv()


"""
Logging Setup
"""
logger = logging.getLogger(envData["LOGGER"])
logger.setLevel(logging.DEBUG)  # Mindestlevel für alle Handler

# Format für Logs
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# Stream-Handler (gibt Logs auf der Konsole aus)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Alle Logs (DEBUG, INFO, etc.) auf der Konsole
console_handler.setFormatter(formatter)

# Datei-Handler (schreibt Logs in Datei)
file_handler = logging.FileHandler(f"{envData['LOGGER']}.log")
file_handler.setLevel(logging.DEBUG)  # Alle Logs (DEBUG, INFO, etc.) auf der Konsole
file_handler.setFormatter(formatter)

# Handler dem Logger hinzufügen
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Helper-Funktionen
def simplify(name: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', name.upper())
  

def getPlayerForBsId(bs_id):
  bs_id = bs_id.upper().replace(" ", "").replace("#", "")
  url = f"https://api.brawlstars.com/v1/players/%23{bs_id}"
  headers = {
      "Authorization": f"Bearer {envData['BsApi']}"
  }
  try:
    response = requests.get(url, headers=headers, timeout=3).json()
  except:
    return None, bs_id, True
  if not "reason" in response:
      return response, bs_id, False
  elif response["reason"] == "inMaintenance":
      return None, bs_id, True
  else:
      return None, bs_id, False
    
      
async def fetchBattleLog(bs_id):
  bs_id = bs_id.replace("#", "")
  url = f"https://api.brawlstars.com/v1/players/%23{bs_id}/battlelog"
  headers = {
      "Authorization": f"Bearer {envData['BsApi']}"
  }
  response = requests.get(url, headers=headers)
  if response.status_code == 200:
      return response.json()["items"]

# -----------------------------------------------------------------------------------------------------------------------

# View Klasse zum Anzeigen der Items wie Buttons und Auswahllisten
class View(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=None)
        for item in items:
            self.add_item(item)

# LinkButton Klasse
class LinkButton(discord.ui.Button):
  def __init__(self, label, url, emoji=None):
    super().__init__(label=label, style=discord.ButtonStyle.link, url=url, emoji=emoji)


def dynamic_guild_cooldown(seconds: int = 15, bot_owner_id: int = 324607583841419276, use_matchmaking_setting: bool = False):
  cooldowns = {}

  async def predicate(interaction: discord.Interaction) -> bool:
    if interaction.user.id == bot_owner_id:
      return True

    cooldown_duration = seconds
    if use_matchmaking_setting and interaction.guild:
      import mongodb
      guild_options = mongodb.findGuildOptions(interaction.guild.id)
      if guild_options:
        cooldown_duration = guild_options.get("cooldown_mm", 120)

    guild_id = interaction.guild.id if interaction.guild else 0
    key = (guild_id, interaction.user.id)
    current_time = time.time()

    if key in cooldowns:
      time_passed = current_time - cooldowns[key]
      if time_passed < cooldown_duration:
        retry_after = cooldown_duration - time_passed
        raise app_commands.CommandOnCooldown(None, retry_after)

    cooldowns[key] = current_time
    return True

  return app_commands.check(predicate)