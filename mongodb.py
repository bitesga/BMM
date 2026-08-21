import base64
import hashlib
import os
from typing import Any

from cryptography.fernet import Fernet
from pymongo import MongoClient
from utils import loadEnv
from datetime import datetime


def _get_encryption_key() -> str | None:
    """Return a Fernet-compatible key from env vars. Accepts a raw string or an existing base64 key."""
    key = None
    for key_name in ("APP_ENCRYPTION_KEY", "MONGO_ENCRYPTION_KEY", "ENCRYPTION_KEY"):
        key = os.getenv(key_name) or envData.get(key_name)
        if key:
            break

    if not key:
        return None

    try:
        base64.urlsafe_b64decode(key.encode() + b"=")
        return key
    except Exception:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")


def _get_cipher() -> Fernet | None:
    key = _get_encryption_key()
    if not key:
        return None
    try:
        return Fernet(key)
    except Exception:
        return None


def _encrypt_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    cipher = _get_cipher()
    if cipher is None or not isinstance(value, str):
        return value
    try:
        return "enc:" + cipher.encrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return value


def _decrypt_value(value: Any) -> Any:
    if not isinstance(value, str) or not value.startswith("enc:"):
        return value
    cipher = _get_cipher()
    if cipher is None:
        return value
    try:
        return cipher.decrypt(value[4:].encode("utf-8")).decode("utf-8")
    except Exception:
        return value


def _encrypt_nested_fields(obj: Any, sensitive_fields: set[str]) -> Any:
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in sensitive_fields:
                result[key] = _encrypt_value(value)
            else:
                result[key] = _encrypt_nested_fields(value, sensitive_fields)
        return result
    if isinstance(obj, list):
        return [_encrypt_nested_fields(item, sensitive_fields) for item in obj]
    return obj


def _decrypt_nested_fields(obj: Any, sensitive_fields: set[str]) -> Any:
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in sensitive_fields:
                result[key] = _decrypt_value(value)
            else:
                result[key] = _decrypt_nested_fields(value, sensitive_fields)
        return result
    if isinstance(obj, list):
        return [_decrypt_nested_fields(item, sensitive_fields) for item in obj]
    return obj


envData = loadEnv()
# Verbindung zur MongoDB-Instanz herstellen
client = MongoClient(
    'localhost',
    27017,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
    socketTimeoutMS=5000,
)

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
        print(f"Error saving user {guild_options['guild_id']}: {e}")
        return False  # Fehler


def findGuildOptions(guild_id):
    try:
        guild_data = guilds.find_one({"guild_id": guild_id})
        if guild_data is None:
            return {
                "guild_id": guild_id, "tz": "Europe/Berlin", "removed_maps": [], "added_maps": [], "threads": False,
                "top3_last_season": [], "doublePointsWeekend": False, "season" : "", "next_reset" : "", "downward_joins" : False,
                "seperate_mm": False, "seperate_mm_roles" : False, "anonymous_queues" : True, "ranks": False,
                "doublePointsWeekendNegativeElo": False, "eloBoundary" : 200, "lb_limit" : 100, "lb_all_roles" : True, "cooldown_mm" : 0
            }
        return guild_data
    except Exception as e:
        print(f"Error finding guild {guild_id}: {e}")
        return None
    
    
# Match Options
def saveMatch(match):
    try:
        match["created_at"] = datetime.now()  # Setze das Erstellungsdatum
        match = _encrypt_nested_fields(match, {"bs_id"})
        matches.update_one({"match_id": match["match_id"]}, {"$set": match}, upsert=True)
        return True  # Erfolg
    except Exception as e:
        print(f"Error saving user {match.get('guild_id')}: {e}")
        return False  # Fehler


def findMatch(match_id):
    try:
        match = matches.find_one({"match_id": match_id})
        if match is None:
            return None
        return _decrypt_nested_fields(match, {"bs_id"})
    except Exception as e:
        print(f"Error finding match {match_id}: {e}")
        return None
 
 
def savePrivate(room):
    """Save private room details to the database."""
    try:
        room["created_at"] = datetime.now()
        privates.update_one({"private_key": room["private_key"]}, {"$set": room}, upsert=True)
        return True
    except Exception as e:
        print(f"Error saving private room {room['private_key']}: {e}")
        return False

def findPrivate(private_key, guild_id):
    """Find a private room by its key."""
    try:
        return privates.find_one({"private_key": private_key, "guild_id" : guild_id})
    except Exception as e:
        print(f"Error finding private room with key {private_key} and guild_id {guild_id}: {e}")
        return None


def getAllPrivates(guild_id):
    """Returns all Privates for a guild."""
    try:
        return list(privates.find({"guild_id" : guild_id}))
    except Exception as e:
        print(f"Error finding private rooms for guild_id {guild_id}: {e}")
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
        payload = _encrypt_nested_fields(user_options, {"bs_id"})
        users.update_one({"discord_id": user_options["discord_id"], "guild_id": user_options["guild_id"]}, {"$set": payload}, upsert=True)
        return True  # Erfolg
    except Exception as e:
        print(f"Error saving user {user_options['discord_id']}: {e}")
        return False  # Fehler


def findUserOptions(discord_id, guild_id):
    try:
        user = users.find_one({"discord_id": discord_id, "guild_id": guild_id})
        if user is None:
            return {
                "discord_id": discord_id, "guild_id": guild_id, "bs_id": None, "region" : None, "elo": 0, "matches_played": 0,
                "in_match": False, "winstreak": 0, "wins": 0, "rank" : None
            }
        return _decrypt_nested_fields(user, {"bs_id"})
    except Exception as e:
        print(f"Error finding user {discord_id}: {e}")
        return None


def findGuildUsers(guild_id):
    try:
        return users.find({"guild_id": guild_id})
    except Exception as e:
        print(f"Error finding guild by guild_id {guild_id}: {e}")
        return None
   
def getTop3Global(guild_id):
    try:
        return list(users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id}).sort("elo", -1).limit(3))
    except Exception as e:
        print(f"Error fetching top players for guild {guild_id}: {e}")
        return []
    
    
def getTopEloPlayers(guild_id, region, role_id=None, enthusiasm=None, limit=1000):
    try:
        guild_options = findGuildOptions(guild_id)
        if guild_options["seperate_mm"]:
            cursor = users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id, "region": region, "enthusiasm": enthusiasm}).sort("elo", -1)
        elif guild_options["seperate_mm_roles"]:
            cursor = users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id, "region": region, "role": str(role_id)}).sort("elo", -1)
        else:
            cursor = users.find({"matches_played": {"$ne": 0}, "guild_id": guild_id, "region": region}).sort("elo", -1)

        if limit is not None:
            cursor = cursor.limit(limit)

        return list(cursor)
    except Exception as e:
        print(f"Error fetching top players for guild {guild_id}: {e}")
        return []

def deleteUserByDiscordId(discord_id, guild_id):
    try:
        return users.delete_one({"discord_id": discord_id, "guild_id": guild_id}).deleted_count > 0
    except Exception as e:
        print(f"Error deleting user {discord_id}: {e}")
        return False

       
def resetInMatchAndLockedStatus():
    users.update_many({}, {"$set": {"in_match": False}})
    guildMMs.delete_many({})
        
if __name__ == "__main__": 
    pass
