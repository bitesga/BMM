from pymongo import MongoClient
from utils import logger, loadEnv
from datetime import datetime


envData = loadEnv()
# Verbindung zur MongoDB-Instanz herstellen
client = MongoClient('localhost', 27017)

# Datenbank und Collections holen
bmmDB = client[envData["DB"]]

guilds = bmmDB["guilds"]
users = bmmDB["users"]
guildMMs = bmmDB["guildMMs"]
locks = bmmDB["locks"]
matches = bmmDB["matches"]
privates = bmmDB["privates"]

# TTL-Index für das created_at-Feld. Löscht matches nach 24h
matches.create_index([("created_at", 1)], expireAfterSeconds=24*3600) 

# TTL-Index für das created_at-Feld. Löscht matches nach 24h
privates.create_index([("created_at", 1)], expireAfterSeconds=24*3600) 

# Guild Options
def saveGuild(guild_options):
    try:
        guilds.update_one({"guild_id": guild_options["guild_id"]}, {"$set": guild_options}, upsert=True)
        return True  # Erfolg
    except Exception as e:
        logger.error(f"Error saving user {guild_options['guild_id']}: {e}")
        return False  # Fehler


def findGuildOptions(guild_id):
    try:
        return guilds.find_one({"guild_id": guild_id}) or {
            "guild_id": guild_id, "tz": "Europe/Berlin", "removed_maps": [], "added_maps": [], "threads": False,
            "top3_last_season": [], "doublePointsWeekend": False, "season" : "", "next_reset" : "", "downward_joins" : False,
            "seperate_mm": False, "seperate_mm_roles" : False, "anonymous_queues" : True, "ranks": False,
            "doublePointsWeekendNegativeElo": False, "eloBoundary" : 200, "lb_limit" : 100, "lb_all_roles" : True, "cooldown_mm" : 0
        }
    except Exception as e:
        logger.error(f"Error finding guild {guild_id}: {e}")
        return None
    
    
# Match Options
def saveMatch(match):
    try:
        match["created_at"] = datetime.now()  # Setze das Erstellungsdatum
        matches.update_one({"match_id": match["match_id"]}, {"$set": match}, upsert=True)
        return True  # Erfolg
    except Exception as e:
        logger.error(f"Error saving user {match['guild_id']}: {e}")
        return False  # Fehler


def findMatch(match_id):
    try:
        return matches.find_one({"match_id": match_id})
    except Exception as e:
        logger.error(f"Error finding match {match_id}: {e}")
        return None
 
 
def savePrivate(room):
    """Save private room details to the database."""
    try:
        room["created_at"] = datetime.now()
        privates.update_one({"private_key": room["private_key"]}, {"$set": room}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"Error saving private room {room['private_key']}: {e}")
        return False

def findPrivate(private_key, guild_id):
    """Find a private room by its key."""
    try:
        return privates.find_one({"private_key": private_key, "guild_id" : guild_id})
    except Exception as e:
        logger.error(f"Error finding private room with key {private_key} and guild_id {guild_id}: {e}")
        return None


def getAllPrivates(guild_id):
    """Returns all Privates for a guild."""
    try:
        return list(privates.find({"guild_id" : guild_id}))
    except Exception as e:
        logger.error(f"Error finding private rooms for guild_id {guild_id}: {e}")
        return None
    
    
# Guild Matchmaking: Only one allowed at a time
def getGuildMM(guild_id, region, role):
    return guildMMs.find_one({"guild_id": guild_id, "region": region, "role": role})

def setGuildMM(guild_id, region, role):
    guildMMs.insert_one({"guild_id": guild_id, "region": region, "role": role})

def deleteGuildMM(guild_id, region, role):
    return guildMMs.delete_many({"guild_id": guild_id, "region": region, "role": role}).deleted_count
    
  
# Matchmaking Lock
def getLock():
    return locks.find_one()
  
def setLock(reason: str):
    locks.delete_many({})
    locks.insert_one({"reason" : reason})

def deleteLock():
    locks.delete_many({})
    
# User Options
def saveUser(user_options):
    try:
        users.update_one({"discord_id": user_options["discord_id"], "guild_id": user_options["guild_id"]}, {"$set": user_options}, upsert=True)
        return True  # Erfolg
    except Exception as e:
        logger.error(f"Error saving user {user_options['discord_id']}: {e}")
        return False  # Fehler


def findUserOptions(discord_id, guild_id):
    try:
        return users.find_one({"discord_id": discord_id, "guild_id": guild_id}) or {
            "discord_id": discord_id, "guild_id": guild_id, "bs_id": None, "region" : None, "elo": 0, "matches_played": 0,
            "in_match": False, "winstreak": 0, "wins": 0, "rank" : None
        }
    except Exception as e:
        logger.error(f"Error finding user {discord_id}: {e}")
        return None


def findGuildUsers(guild_id):
    try:
        return users.find({"guild_id": guild_id})
    except Exception as e:
        logger.error(f"Error finding guild by guild_id {guild_id}: {e}")
        return None
   
def getTop3Global(guild_id):
    try:
        return list(users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id}).sort("elo", -1).limit(3))
    except Exception as e:
        logger.error(f"Error fetching top players for guild {guild_id}: {e}")
        return []
    
    
def getTopEloPlayers(guild_id, region, role_id=None, enthusiasm=None, limit=1000):
    try:
        guild_options = findGuildOptions(guild_id)
        if guild_options["seperate_mm"]:
            return list(users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id, "region": region, "enthusiasm": enthusiasm}).sort("elo", -1).limit(limit))
        elif guild_options["seperate_mm_roles"]:
            return list(users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id, "region": region, "role": str(role_id)}).sort("elo", -1).limit(limit))
        else:
            return list(users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id, "region": region}).sort("elo", -1).limit(limit))
    except Exception as e:
        logger.error(f"Error fetching top players for guild {guild_id}: {e}")
        return []

def deleteUserByDiscordId(discord_id, guild_id):
    try:
        return users.delete_one({"discord_id": discord_id, "guild_id": guild_id}).deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting user {discord_id}: {e}")
        return False

       
def resetInMatchAndLockedStatus():
    for user in users.find():
        user["in_match"] = False
        saveUser(user)
    
    guildMMs.drop()  
        
if __name__ == "__main__": 
    for guild in guilds.find():
        guild["cooldown_mm"] = 120
        saveGuild(guild)
        print(f"Updated guild {guild['guild_id']} with default cooldown_mm")
        print(guild)
