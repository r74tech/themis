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

class StaticRole(Base):
    __tablename__ = "static_roles"
    id = Column(Integer, primary_key=True)
    server_id = Column(BigInteger)
    role_id = Column(BigInteger)

class InactiveRole(Base):
    __tablename__ = "inactive_roles"
    id = Column(Integer, primary_key=True)
    server_id = Column(BigInteger)
    role_id = Column(BigInteger)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class RoleSelect(DiscordSelect):
    def __init__(self, bot, role_names):
        options = [
            discord.SelectOption(label=role_name, value=role_name)
            for role_name in role_names
        ]
        self.session = sessionmaker(bind=engine, class_=AsyncSession)
        self.bot = bot

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
        # Select menuを無効にする
        for item in self.view.children:
            item.disabled = True
        await self.view.message.edit(view=self.view)

        selected_roles = self.values

        async with self.session() as session:
            role_ids = []
            for role_name in selected_roles:
                for guild in self.bot.guilds:
                    role = discord.utils.find(lambda r: r.name == role_name, guild.roles)
                    if role:
                        role_ids.append((role.id, guild.id))

            if not role_ids:
                await interaction.response.send_message(":exclamation: 指定されたロールがどのサーバーにも見つかりませんでした")
                return

            member_id = member_ids_dict[self.custom_id].get("member_id")
            member = self.bot.get_user(member_id)
            member_ids_dict.pop(self.custom_id)

            # すべてのギルドでロールをメンバーに付与
            for role_id, guild_id in role_ids:
                guild = self.bot.get_guild(guild_id)
                guild_member = guild.get_member(member_id)
                if guild_member:
                    role = guild.get_role(role_id)
                    await guild_member.add_roles(role)

            allowed_mentions = discord.AllowedMentions(roles=False, users=True)
            embed = discord.Embed(
                title="ロールを割り当てました",
                description=f"{member.mention} に割り当てたロールは以下の通りです",
            )
            for guild_id in set(guild_id for _, guild_id in role_ids):
                guild = self.bot.get_guild(guild_id)
                if guild == interaction.guild:
                    roles = [
                        role.mention
                        for role_id, _guild_id in role_ids
                        if _guild_id == guild_id
                        for role in guild.roles
                        if role.id == role_id
                    ]
                else:
                    roles = [
                        role_name
                        for role_id, _guild_id in role_ids
                        if _guild_id == guild_id
                        for role_name in [role.name for role in guild.roles if role.id == role_id]
                    ]

                embed.add_field(
                    name=guild.name,
                    value=", ".join(roles),
                    inline=False,
                )

            await interaction.followup.edit_message(
                embed=embed,
                content=None,
                allowed_mentions=allowed_mentions,
                message_id=interaction.message.id,
                view=None,
            )


