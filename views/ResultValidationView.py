import discord
import mongodb
import datetime
import pytz
import asyncio

from utils import simplify, fetchBattleLog
from elo_system.RankSystem import RankSystem

rank_system = RankSystem()


async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False):
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
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
        return True
    except Exception:
        return False


async def run_blocking(func, *args):
    return await asyncio.to_thread(func, *args)


def handle_points_rank_system(winning_team, losing_team, match_id, privatefactor):
    print(f"Match {match_id}: Applying rank system with privatefactor {privatefactor}")
    for player in winning_team:
        rank = rank_system.get_rank_by_points(player["elo"])
        print(f"Rank for {player['discord_id']}: {rank}")
        streak_bonus = rank.ws_bonus if player["winstreak"] > rank.wins_needed else 0
        player["elo"] += ((rank.win_plus + streak_bonus) * privatefactor)
        player["wins"] += 1
        player["winstreak"] += 1
        player["rank"] = rank_system.get_rank_by_points(player["elo"]).rank_name
        print(f"Winner {player['bs_id']} updated: +{((rank.win_plus + streak_bonus) * privatefactor)} elo, winstreak +1")
        player["in_match"] = False
        player["matches_played"] += 1
        mongodb.saveUser(player)

    for player in losing_team:
        rank = rank_system.get_rank_by_points(player["elo"])
        print(f"Rank for {player['discord_id']}: {rank}")
        player["elo"] += (rank.lose_minus * privatefactor)
        if player["elo"] < 0: player["elo"] = 0
        player["winstreak"] = 0
        player["rank"] = rank_system.get_rank_by_points(player["elo"]).rank_name
        print(f"Loser {player['bs_id']} updated: {(rank.lose_minus * privatefactor)} elo, winstreak reset")
        player["in_match"] = False
        player["matches_played"] += 1
        mongodb.saveUser(player)



def handle_points_point_system(matches, winning_team, losing_team, bonusfactor, bonusfactorNegativeEloPlayers, match_id, privatefactor):
    print(f"Match {match_id}: Applying point system with bonus factor: {bonusfactor}/{bonusfactorNegativeEloPlayers} and privatefactor {privatefactor}")

    if matches == 2:
        for player in winning_team:
            bonus = bonusfactor if player["elo"] >= 0 else bonusfactorNegativeEloPlayers
            player["elo"] += (19 * bonus * privatefactor)
            player["wins"] += 1
            player["winstreak"] += 1
            print(f"Match {match_id}: Winner {player['bs_id']} updated: +{19 * bonus * privatefactor} elo, winstreak +1")
            player["in_match"] = False
            player["matches_played"] += 1
            mongodb.saveUser(player)

        for player in losing_team:
            player["elo"] -= (20 * privatefactor)
            player["winstreak"] = 0
            print(f"Match {match_id}: Loser {player['bs_id']} updated: -{(20 * privatefactor)} elo, winstreak reset")
            player["in_match"] = False
            player["matches_played"] += 1
            mongodb.saveUser(player)
    elif matches == 3:
        for player in winning_team:
            bonus = bonusfactor if player["elo"] >= 0 else bonusfactorNegativeEloPlayers
            player["elo"] += (13 * bonus * privatefactor)
            player["wins"] += 1
            player["winstreak"] += 1
            print(f"Match {match_id}: Winner {player['bs_id']} updated: +{13 * bonus * privatefactor} elo, winstreak +1")
            player["in_match"] = False
            player["matches_played"] += 1
            mongodb.saveUser(player)

        for player in losing_team:
            player["elo"] -= (14 * privatefactor)
            player["winstreak"] = 0
            print(f"Match {match_id}: Loser {player['bs_id']} updated: -{(14 * privatefactor)} elo, winstreak reset")
            player["in_match"] = False
            player["matches_played"] += 1
            mongodb.saveUser(player)


def refreshElos(team1, team2, guild_id):
    for i in range(3):
        team1[i] = mongodb.findUserOptions(team1[i]["discord_id"], guild_id)
        
    for i in range(3):
        team2[i] = mongodb.findUserOptions(team2[i]["discord_id"], guild_id)
        
    return team1, team2
 
 
