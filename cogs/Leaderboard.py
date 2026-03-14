# Füge das Last-Update-Embed hinzu
from datetime import datetime, timedelta
import json
import math
import asyncio

from discord.ext import commands
import discord
from discord import app_commands
from discord.app_commands import guild_only

import mongodb
import pytz

from utils import dynamic_guild_cooldown


with open("elosystems.json", "r", encoding="UTF-8") as f:
    elosystems = json.load(f)


REGIONS = ["EMEA", "SA", "NA", "APAC"]
ENTHUSIASM_OPTIONS = ["tryhard", "casual"]
PLAYERS_PER_EMBED = 25
MAX_PAGE_SIZE = 200


def get_player_name(bot: commands.Bot, guild: discord.Guild, discord_id: int) -> str:
    member = guild.get_member(discord_id)
    if member:
        return member.display_name

    user = bot.get_user(discord_id)
    if user:
        return user.display_name

    return "Unknown Player"


def build_leaderboard_boards(bot: commands.Bot, guild: discord.Guild, guild_options: dict) -> list[dict]:
    boards = []

    if guild_options["seperate_mm_roles"]:
        role_ids = guild_options.get("mm_roles", [])
        if not guild_options.get("lb_all_roles", True) and role_ids:
            role_ids = [role_ids[0]]

        for region in REGIONS:
            for role_id in role_ids:
                role = guild.get_role(role_id)
                role_name = role.name if role else f"Role {role_id}"
                players = mongodb.getTopEloPlayers(guild.id, region, role_id=role_id, limit=None)
                if not players:
                    continue
                boards.append({
                    "key": f"{region}:{role_id}",
                    "title": f"{region} {role_name}",
                    "players": players,
                })
    elif guild_options["seperate_mm"]:
        enthusiasm_options = ENTHUSIASM_OPTIONS if guild_options.get("lb_all_roles", True) else ["tryhard"]
        for region in REGIONS:
            for enthusiasm in enthusiasm_options:
                players = mongodb.getTopEloPlayers(guild.id, region, enthusiasm=enthusiasm, limit=None)
                if not players:
                    continue
                boards.append({
                    "key": f"{region}:{enthusiasm}",
                    "title": f"{region} {enthusiasm.title()}",
                    "players": players,
                })
    else:
        for region in REGIONS:
            players = mongodb.getTopEloPlayers(guild.id, region, limit=None)
            if not players:
                continue
            boards.append({
                "key": region,
                "title": region,
                "players": players,
            })

    return boards


def build_summary_embed(board: dict, guild_options: dict, page_index: int, total_pages: int, page_size: int) -> discord.Embed:
    total_players = len(board["players"])
    start_rank = page_index * page_size + 1
    end_rank = min((page_index + 1) * page_size, total_players)

    embed = discord.Embed(
        title=f"🏆 {board['title']} Leaderboard 🏆",
        description=f"Showing ranks {start_rank}-{end_rank} of {total_players} players.",
        color=discord.Color.gold(),
    )

    elo_text = "rankSystem" if guild_options["ranks"] else "pointSystem"
    embed.add_field(
        name=elosystems[elo_text]["name"],
        value=elosystems[elo_text]["value"],
        inline=False,
    )

    season = guild_options["season"] if guild_options["season"] else "Beta Season"
    next_reset = guild_options["next_reset"] if guild_options["next_reset"] else (datetime.now() + timedelta(days=60)).strftime("01.%m.%Y")
    embed.add_field(
        name=season,
        value=f"Stats will be resetted on {next_reset}.",
        inline=False,
    )

    if guild_options.get("top3_last_season"):
        top3_text = "\n".join(
            f"{emoji} <@{player['discord_id']}> {player['elo']}"
            for emoji, player in zip(["🥇", "🥈", "🥉"], guild_options["top3_last_season"])
        )
        embed.add_field(
            name="<:lb:1318628338906173490> Top 3 Last Season",
            value=top3_text,
            inline=False,
        )

    if not guild_options["ranks"]:
        now = datetime.now(pytz.timezone(guild_options["tz"]))
        if now.weekday() in [5, 6]:
            if guild_options["doublePointsWeekend"]:
                embed.add_field(
                    name="Weekend Bonus",
                    value="Double plus points for all wins are active.",
                    inline=False,
                )
            elif guild_options["doublePointsWeekendNegativeElo"]:
                embed.add_field(
                    name="Weekend Bonus",
                    value="Double plus points for wins of players with negative elo are active.",
                    inline=False,
                )

    last_update = datetime.now(pytz.timezone(guild_options["tz"])).strftime(f"%d.%m.%Y, %H:%M {guild_options['tz']}")
    embed.set_footer(text=f"Page {page_index + 1}/{total_pages} | Last update: {last_update}")
    return embed


