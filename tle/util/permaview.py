import discord
from discord.ext import commands
from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common
from tle.util import db


import asyncio
import random
import time

class registermodal(discord.ui.Modal, title='Identify Codeforces account'):
    handle = discord.ui.TextInput(label='Codeforces username:')
    
    async def on_submit(self, interaction: discord.Interaction):

        if cf_common.user_db.get_user_id( str(self.handle), interaction.guild_id):
            await interaction.response.send_message( f'The handle `{self.handle}` is already associated with another user. Ask an Admin or Moderator in case of an inconsistency.', ephemeral=True)
            return

        try:
            users = await cf.user.info(handles=[str(self.handle)])
        except cf.HandleNotFoundError as e:
            await interaction.response.send_message( f'Handle `{self.handle}` not found on Codeforces', ephemeral=True)
            return

        
        invoker = str(interaction.user)
        handle = users[0].handle
        problems = [prob for prob in cf_common.cache2.problem_cache.problems
                    if prob.rating <= 1200]
        problem = random.choice(problems)
        await interaction.response.send_message(f'`{invoker}`, submit a compile error to <{problem.url}> <t:{int(time.time())+60}:R>', ephemeral=True)
        await asyncio.sleep(60)

        subs = await cf.user.status(handle=handle, count=5)
        if any(sub.problem.name == problem.name and sub.verdict == 'COMPILATION_ERROR' for sub in subs):
            user, = await cf.user.info(handles=[handle])

            member = interaction.user
            try:
                cf_common.user_db.set_handle(member.id, interaction.guild_id, handle)
            except db.UniqueConstraintFailed:
                interaction.followup.send(content=f'The handle `{self.handle}` is already associated with another user. Ask an Admin or Moderator in case of an inconsistency.', ephemeral=True)
                return
            cf_common.user_db.cache_cf_user(user)
    
            if user.rank == cf.UNRATED_RANK:
                role_to_assign = None
            else:
                roles = [role for role in interaction.guild.roles if role.name == user.rank.title]
                if len(roles) == 0:
                    interaction.followup.send(content=f'Role for rank `{user.rank.title}` not present in the server')
                role_to_assign = roles[0]

            role_names_to_remove = {rank.title for rank in cf.RATED_RANKS}
            if role_to_assign is not None:
                role_names_to_remove.discard(role_to_assign.name)
                if role_to_assign.name not in ['Newbie', 'Pupil', 'Specialist', 'Expert']:
                    role_names_to_remove.add('Purgatory')
            to_remove = [role for role in member.roles if role.name in role_names_to_remove]
            if to_remove:
                await member.remove_roles(*to_remove, reason='New handle set for user')
            if role_to_assign is not None and role_to_assign not in member.roles:
                await member.add_roles(role_to_assign, reason='New handle set for user')

            await interaction.followup.send(content=f'Handle for {member.mention} successfully set to **[{user.handle}]({user.url})**', ephemeral=True)
        else:
            await interaction.followup.send(content=f'Sorry `{invoker}`, can you try again?', ephemeral=True)



class PersistentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='register', style=discord.ButtonStyle.green, custom_id='register_button')
 #    @cf_common.user_guard(group='handle', get_exception=lambda: )
    async def registerbutton(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        if cf_common.user_db.get_handle(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message( 'You cannot identify when your handle is already set. Ask an Admin or Moderator if you wish to change it', ephemeral=True)
            return

        await interaction.response.send_modal( registermodal() )