def check_player_in_match(user, battle_team):
    """
    Pr├╝ft, ob ein Spieler (BS-ID) in einem Team vorhanden ist.
    """
    user_tag = user["bs_id"].replace('#', '')
    for player in battle_team:
        if user_tag == player["tag"].replace('#', ''):
            return True
    return False


def is_valid_team(battle_teams, team1, team2, match_id, match_idx):
    """
    ├£berpr├╝ft die ├£bereinstimmung der Teams Spieler f├╝r Spieler und loggt fehlende Spieler.
    """
    team1_battle, team2_battle = battle_teams
    team1_count, team2_count = 0, 0
    not_founds = []

    # Pr├╝fe Team 1
    print(f"Match {match_id}: Verifying Team 1 in match {match_idx + 1}...")
    for user in team1:
        if not check_player_in_match(user, team1_battle):
            print(f"Match {match_id}: Player {user['bs_id']} not found in registered Team 1.")
            if not user in not_founds:
                not_founds.append(user)
        else:
            team1_count += 1

    # Pr├╝fe Team 2
    print(f"Match {match_id}: Verifying Team 2 in match {match_idx + 1}...")
    for user in team2:
        if not check_player_in_match(user, team2_battle):
            print(f"Match {match_id}: Player {user['bs_id']} not found in registered Team 2.")
            if not user in not_founds:
                not_founds.append(user)
        else:
            team2_count += 1

    return team1_count + team2_count >= 4, not_founds

       
def evaluate_winner(battle_log, team1, team2, bs_map, match_id, match_date, guild_id, private):
    team1_score = 0
    team2_score = 0
    valid_matches = []
    not_founds = []
    guild_options = mongodb.findGuildOptions(guild_id)
    
    # Refresh the team elos before adding new elos
    team1, team2 = refreshElos(team1, team2, guild_id)
    
    # Log initiales Team und Match-Setup
    print(f"Evaluating Winner for {'private' if private else 'public'} Match #{match_id} on Map {bs_map} in Guild {guild_id} at {match_date.isoformat()}")
    print(f"Initial Elos: {[player['elo'] for player in team1 + team2]}")
        
    for idx, match in enumerate(battle_log):
        if len(valid_matches) == 3:
            break
        
        print(f"Match {match_id}: Processing match: {match['event']} against map: {bs_map}")
        if not match["event"]["map"]: 
            continue

        # Check if the match is older than the matchmaking start date
        strftime_format = "%d/%m/%Y, %H:%M"
        battle_log_match_time = datetime.datetime.strptime(match["battleTime"], "%Y%m%dT%H%M%S.%fZ")
        if battle_log_match_time.replace(tzinfo=datetime.timezone.utc) < match_date.replace(tzinfo=datetime.timezone.utc):
            print(f"Match {match_id}: Match #{idx + 1} {battle_log_match_time.strftime(strftime_format)} is older than matchmaking start date {match_date.strftime(strftime_format)}. Stopping further search.")
            break
        
        print(f"Match {match_id}: Battle Log Match {battle_log_match_time.strftime(strftime_format)} is fresher than MM {match_date.strftime(strftime_format)}, continuing search...")
            
            
        if simplify(match["event"]["map"]) == simplify(bs_map):
            print(f"Match {match_id}: Map match found, verifying teams...")
            battle_teams = match["battle"]["teams"]
            
            print(f"Registered Team 1: {team1}")
            print(f"Registered Team 2: {team2}")
            print(f"Battle Log Teams: {match['battle']['teams']}")

            valid_team1, not_founds1 = is_valid_team(battle_teams, team1, team2, match_id, idx)
            valid_team2, not_founds2 = is_valid_team(battle_teams, team2, team1, match_id, idx)
            not_founds = not_founds1 if len(not_founds1) < len(not_founds2) else not_founds2
            if valid_team1 or valid_team2:
                if match["battle"]["result"] in ["victory", "defeat"]:
                    print(f"Match {match_id}: Valid match found: {match}")
                    valid_matches.append(match)
            else:
                if valid_matches:
                    print(f"Match {match_id}: Stopping further processing as valid matches are already found.")
                    break
        else:
            if valid_matches:
                print(f"Match {match_id}: Stopping further processing as valid matches are already found.")
                break
    
    
    print(f"Match {match_id}: Found {len(valid_matches)} valid matches.")
    
    if len(valid_matches) < 2:
        print(f"Match {match_id}: Not enough valid matches found.")
        return None, None, not_founds

    bonusfactor = 2 if datetime.datetime.now(pytz.timezone(guild_options["tz"])).weekday() in [5, 6] and guild_options["doublePointsWeekend"] else 1
    bonusfactorNegativeEloPlayers = 2 if datetime.datetime.now(pytz.timezone(guild_options["tz"])).weekday() in [5, 6] and guild_options["doublePointsWeekendNegativeElo"] else 1
    privatefactor = 0.5 if private else 1

    for match in valid_matches:
        if match["battle"]["result"] == "victory":
            team1_score += 1
        else:
            team2_score += 1
            
        if match["battle"]["starPlayer"]:
            star_player_tag = match["battle"]["starPlayer"]["tag"]
            print(f"Match {match_id}: Star player found: {star_player_tag}")
            for player in team1 + team2:
                if player["bs_id"].replace('#', '') == star_player_tag.replace('#', ''):
                    bonus = bonusfactor if player["elo"] >= 0 else bonusfactorNegativeEloPlayers
                    player["elo"] += (1 * bonus * privatefactor)
                    print(f"Match {match_id}: Starplayer {player['bs_id']} awarded {(1 * bonus * privatefactor)} bonus point (Total elo: {player['elo']})")
                    if (match["battle"]["result"] == "defeat" and player in team1) or (
                        match["battle"]["result"] == "victory" and player in team2):
                        player["elo"] += (2 * bonus * privatefactor)
                        print(f"Match {match_id}: Starplayer {player['bs_id']} in losing team awarded {(2 * bonus * privatefactor)} extra points (Total elo: {player['elo']})")
 
 
    if team1_score == 2:
        winning_team, losing_team = team1, team2
    elif team2_score == 2:
        winning_team, losing_team = team2, team1
    else: 
        return None, None, not_founds
        
    
    print(f"Match {match_id}: Winning Team: {winning_team}, Losing Team: {losing_team}")
    if guild_options["ranks"]:
        handle_points_rank_system(winning_team, losing_team, match_id, privatefactor)
    else:
        handle_points_point_system(len(valid_matches), winning_team, losing_team, bonusfactor, bonusfactorNegativeEloPlayers, match_id, privatefactor)


    return winning_team, losing_team, not_founds



