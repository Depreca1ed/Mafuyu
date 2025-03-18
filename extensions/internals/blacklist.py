from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from utils import AlreadyBlacklistedError, BaseCog, BlacklistData, BotEmojis, NotBlacklistedError

if TYPE_CHECKING:
    from utils import Context, Mafuyu

WHITELISTED_GUILDS = [1219060126967664754, 774561547930304536]


class Blacklist(BaseCog):
    _command_attempts: dict[int, int]

    def __init__(self, bot: Mafuyu) -> None:
        self._command_attempts = {}

        super().__init__(bot)

    async def cog_load(self) -> None:
        self.bot.blacklists = {}
        entries = await self.bot.pool.fetch("""SELECT * FROM Blacklists""")

        for entry in entries:
            self.bot.blacklists[entry['snowflake']] = BlacklistData(
                reason=entry['reason'],
                lasts_until=entry['lasts_until'],
                blacklist_type=entry['blacklist_type'],
            )

        # Filled cache

    @commands.group(
        name='blacklist',
        aliases=['bl'],
        invoke_without_command=True,
        help='The command which handles bot blacklists',
    )
    @commands.is_owner()
    async def blacklist_cmd(self, ctx: Context) -> None:
        bl_guild_count = len([
            entry for entry in self.bot.blacklists if self.bot.blacklists[entry].blacklist_type == 'guild'
        ])
        bl_user_count = len([entry for entry in self.bot.blacklists if self.bot.blacklists[entry].blacklist_type == 'user'])

        content = f'Currently, `{bl_guild_count}` servers and `{bl_user_count}` users are blacklisted.'
        await ctx.reply(content=content)

    @blacklist_cmd.command(name='show', description='Get information about a blacklist entry if any', aliases=['info'])
    async def blacklist_info(
        self, ctx: Context, snowflake: discord.User | discord.Member | discord.Guild
    ) -> discord.Message:
        bl = self.bot.is_blacklisted(snowflake)
        if not bl:
            return await ctx.reply(f'{snowflake} is not blacklisted')
        timestamp_wording = self._timestamp_wording(bl.lasts_until)
        content = f'`{snowflake}` is blacklisted from using this bot for `{bl.reason}` {timestamp_wording}.'
        return await ctx.reply(content)

    @blacklist_cmd.command(name='add', help='Add a user or server to the blacklist')
    async def blacklist_add(
        self,
        ctx: Context,
        snowflake: discord.User | discord.Member | discord.Guild,
        until: str | None,
        *,
        reason: str = 'No reason provided',
    ) -> None:
        if snowflake.id in WHITELISTED_GUILDS:
            msg = 'You cannot blacklist this guilld.'
            raise commands.CheckFailure(msg)
        bl_until = None
        if until:
            bl_until = await self._handle_datetime_argument(ctx, until)
            if not bl_until:
                return

        try:
            await self.add(snowflake, lasts_until=bl_until, reason=reason)

        except AlreadyBlacklistedError as err:
            content = str(err)
            await ctx.reply(content)

        await ctx.message.add_reaction(BotEmojis.GREEN_TICK)
        return

    @blacklist_cmd.command(name='remove', help='Remove a user or server from blacklist')
    async def blacklist_remove(self, ctx: Context, snowflake: discord.User | discord.Member | discord.Guild | int) -> None:
        try:
            await self.remove(snowflake)

        except NotBlacklistedError as err:
            content = str(err)
            await ctx.reply(content)
            return

        await ctx.message.add_reaction(BotEmojis.GREEN_TICK)

    async def bot_check_once(self, ctx: Context) -> bool:
        """
        Blacklist check ran every command.

        Parameters
        ----------
        ctx : Context
            The commands.Context from the check

        Returns
        -------
        bool
            If the command should be run

        """
        if data := self.bot.is_blacklisted(ctx.author):
            if not await self._pre_check(ctx.author, data):
                return True
            await self.handle_user_blacklist(ctx, ctx.author, data)
            return False

        if ctx.guild and (data := self.bot.is_blacklisted(ctx.guild)):
            if not await self._pre_check(ctx.guild, data):
                return True
            await self.handle_guild_blacklist(ctx, ctx.guild, data)
            return False

        return True

    async def _pre_check(
        self,
        snowflake: discord.User | discord.Member | discord.Guild,
        data: BlacklistData,
    ) -> bool:
        """
        Check(not to be confused with command check) to make sure user is actually still blacklisted.

        Parameters
        ----------
        snowflake : discord.User | discord.Member | discord.Guild
            The snowflake being checked
        data : BlacklistData
            Blacklist data of the snowflake

        Returns
        -------
        bool
            If user is still blacklisted

        """
        if data.lasts_until and datetime.datetime.now() > data.lasts_until:
            await self.remove(snowflake)
            return True
        return False

    async def handle_user_blacklist(self, ctx: Context, user: discord.User | discord.Member, data: BlacklistData) -> None:
        """
        Handle the actions to be done when the bot comes across a blacklisted user.

        Parameters
        ----------
        ctx : Context
            The commands.Context from the check
        user : discord.User | discord.Member
            The blacklisted User
        data : BlacklistData
            The data of the blacklisted users i.e. reason, lasts_until & blacklist_type

        """
        timestamp_wording = self._timestamp_wording(data.lasts_until)
        content = (
            f'{user.mention}, you are blacklisted from using {ctx.bot.user} for `{data.reason}` {timestamp_wording}. '
            f'If you wish to appeal this blacklist, please join the [Support Server]( {self.bot.support_invite} ).'
        )

        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.channel.send(content)
            return

        attempt_check = self._command_attempts.get(user.id)

        if not attempt_check:
            self._command_attempts[user.id] = attempt_check = 0

        self._command_attempts[user.id] += 1

        if attempt_check >= 5:
            await ctx.channel.send(content)
            del self._command_attempts[user.id]
            return

        return

    async def handle_guild_blacklist(self, ctx: Context | None, guild: discord.Guild, data: BlacklistData) -> None:
        """
        Handle the actions to be done when the bot comes across a blacklisted guild.

        This function is also used in the on_guild_join event thus the optional context argument.


        Parameters
        ----------
        ctx : Context | None
            The commands.Context from the check. Will be optional when used in the event.
        guild : discord.Guild
            The blacklisted Guild
        data : BlacklistData
            The data of the blacklisted users i.e. reason, lasts_until & blacklist_type

        """
        channel = (
            ctx.channel
            if ctx
            else discord.utils.find(
                lambda ch: (ch.guild.system_channel or 'general' in ch.name.lower())  # The channel to choose
                and ch.permissions_for(guild.me).send_messages is True,  # The check for if we can send message
                guild.text_channels,
            )
        )

        timestamp_wording = self._timestamp_wording(data.lasts_until)
        content = (
            f'`{guild}` is blacklisted from using this bot for `{data.reason}` {timestamp_wording}.'
            f'If you wish to appeal this blacklist, please join the [Support Server]( {self.bot.support_invite} ).'
        )

        if channel:
            await channel.send(content=content)

    async def _handle_datetime_argument(self, ctx: Context, dt: str) -> None | datetime.datetime:
        suffixes = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400,
            'mo': 2592000,
            'y': 2592000 * 12,
        }

        if dt[-1:] not in suffixes:
            await ctx.reply(f"{ctx.author.mention}, i can't understand the time you provided.")
            return None
        parsed = suffixes[dt[-1:]]
        c = int(dt[:-1]) if dt[-2:] != 'mo' else int(dt[-2:])
        final = c * parsed
        return datetime.datetime.now() + datetime.timedelta(seconds=final)

    async def add(
        self,
        snowflake: discord.User | discord.Member | discord.Guild,
        *,
        reason: str,
        lasts_until: datetime.datetime | None = None,
    ) -> dict[int, BlacklistData]:
        """
        Add an entry to the blacklist.

        This adds the entry to the database as well as cache

        Parameters
        ----------
        snowflake : discord.User | discord.Member | discord.Guild
            The snowflake being blacklisted
        reason : str, optional
            The reason for the blacklist, by default 'No reason provided'
        lasts_until : datetime.datetime | None, optional
            For how long the snowflake is blacklisted for, by default None

        Returns
        -------
        dict[int, BlacklistData]
            Returns a dict of the snowflake and the data as stored in the cache

        Raises
        ------
        AlreadyBlacklistedError
            Raised when snowflake being blacklisted is already blacklisted.
            This is handled by the command executing this function

        """
        entry = self.bot.is_blacklisted(snowflake)

        if entry:
            check = await self._pre_check(snowflake, entry)
            if check:
                raise AlreadyBlacklistedError(snowflake, reason=entry.reason, until=entry.lasts_until)
        blacklist_type = 'user' if isinstance(snowflake, discord.User | discord.Member) else 'guild'

        await self.bot.pool.execute(
            """INSERT INTO
                    Blacklists (snowflake, reason, lasts_until, blacklist_type)
               VALUES
                    ($1, $2, $3, $4);""",
            snowflake.id,
            reason,
            lasts_until,
            blacklist_type,
        )

        self.bot.blacklists[snowflake.id] = BlacklistData(
            reason=reason,
            lasts_until=lasts_until,
            blacklist_type=blacklist_type,
        )
        return {snowflake.id: self.bot.blacklists[snowflake.id]}

    async def remove(self, snowflake: discord.User | discord.Member | discord.Guild | int) -> dict[int, BlacklistData]:
        """
        Remove an entry from the blacklist.

        This removes the entry from the database as well as cache

        Parameters
        ----------
        snowflake : discord.User | discord.Member | discord.Guild
            The snowflake being removed from blacklist

        Returns
        -------
        dict[int, BlacklistData]
            A dict of the snowflake and the data as was in the cache beforehand

        Raises
        ------
        NotBlacklistedError
            Raised when the snowflake is not blacklisted to begin with

        """
        if not self.bot.is_blacklisted(snowflake):
            raise NotBlacklistedError(snowflake)

        obj = snowflake if isinstance(snowflake, int) else snowflake.id

        await self.bot.pool.execute(
            """DELETE FROM Blacklists WHERE snowflake = $1""",
            obj,
        )

        item_removed = self.bot.blacklists.pop(obj)
        return {obj: item_removed}

    def _timestamp_wording(self, dt: datetime.datetime | None) -> str:
        return f'until {discord.utils.format_dt(dt, "f")}' if dt else 'permanently'
