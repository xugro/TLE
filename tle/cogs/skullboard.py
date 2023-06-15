import asyncio
import logging

import discord
from discord.ext import commands

from tle import constants
from tle.util import codeforces_common as cf_common
from tle.util import discord_common

_SKULL = '\N{SKULL}'
_SKULL_ORANGE = 0xfffff0


class SkullboardCogError(commands.CommandError):
    pass


class Skullboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locks = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        self.logger.info( "reaction added: " + str(payload.emoji) )
        if str(payload.emoji) != _SKULL or payload.guild_id is None:
            return
        res = cf_common.user_db.get_skullboard(payload.guild_id)
        if res is None:
            return
        skullboard_channel_id = int(res[0])
        try:
            await self.check_and_add_to_skullboard(skullboard_channel_id, payload)
        except SkullboardCogError as e:
            self.logger.info(f'Failed to skullboard: {e!r}')

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        if payload.guild_id is None:
            return
        res = cf_common.user_db.get_skullboard(payload.guild_id)
        if res is None:
            return
        skullboard_channel_id = int(res[0])
        if payload.channel_id != skullboard_channel_id:
            return
        cf_common.user_db.remove_skullboard_message(skullboard_msg_id=payload.message_id)
        self.logger.info(f'Removed message {payload.message_id} from skullboard')

    @staticmethod
    def prepare_embed(message):
        # Adapted from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/skulls.py
        embed = discord.Embed(color=_SKULL_ORANGE, timestamp=message.created_at)
        embed.add_field(name='Channel', value=message.channel.mention)
        embed.add_field(name='Jump to', value=f'[Original]({message.jump_url})')

        if message.content:
            embed.add_field(name='Content', value=message.content, inline=False)

        if message.embeds:
            data = message.embeds[0]
            if data.type == 'image':
                embed.set_image(url=data.url)

        if message.attachments:
            file = message.attachments[0]
            if file.url.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                embed.set_image(url=file.url)
            else:
                embed.add_field(name='Attachment', value=f'[{file.filename}]({file.url})', inline=False)

        embed.set_footer(text=str(message.author), icon_url=message.author.avatar)
        return embed

    async def check_and_add_to_skullboard(self, skullboard_channel_id, payload):
        guild = self.bot.get_guild(payload.guild_id)
        skullboard_channel = guild.get_channel(skullboard_channel_id)
        if skullboard_channel is None:
            raise SkullboardCogError('Skullboard channel not found')

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if ((message.type != discord.MessageType.default and message.type != discord.MessageType.reply)
            or (len(message.content) == 0 and len(message.attachments) == 0)):
            raise SkullboardCogError('Cannot skullboard this message')

        reaction_count = sum(reaction.count for reaction in message.reactions
                             if str(reaction) == _SKULL)
        if reaction_count < constants.SKULLBOARD_THRESHOLD:
            return
        lock = self.locks.get(payload.guild_id)
        if lock is None:
            self.locks[payload.guild_id] = lock = asyncio.Lock()

        async with lock:
            if cf_common.user_db.check_exists_skullboard_message(message.id):
                return
            embed = self.prepare_embed(message)
            skullboard_message = await skullboard_channel.send(embed=embed)
            cf_common.user_db.add_skullboard_message(message.id, skullboard_message.id, guild.id)
            self.logger.info(f'Added message {message.id} to skullboard (Last reaction by {payload.user_id})')

    @commands.group(brief='Skullboard commands',
                    invoke_without_command=True)
    async def skullboard(self, ctx):
        """Group for commands involving the skullboard."""
        await ctx.send_help(ctx.command)

    @skullboard.command(brief='Set skullboard to current channel')
    @commands.has_role(constants.TLE_ADMIN)
    async def here(self, ctx):
        """Set the current channel as skullboard."""
        res = cf_common.user_db.get_skullboard(ctx.guild.id)
        if res is not None:
            raise SkullboardCogError('The skullboard channel is already set. Use `clear` before '
                                    'attempting to set a different channel as skullboard.')
        cf_common.user_db.set_skullboard(ctx.guild.id, ctx.channel.id)
        await ctx.send(embed=discord_common.embed_success('Skullboard channel set'))

    @skullboard.command(brief='Clear skullboard settings')
    @commands.has_role(constants.TLE_ADMIN)
    async def clear(self, ctx):
        """Stop tracking skullboard messages and remove the currently set skullboard channel
        from settings."""
        cf_common.user_db.clear_skullboard(ctx.guild.id)
        cf_common.user_db.clear_skullboard_messages_for_guild(ctx.guild.id)
        await ctx.send(embed=discord_common.embed_success('Skullboard channel cleared'))

    @skullboard.command(brief='Remove a message from skullboard')
    @commands.has_role(constants.TLE_ADMIN)
    async def remove(self, ctx, original_message_id: int):
        """Remove a particular message from the skullboard database."""
        rc = cf_common.user_db.remove_skullboard_message(original_msg_id=original_message_id)
        if rc:
            await ctx.send(embed=discord_common.embed_success('Successfully removed'))
        else:
            await ctx.send(embed=discord_common.embed_alert('Not found in database'))

    @discord_common.send_error_if(SkullboardCogError)
    async def cog_command_error(self, ctx, error):
        pass


async def setup(bot):
    await bot.add_cog(Skullboard(bot))