def build_ranking_embeds(bot: commands.Bot, guild: discord.Guild, board: dict, page_index: int, page_size: int) -> list[discord.Embed]:
    page_start = page_index * page_size
    page_end = min((page_index + 1) * page_size, len(board["players"]))
    page_players = board["players"][page_start:page_end]

    if not page_players:
        return [
            discord.Embed(
                title=f"🏆 {board['title']} Leaderboard 🏆",
                description="No players found for this leaderboard.",
                color=discord.Color.red(),
            )
        ]

    embeds = []
    for chunk_start in range(0, len(page_players), PLAYERS_PER_EMBED):
        chunk = page_players[chunk_start:chunk_start + PLAYERS_PER_EMBED]
        lines = []
        for idx, player in enumerate(chunk, start=page_start + chunk_start + 1):
            player_name = get_player_name(bot, guild, player.get("discord_id", 0))
            elo = player.get("elo", 0)
            lines.append(f"{idx}. {player_name} : {elo}")

        embed = discord.Embed(
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embeds.append(embed)

    return embeds


class LeaderboardBoardSelect(discord.ui.Select):
    def __init__(self, leaderboard_view: "LeaderboardView"):
        self.leaderboard_view = leaderboard_view
        options = [
            discord.SelectOption(
                label=board["title"][:100],
                value=str(index),
                default=index == leaderboard_view.current_board_index,
            )
            for index, board in enumerate(leaderboard_view.boards)
        ]

        super().__init__(
            placeholder="Select leaderboard",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.leaderboard_view.current_board_index = int(self.values[0])
        self.leaderboard_view.current_page = 0
        self.leaderboard_view.sync_components()
        await interaction.response.edit_message(embeds=self.leaderboard_view.build_embeds(), view=self.leaderboard_view)


class LeaderboardView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, guild_options: dict, boards: list[dict], page_size: int):
        super().__init__(timeout=900)
        self.bot = bot
        self.guild = guild
        self.guild_options = guild_options
        self.boards = boards
        self.page_size = page_size
        self.current_board_index = 0
        self.current_page = 0
        self.message = None

        if len(self.boards) > 1:
            self.board_select = LeaderboardBoardSelect(self)
            self.add_item(self.board_select)
        else:
            self.board_select = None

        self.sync_components()

    @property
    def current_board(self) -> dict:
        return self.boards[self.current_board_index]

    @property
    def total_pages(self) -> int:
        total_players = len(self.current_board["players"])
        return max(1, math.ceil(total_players / self.page_size))

    def build_embeds(self) -> list[discord.Embed]:
        summary_embed = build_summary_embed(
            self.current_board,
            self.guild_options,
            self.current_page,
            self.total_pages,
            self.page_size,
        )
        ranking_embeds = build_ranking_embeds(
            self.bot,
            self.guild,
            self.current_board,
            self.current_page,
            self.page_size,
        )
        return [summary_embed, *ranking_embeds]

    def sync_components(self):
        self.previous_page.disabled = self.current_page <= 0
        self.next_page.disabled = self.current_page >= self.total_pages - 1

        if self.board_select:
            for index, option in enumerate(self.board_select.options):
                option.default = index == self.current_board_index

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        self.sync_components()
        await interaction.response.edit_message(embeds=self.build_embeds(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        self.sync_components()
        await interaction.response.edit_message(embeds=self.build_embeds(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _safe_interaction_reply(self, interaction: discord.Interaction, content: str, ephemeral: bool = True):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content=content, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content=content, ephemeral=ephemeral)
            return True
        except discord.NotFound:
            return False
        except Exception as e:
            print(f"Unexpected leaderboard interaction error: {str(e)}")
            return False

    @guild_only
    @app_commands.command(description="show the leaderboard")
    @dynamic_guild_cooldown(seconds=15)
    async def leaderboard(self, interaction: discord.Interaction):
        guild_options = await asyncio.to_thread(mongodb.findGuildOptions, interaction.guild.id)
        boards = await asyncio.to_thread(build_leaderboard_boards, self.bot, interaction.guild, guild_options)

        if not boards:
            empty_embed = discord.Embed(
                title="🏆 Leaderboard 🏆",
                description="No played matches found for this server.",
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=empty_embed, ephemeral=True)

        page_size = max(1, min(guild_options.get("lb_limit", 100), MAX_PAGE_SIZE))
        view = LeaderboardView(self.bot, interaction.guild, guild_options, boards, page_size)
        await interaction.response.send_message(embeds=view.build_embeds(), view=view)
        view.message = await interaction.original_response()

    @leaderboard.error
    async def leaderboard_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await self.__handle_error("leaderboard", interaction, error)

    async def __handle_error(self, function, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original_error = getattr(error, "original", error)

        if isinstance(original_error, discord.NotFound) and getattr(original_error, "code", None) == 10062:
            print(f"Interaction expired in \"{function}\" command (10062 Unknown interaction).")
            return

        if isinstance(error, app_commands.CommandOnCooldown):
            await self._safe_interaction_reply(interaction, f"❌ {str(error)}", ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            await self._safe_interaction_reply(interaction, "❌ You do not have permission to use this command.", ephemeral=True)
        elif isinstance(error, app_commands.NoPrivateMessage):
            await self._safe_interaction_reply(interaction, "❌ This command cannot be run in private messages.", ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure):
            await self._safe_interaction_reply(interaction, "❌ You do not have permission to use this command.", ephemeral=True)
        else:
            print(f"Unhandled error in \"{function}\" command: {error}")
            await self._safe_interaction_reply(interaction, f"❌ An unknown error occurred: {error}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