class ResultValidationView(discord.ui.View):
    def __init__(self, bot, team1, team2, map, match_id, match_date, guild_id, auditlogChannel, thread, private_key):
        super().__init__(timeout=1800)  # Timeout f├╝r die View setzen
        self.bot = bot
        self.team1 = team1
        self.team2 = team2
        self.bs_map = map
        self.match_evaluated = False
        self.message = None
        self.users_voted_cancel = set()
        self.match_id = match_id
        self.match_date = match_date
        self.guild_id = guild_id
        self.auditlogChannel = auditlogChannel
        self.thread = thread
        self.private_key = private_key


    @discord.ui.button(label="Check Result", style=discord.ButtonStyle.green)
    async def check_result_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        if not await safe_defer(interaction):
            return
    
        async with self.bot.validation_lock:
            user_is_admin = str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator
            user_is_admin = user_is_admin and not str(interaction.user.id) in self.bot.blockedAdmins
            if not interaction.user.id in [player["discord_id"] for player in self.team1 + self.team2] and not user_is_admin:
                return await safe_followup(interaction, "You are not part of this match.", ephemeral=True)

            if self.match_evaluated:
                try:
                    return await safe_followup(interaction, "This match has already been evaluated.", ephemeral=True)
                except Exception as e:
                    return print(f"An error occurred on check result btn for Match #{self.match_id}: {str(e)}")
                    
                    
            try:
                match = await run_blocking(mongodb.findMatch, str(self.match_id))
                if match["validated"]:
                    self.match_evaluated = True

                    winning_team = match["winner"]
                    embed_validated = discord.Embed(
                        title=f"[OK] Match #{self.match_id} Result Validated",
                        description=f'Winners: <@{winning_team[0]["discord_id"]}> <@{winning_team[1]["discord_id"]}> <@{winning_team[2]["discord_id"]}>',
                        color=discord.Color.green()
                    )
                    await interaction.edit_original_response(embed=embed_validated, view=None)
                    
                    await safe_followup(interaction, "match has been evaluated by command.", ephemeral=True)
                    
                    if self.thread:
                        try:
                            await self.message.channel.send("Deleting thread channel in 30 seconds <a:loading:1324279901234397224>")
                            await asyncio.sleep(30)
                            await self.message.channel.delete()
                        except Exception as e:
                            print(f"An error occurred on deleting thread channel: {str(e)}")
                    return
            
            except Exception as e:
                print(f"An error occurred on check result btn for Match #{self.match_id}: {str(e)}")
                

            # Ergebnispr├╝fung
            battle_log = await fetchBattleLog(self.team1[0]["bs_id"])
            if not battle_log:
                print(f"Fetching battle log for Team 1 Player BS ID failed {self.team1[0]['bs_id']}.")
                return await safe_followup(interaction, f"Could not fetch the battle log for <@{self.team1[0]['discord_id']}> with BS ID: `{self.team1[0]['bs_id']}`.", ephemeral=True)

            self.team1, self.team2 = await run_blocking(refreshElos, self.team1, self.team2, interaction.guild.id)
            elos_before_evaluation = [player["elo"] for player in self.team1 + self.team2]
            print(f"Elos before Evaluation of Match #{self.match_id} on Map {self.bs_map} in {interaction.guild.name}:\n\t{elos_before_evaluation}")
            winning_team, _, not_founds = await run_blocking(
                evaluate_winner,
                battle_log,
                self.team1,
                self.team2,
                self.bs_map,
                self.match_id,
                self.match_date,
                interaction.guild_id,
                self.private_key,
            )

            if not winning_team:
                if not_founds:
                    not_founds_text = ""
                    for user in not_founds:
                        not_founds_text += f"\n<@{user['discord_id']}> with BS ID: #{user['bs_id']}"
                    print(f"Map `{self.bs_map}` found but the following players where not found.\n{not_founds_text}")
                    return await safe_followup(interaction, f"Map `{self.bs_map}` found but the following players where not found.\n{not_founds_text}\n\nPlease save your correct id: `/save_id`", ephemeral=True)
                return await safe_followup(interaction, f"Match with the registered players and map `{self.bs_map}` was not found in the battle log.", ephemeral=True)

            match["winner"] = winning_team
            match["validated"] = True
            await run_blocking(mongodb.saveMatch, match)
            
            # ELO Updates string erstellen
            eloupdateText = ""
            # Refresh the team elos before using them for audit log
            for i, player in enumerate(self.team1 + self.team2):
                print(f"Elo change f├╝r {player['bs_id']}: {elos_before_evaluation[i]}, {player['elo']}. #{self.match_id} - {self.bs_map} - {interaction.guild.name}")
                elo_change = player["elo"] - elos_before_evaluation[i]
                eloupdateText += f"<@{player['discord_id']}> {'+' if elo_change > 0 else ''}{elo_change} ({elos_before_evaluation[i]} -> {player['elo']})\n"

            if self.auditlogChannel:
                await self.auditlogChannel.send(embed=discord.Embed(title=f"Match #{self.match_id} on map {self.bs_map} was validated on Buttonclick and here are the elo updates:", description=eloupdateText, color=discord.Color.green()))
           
            self.match_evaluated = True
                
            embed_validated = discord.Embed(
                title=f"[OK] Match #{self.match_id} Result Validated",
                description=f'Winners: <@{winning_team[0]["discord_id"]}> <@{winning_team[1]["discord_id"]}> <@{winning_team[2]["discord_id"]}>',
                color=discord.Color.green()
            )
            
            if self.message:
                await self.message.edit(embed=embed_validated, view=None)
            
            if self.thread:
                try:
                    await self.message.channel.send("Deleting thread channel in a minute...")
                    await asyncio.sleep(60)
                    await self.message.channel.delete()
                except:
                    pass

   
    @discord.ui.button(label="Vote Cancel Match", style=discord.ButtonStyle.grey)
    async def vote_cancel_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message

        if not await safe_defer(interaction):
            return
        
        if not interaction.user.id in [player["discord_id"] for player in self.team1 + self.team2]:
            return await safe_followup(interaction, "You are not part of this match.", ephemeral=True)

        if self.match_evaluated:
            return await safe_followup(interaction, "This match has already been evaluated.", ephemeral=True)

        if interaction.user.id in self.users_voted_cancel:
            return await safe_followup(interaction, "You already voted for cancelling this match.", ephemeral=True)

        self.users_voted_cancel.add(interaction.user.id)

        embed = discord.Embed(
            title=f"Match #{self.match_id} Result Validation",
            description=f"Click the button below to validate the match result.\nResults must be submitted within 30 minutes.\nVotes for cancel: {len(self.users_voted_cancel)}/4",
            color=discord.Color.blurple()
        )
        await interaction.edit_original_response(embed=embed)
        
        # 4 Votes lead to match cancel
        if len(self.users_voted_cancel) >= 4:
            self.match_evaluated = True
            
            # Benutzer in der Datenbank aktualisieren
            for user in self.team1 + self.team2:
                user["in_match"] = False
                await run_blocking(mongodb.saveUser, user)

            self.match_evaluated = True
            embed_validated = discord.Embed(
                title=f"Match #{self.match_id} Cancelled",
                description="Players can join a new match now.",
            )
            
            await interaction.edit_original_response(embed=embed_validated, view=None)
            
            if self.thread:
                try:
                    await self.message.channel.send("Deleting thread channel in a minute <a:loading:1324279901234397224>")
                    await asyncio.sleep(60)
                    await self.message.channel.delete()
                except:
                    pass
    
        

    @discord.ui.button(label="Admin: Cancel Match", style=discord.ButtonStyle.red)
    async def cancel_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        
        if not await safe_defer(interaction):
            return
        
        if not ((str(interaction.user.id) in self.bot.admins or interaction.user.guild_permissions.administrator) and not str(interaction.user.id) in self.bot.blockedAdmins):
            return await safe_followup(interaction, "This button is reserved for admins.", ephemeral=True)

        # Benutzer in der Datenbank aktualisieren
        for user in self.team1 + self.team2:
            user["in_match"] = False
            await run_blocking(mongodb.saveUser, user)

        self.match_evaluated = True
        embed_validated = discord.Embed(
            title=f"Match #{self.match_id} Cancelled",
            description="Players can join a new match now.",
        )
        
        await interaction.edit_original_response(embed=embed_validated, view=None)
        
        if self.thread:
            try:
                await self.message.channel.send("Deleting thread channel in a minute <a:loading:1324279901234397224>")
                await asyncio.sleep(60)
                await self.message.channel.delete()
            except:
                pass

                  
        
    async def on_timeout(self):
        """
        Funktion, die ausgef├╝hrt wird, wenn der Button nach Timeout deaktiviert wird.
        """
        
        _, _, _, _, auditlogChannel = await self.bot.getChannels(self.bot.get_guild(self.guild_id))
        self.auditlogChannel = auditlogChannel
        
        # Logging: Start der Timeout-Funktion
        print(f"Starting timeout handler for Match #{self.match_id}.")
        
        try:
            match = await run_blocking(mongodb.findMatch, str(self.match_id))
            if match["validated"]:
                print(f"Match evaluated, updating embed #{self.match_id}.")
                self.match_evaluated = True

                winning_team = match["winner"]
                embed_validated = discord.Embed(
                    title=f"[OK] Match #{self.match_id} Result Validated",
                    description=f'Winners: <@{winning_team[0]["discord_id"]}> <@{winning_team[1]["discord_id"]}> <@{winning_team[2]["discord_id"]}>',
                    color=discord.Color.green()
                )
                
                if self.message:
                    await self.message.edit(embed=embed_validated, view=None)
                
                if self.thread and self.message:
                    print(f"deleting thread channel #{self.match_id}.")
                    try:
                        await self.message.channel.send("Deleting thread channel in 30 seconds <a:loading:1324279901234397224>")
                        await asyncio.sleep(30)
                        await self.message.channel.delete()
                    except Exception as e:
                        print(f"An error occurred on deleting thread channel: {str(e)}")
                return
        
        except Exception as e:
            print(f"An error occurred on check result btn for Match #{self.match_id}: {str(e)}")
                
                

        timeout_message = discord.Embed(
            title=f"Match #{self.match_id} Result Validation Timed Out",
            description="Result not validated. Start a new match and try again.",
            color=discord.Color.red()
        )


        if not self.match_evaluated:
            print(f"Match #{self.match_id} on map {self.bs_map} has not been evaluated yet. Proceeding with result validation.")
            
            # Ergebnispr├╝fung
            try:
                print(f"Fetching battle log for Team 1 Player BS ID: {self.team1[0]['bs_id']}.")
                battle_log = await fetchBattleLog(self.team1[0]["bs_id"])

                if not battle_log:
                    print(f"Battle log not found for Match #{self.match_id}. Sending timeout message.")
                    if self.message:
                        await self.message.edit(embed=timeout_message, view=None)
                       
                    if self.auditlogChannel: 
                        await self.auditlogChannel.send(embed=discord.Embed(title=f"Match #{self.match_id} on map {self.bs_map} validation timed out. No battle log found.",description="", color=discord.Color.yellow()))
                    return

                print(f"Evaluating winner for Match #{self.match_id}.")
                self.team1, self.team2 = await run_blocking(refreshElos, self.team1, self.team2, self.guild_id)
                elos_before_evaluation = [player["elo"] for player in self.team1 + self.team2]
                print(f"Elos davor {elos_before_evaluation}")
                winning_team, _, not_founds = await run_blocking(
                    evaluate_winner,
                    battle_log,
                    self.team1,
                    self.team2,
                    self.bs_map,
                    self.match_id,
                    self.match_date,
                    self.guild_id,
                    self.private_key,
                )

                if not winning_team:
                    if not_founds:
                        not_founds_text = ""
                        for user in not_founds:
                            not_founds_text += f"\n<@{user['discord_id']} with BS ID: #{user['bs_id']}"
                            print(f"Map `{self.bs_map}` was found but the following players where not found.\n{not_founds_text}")
                    else:
                        print(f"No winner found for Match #{self.match_id}. Sending timeout message.")
                    if self.message:
                        await self.message.edit(embed=timeout_message, view=None)

                    # Audit-Log f├╝r Timeout hinzuf├╝gen
                    if self.auditlogChannel:
                        return await self.auditlogChannel.send(embed=discord.Embed(title=f"Match #{self.match_id} validation timed out. No winner could be determined.",description=f"(The map {self.bs_map} could not be found)", color=discord.Color.yellow()))
                    

                # Erfolgreiche Validierung
                embed_validated = discord.Embed(
                    title=f"[OK] Match #{self.match_id} Result Validated",
                    description=f'Winners: <@{winning_team[0]["discord_id"]}> <@{winning_team[1]["discord_id"]}> <@{winning_team[2]["discord_id"]}>',
                    color=discord.Color.green()
                )
        
                print(f"Match #{self.match_id} successfully validated. Winners determined.")
                if self.message:
                    await self.message.edit(embed=embed_validated, view=None)

                # ELO Updates string erstellen
                eloupdateText = ""
                for i, player in enumerate(self.team1 + self.team2):
                    print(f"Elos jetzt {elos_before_evaluation[i]}, {player['elo']}")
                    elo_change = player["elo"] - elos_before_evaluation[i]
                    eloupdateText += f"<@{player['discord_id']}> {'+' if elo_change > 0 else ''}{elo_change} ({elos_before_evaluation[i]} -> {player['elo']})\n"

                if self.auditlogChannel:
                    await self.auditlogChannel.send(embed=discord.Embed(title=f"Match #{self.match_id} on map {self.bs_map} was validated on timeout and here are the elo updates:", description=eloupdateText, color=discord.Color.green()))
                

            except Exception as e:
                print(f"An error occurred during timeout handling for Match #{self.match_id}: {str(e)}")
                if self.message:
                    await self.message.edit(embed=timeout_message, view=None)

                # Audit-Log f├╝r Fehler
                if self.auditlogChannel:
                    await self.auditlogChannel.send(embed=discord.Embed(title=f"An error occurred during Match #{self.match_id} validation: {str(e)}", description="", color=discord.Color.red()))

        if self.thread and self.message:
            try:
                await self.message.channel.send("Deleting thread channel in a minute <a:loading:1324279901234397224>")
                await asyncio.sleep(60)
                await self.message.channel.delete()
            except:
                pass

