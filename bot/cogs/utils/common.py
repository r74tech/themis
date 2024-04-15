import logging

import discord
from discord.ext import commands


class CommonUtil:
    @staticmethod
    async def delete_after(
        msg: discord.Message | discord.InteractionMessage, second: int = 5
    ):
        """渡されたメッセージを指定秒数後に削除する関数

        Args:
            msg (discord.Message): 削除するメッセージオブジェクト
            second (int, optional): 秒数. Defaults to 5.
        """
        if isinstance(msg, discord.InteractionMessage):
            try:
                await msg.delete(delay=second)
            except discord.Forbidden:
                logging.error("メッセージの削除に失敗しました。Forbidden")
        else:
            try:
                await msg.delete(delay=second)
            except discord.Forbidden:
                logging.error("メッセージの削除に失敗しました。Forbidden")

    @staticmethod
    def return_member_or_role(
        guild: discord.Guild, id: int
    ) -> discord.Role | discord.Member:
        """メンバーか役職オブジェクトを返す関数

        Args:
            guild (discord.guild): discord.pyのguildオブジェクト
            id (int): 役職かメンバーのID

        Returns:
            typing.Union[discord.Member, discord.Role]: discord.Memberかdiscord.Role
        """
        user_or_role = guild.get_role(id)
        if user_or_role is None:
            user_or_role = guild.get_member(id)

        if user_or_role is None:
            raise ValueError(f"IDが不正です。ID:{id}")

        return user_or_role

    async def has_bot_user(
        self, guild: discord.Guild | None, command_user: discord.Member | discord.User
    ) -> bool:
        """bot_userかどうか判定する関数

        Args:
            guild (discord.Guild): サーバーのギルドオブジェクト
            command_user (discord.Member): コマンド使用者のメンバーオブジェクト

        Returns:
            bool: BOT_userならTrue、そうでなければFalse
        """

        if isinstance(command_user, discord.User):
            return False

        if not isinstance(guild, discord.Guild):
            return False

        if not await self.is_bot_user(guild, command_user):
            return False
        else:
            return True

    async def has_bot_manager(
        self, guild: discord.Guild | None, command_user: discord.Member | discord.User
    ) -> bool:
        """bot_managerかどうか判定する関数

        Args:
            guild (discord.Guild): サーバーのギルドオブジェクト
            command_user (discord.Member): コマンド使用者のメンバーオブジェクト

        Returns:
            bool: BOT_userならTrue、そうでなければFalse
        """

        if isinstance(command_user, discord.User):
            return False

        if not isinstance(guild, discord.Guild):
            return False

        if not await self.is_bot_manager(guild, command_user):
            return False
        else:
            return True