class RoleSelectView(View):
    def __init__(self,bot, role_names):
        self.bot = bot
        super().__init__()
        self.add_item(RoleSelect(self.bot, role_names))


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

        view = RoleSelectView(self.bot, role_names)
        view.message = await ctx.respond("ロールを選択してください", view=view)

        member_ids_dict[view.children[0].custom_id] = {
            "member_id": member_id,
        }

    @assign_role.error
    async def assign_role_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond("権限がありません")


    @slash_command(name="inactive", description="非アクティブ化処理を行います")
    @commands.has_permissions(manage_roles=True)
    async def inactive(self, ctx: discord.ApplicationContext, member: Option(Member, "非アクティブ化処理を行うメンバーを指定してください", required=True)):
        # すべてのサーバーでstatic_roles以外のロールをすべて削除し、inactive_rolesのロールを付与する
        await ctx.response.defer()
        roles_dict = {}
        async with self.session() as session:
            inactive_roles = await session.execute(
                sqlalchemy_select(InactiveRole.role_id)
            )
            inactive_roles = [role_id for role_id in inactive_roles.scalars()]

            static_roles = await session.execute(
                sqlalchemy_select(StaticRole.role_id)
            )
            static_roles = [role_id for role_id in static_roles.scalars()]

        for guild in self.bot.guilds:
            member = guild.get_member(member.id)
            if member:
                roles_dict[guild.id] = []
                for role in member.roles:
                    if role.id not in static_roles and role.is_assignable():
                        roles_dict[guild.id].append(role.id)
                        await member.remove_roles(role)

                for role_id in inactive_roles:
                    role = guild.get_role(role_id)
                    if role:
                        await member.add_roles(role)
        
        embed = discord.Embed(
            title="非アクティブ化処理を行いました",
            description=f"{member.mention} から削除したロールは以下の通りです",
        )
        for guild_id, role_ids in roles_dict.items():
            guild = self.bot.get_guild(guild_id)
            roles = [role.name for role in guild.roles if role.id in role_ids]
            embed.add_field(name=guild.name, value=", ".join(roles), inline=False)
        
        await ctx.followup.send(embed=embed)

    @slash_command(name="uninactive", description="非アクティブ化処理を解除します")
    @commands.has_permissions(manage_roles=True)
    async def uninactive(self, ctx: discord.ApplicationContext, member: Option(Member, "非アクティブ化処理を解除するメンバーを指定してください", required=True)):
        async with self.session() as session:
            inactive_roles = await session.execute(
                sqlalchemy_select(InactiveRole.role_id)
            )
            inactive_roles = [role_id for role_id in inactive_roles.scalars()]

        guilds_list = []
        for guild in self.bot.guilds:
            member = guild.get_member(member.id)
            if member:
                for role_id in inactive_roles:
                    role = guild.get_role(role_id)
                    if role:
                        guilds_list.append(guild)
                        await member.remove_roles(role)

        guild_names = ""
        print(guilds_list)
        if guilds_list:
            for guild in guilds_list:
                guild_names += f"{guild.name}, "
        
        await ctx.respond(f"{member.mention} から非アクティブ化処理を解除しました: {guild_names}")



    @slash_command(name="static", description="非アクティブ化で処理を行わないロールを設定します")
    @commands.has_permissions(manage_roles=True)
    async def static(self, ctx: discord.ApplicationContext, roles: Option(str, "非アクティブ化で処理を行わないロールを指定してください", required=True)):
        roles = roles.split(",")
        async with self.session() as session:
            for guild in self.bot.guilds:
                for role in guild.roles:
                    if role.name in roles:
                        mapping = await session.execute(
                            sqlalchemy_select(StaticRole).where(
                                StaticRole.server_id == guild.id,
                                StaticRole.role_id == role.id,
                            )
                        )
                        mapping = mapping.scalar()

                        if mapping:
                            mapping.role_id = role.id
                        else:
                            mapping = StaticRole(
                                server_id=guild.id, role_id=role.id
                            )
                            session.add(mapping)

            await session.commit()
        
        # 設定したロールを表示
        await ctx.respond(f"非アクティブ化で処理を行わないロールを設定しました: {roles}")

    @slash_command(name="set_inactive", description="非アクティブ化時に割り当てるロールを設定します")
    @commands.has_permissions(manage_roles=True)
    async def set_inactive(self, ctx: discord.ApplicationContext, role_name: Option(str, "非アクティブ化時に割り当てるロールを指定してください", required=True)):
        async with self.session() as session:
            for guild in self.bot.guilds:
                role = discord.utils.find(lambda r: r.name == role_name, guild.roles)
                if role:
                    mapping = await session.execute(
                        sqlalchemy_select(InactiveRole).where(
                            InactiveRole.server_id == guild.id,
                            InactiveRole.role_id == role.id,
                        )
                    )
                    mapping = mapping.scalar()

                    if mapping:
                        mapping.role_id = role.id
                    else:
                        mapping = InactiveRole(
                            server_id=guild.id, role_id=role.id
                        )
                        session.add(mapping)

            await session.commit()
        
        await ctx.respond(f"非アクティブ化時に割り当てるロールを設定しました: {role_name}")

    @slash_command(name="remove_inactive", description="非アクティブ化時に割り当てるロールを削除します")
    @commands.has_permissions(manage_roles=True)
    async def remove_inactive(self, ctx: discord.ApplicationContext):
        async with self.session() as session:
            await session.execute(delete(InactiveRole))
            await session.commit()
    

    @slash_command(name="remove_static", description="非アクティブ化で処理を行わないロールを削除します")
    @commands.has_permissions(manage_roles=True)
    async def remove_static(self, ctx: discord.ApplicationContext):
        async with self.session() as session:
            await session.execute(delete(StaticRole))
            await session.commit()

    @slash_command(name="show_inactive", description="参加サーバーの非アクティブ化時に割り当てるロールを表示します")
    @commands.has_permissions(manage_roles=True)
    async def show_inactive(self, ctx: discord.ApplicationContext):
        async with self.session() as session:
            inactive_roles = await session.execute(
                sqlalchemy_select(InactiveRole.role_id)
            )
            inactive_roles = [role_id for role_id in inactive_roles.scalars()]

        roles = []
        for guild in self.bot.guilds:
            guild_roles = [role.name for role in guild.roles if role.id in inactive_roles]
            if guild_roles:
                roles.append(f"{guild.name}: {', '.join(guild_roles)}")
        
        if not roles:
            await ctx.respond("非アクティブ化時に割り当てるロールは設定されていません")
            return

        await ctx.respond("\n".join(roles))


def setup(bot):
    return bot.add_cog(RoleManager(bot))