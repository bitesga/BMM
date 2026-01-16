from discord.ext import commands, tasks
import discord, datetime, pytz
from discord.app_commands import guild_only
from discord import app_commands
from utils import currentFolder


format = "%d.%m.%Y, %H:%M"
germanTimeZone = pytz.timezone("Europe/Berlin")


botAdmins = [324607583841419276, 818879706350092298, 230684337341857792]


class ServerList(commands.Cog):
  
  def __init__(self, bot):
    self.bot = bot
    if currentFolder() == "BMM":
      self.serverList.start()


  @tasks.loop(seconds=120)
  async def serverList(self):
    total_members = sum(guild.member_count for guild in self.bot.guilds)
    description = "\n".join(guild.name+" - "+str(guild.member_count) for guild in self.bot.guilds)
    serverListEmbed = discord.Embed(title="Server List", description=description, color=int("ffffff", 16))
    serverListEmbed.add_field(name="Server Count", value=len(self.bot.guilds))
    serverListEmbed.add_field(name="Total Members", value=total_members)
    serverListEmbed.set_footer(text=f"Last Update: {datetime.datetime.now(germanTimeZone).strftime(format)}")

    serverListChannel = await self.bot.fetch_channel(1223417217727856661)
    if not serverListChannel:
        return
    
    messages = [message async for message in serverListChannel.history()]
    if not messages:
            return await serverListChannel.send(embed=serverListEmbed)
    for msg in messages:
        if msg.author == self.bot.user:
            await msg.edit(embed=serverListEmbed)
            return
    
    await serverListChannel.send(embed=serverListEmbed)


  
  # Delete player ID
  @guild_only
  @app_commands.command(description="look up invite link for a server by id or name")
  async def get_invite_link(self, interaction: discord.Interaction, server: str):
    if interaction.user.id not in botAdmins:
      return await interaction.response.send_message(content="⛔ You are not allowed to use this command.")

    await interaction.response.defer()

    try:
        for guild in self.bot.guilds:
            if guild.name == server or guild.id == server:
                invites = await guild.invites()
                if not invites:
                    await interaction.followup.send(content=f"⛔ No invite found for the server")
                else:
                    await interaction.followup.send(content=f"✅ Invite: {invites[0].url}")
    except Exception as e:
        await interaction.followup.send(content=f"⛔ Error fetching invite link {str(e)}!")

  @get_invite_link.error
  async def admin_block_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
     await self.__handle_error("get_invite_link",interaction,error)
     
            
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
  await bot.add_cog(ServerList(bot))
