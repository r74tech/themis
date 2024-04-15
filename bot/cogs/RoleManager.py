import time

import discord
from discord import Member, Role
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup, slash_command
from discord.ui import Select as DiscordSelect, View
from sqlalchemy.future import select as sqlalchemy_select

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, BigInteger, delete

from .utils.db import engine
from .utils.common import CommonUtil

Base = declarative_base()
c = CommonUtil()
member_ids_dict = {}


class RoleMapping(Base):
    __tablename__ = "role_mappings"
    id = Column(Integer, primary_key=True)
    server_id = Column(BigInteger)
    role_name = Column(String)
    role_id = Column(BigInteger)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class RoleSelect(DiscordSelect):
    def __init__(self, role_names):
        options = [
            discord.SelectOption(label=role_name, value=role_name)
            for role_name in role_names
        ]
        self.session = sessionmaker(bind=engine, class_=AsyncSession)

        super().__init__(
            placeholder="ロールを選択してください",
            options=options,
            min_values=1,
            max_values=len(options),
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.view is None:
            return
        # select menuを無効にする
        for item in self.view.children:
            item.disabled = True
        await self.view.message.edit(view=self.view)

        selected_roles = self.values

        async with self.session() as session:
            role_ids = []
            for role_name in selected_roles:
                mapping = await session.execute(
                    sqlalchemy_select(RoleMapping).where(
                        RoleMapping.server_id == interaction.guild.id,
                        RoleMapping.role_name == role_name,
                    )
                )
                mapping = mapping.scalar()
                if mapping:
                    role_ids.append(mapping.role_id)

            roles = [interaction.guild.get_role(role_id) for role_id in role_ids]

            if not roles:
                await interaction.response.send_message(":exclamation: 指定されたロールが見つかりませんでした")
                return

            member_id = member_ids_dict[self.custom_id].get("member_id")
            member_ids_dict.pop(self.custom_id)

            member = discord.utils.get(interaction.guild.members, id=member_id)

            await member.add_roles(*roles)

            role_mentions = " ".join(role.mention for role in roles)
            allowed_mentions = discord.AllowedMentions(roles=False, users=True)
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content=f"{role_mentions} を {member.mention} に割り当てました",
                allowed_mentions=allowed_mentions,
                view=None,
            )


class RoleSelectView(View):
    def __init__(self, role_names):
        super().__init__()
        self.add_item(RoleSelect(role_names))


class RoleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = sessionmaker(bind=engine, class_=AsyncSession)

    @commands.Cog.listener()
    async def on_ready(self):
        await create_tables()
        await self.update_role_mappings()

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self.update_role_mappings()

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        await self.update_role_mappings()

    async def update_role_mappings(self):
        async with self.session() as session:
            for guild in self.bot.guilds:
                # ボット専用でないロールのみを処理, また自分の持つ最高位のロールは処理しない, またeveryoneロールも処理しない
                non_bot_roles = [
                    role
                    for role in guild.roles
                    if not role.is_bot_managed()
                    and role.is_assignable()
                    and role.position != guild.me.top_role.position
                ]
                for role in non_bot_roles:
                    mapping = await session.execute(
                        sqlalchemy_select(RoleMapping).where(
                            RoleMapping.server_id == guild.id,
                            RoleMapping.role_id == role.id,
                        )
                    )
                    mapping = mapping.scalar()

                    if mapping:
                        mapping.role_name = role.name
                    else:
                        mapping = RoleMapping(
                            server_id=guild.id, role_name=role.name, role_id=role.id
                        )
                        session.add(mapping)

            # 重複値を削除
            await session.execute(
                delete(RoleMapping).where(
                    RoleMapping.id.notin_(
                        sqlalchemy_select(RoleMapping.id).distinct(
                            RoleMapping.server_id, RoleMapping.role_id
                        )
                    )
                )
            )


            await session.commit()

    @slash_command(name="update_db", description="データベースを更新します")
    @commands.is_owner()
    async def update_db(self, ctx: discord.ApplicationContext):
        await self.update_role_mappings()
        await ctx.respond("データベースを更新しました")


    @slash_command(name="assign", description="指定したロールを割り当てます")
    @commands.has_permissions(manage_roles=True)
    async def assign_role(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "ロールを割り当てるメンバーを指定してください"),
    ):
        member_id = member.id
        async with self.session() as session:
            mappings = await session.execute(
                sqlalchemy_select(RoleMapping.role_name).where(
                    RoleMapping.server_id == ctx.guild_id
                )
            )
            role_names = [mapping for mapping in mappings.scalars()]

        view = RoleSelectView(role_names)
        view.message = await ctx.respond("ロールを選択してください", view=view)

        member_ids_dict[view.children[0].custom_id] = {
            "member_id": member_id,
        }


def setup(bot):
    return bot.add_cog(RoleManager(bot))