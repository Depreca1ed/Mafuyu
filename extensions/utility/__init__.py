from __future__ import annotations

import operator
from collections import Counter
from io import BytesIO
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from jishaku.paginators import PaginatorInterface, WrappedFilePaginator

from utils import BaseCog

if TYPE_CHECKING:
    from utils import Context, Mafuyu


class Utility(BaseCog, name='Utility'):
    """Some useful utility commands."""

    @commands.command(name='file-to-pages', help='Turns a file into a pages to browse through', aliases=['ftp'])
    async def ftp(self, ctx: Context, attachment: discord.Attachment | None) -> discord.Message | PaginatorInterface:
        if not attachment and ctx.message.reference and isinstance(ctx.message.reference.resolved, discord.Message):
            attachment = ctx.message.reference.resolved.attachments[0]

        if not attachment:
            raise commands.MissingRequiredArgument(commands.parameter(displayed_name='attachment'))

        if attachment.size > 1024 * 1024 * 10:
            return await ctx.send('File larged than 10MB')

        if attachment.content_type and not attachment.content_type.startswith('text'):
            return await ctx.send('Not a text document')

        paginator = WrappedFilePaginator(BytesIO(await attachment.read()), max_size=1980)
        interface = PaginatorInterface(self.bot, paginator)
        return await interface.send_to(ctx)

    async def _basic_cleanup_strategy(self, ctx: Context, search: int) -> dict[str, int]:
        count = 0
        async for msg in ctx.history(limit=search, before=ctx.message):
            if msg.author == ctx.me and not (msg.mentions or msg.role_mentions):
                await msg.delete()
                count += 1
        return {'Bot': count}

    async def _complex_cleanup_strategy(self, ctx: Context, search: int) -> None | Counter[str]:
        prefixes = tuple(self.bot.get_prefixes(ctx.guild))  # thanks startswith

        def check(m: discord.Message) -> bool:
            return m.author == ctx.me or m.content.startswith(prefixes)

        if isinstance(ctx.channel, discord.DMChannel | discord.PartialMessageable | discord.GroupChannel):
            return None

        deleted = await ctx.channel.purge(limit=search, check=check, before=ctx.message)
        return Counter(m.author.display_name for m in deleted)

    async def _regular_user_cleanup_strategy(self, ctx: Context, search: int) -> None | Counter[str]:
        prefixes = tuple(self.bot.get_prefixes(ctx.guild))

        def check(m: discord.Message) -> bool:
            return (m.author == ctx.me or m.content.startswith(prefixes)) and not (m.mentions or m.role_mentions)

        if isinstance(ctx.channel, discord.DMChannel | discord.PartialMessageable | discord.GroupChannel):
            return None

        deleted = await ctx.channel.purge(limit=search, check=check, before=ctx.message)
        return Counter(m.author.display_name for m in deleted)

    @commands.command()
    @commands.guild_only()
    async def cleanup(self, ctx: Context, search: int = 100) -> None:
        strategy = self._basic_cleanup_strategy

        if not isinstance(ctx.author, discord.Member) or not isinstance(ctx.me, discord.Member):
            raise commands.GuildNotFound(str(ctx.guild))

        is_mod = ctx.channel.permissions_for(ctx.author).manage_messages
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            strategy = self._complex_cleanup_strategy if is_mod else self._regular_user_cleanup_strategy

        search = min(max(2, search), 1000) if is_mod else min(max(2, search), 25)

        spammers = await strategy(ctx, search)
        deleted = sum(spammers.values()) if spammers else 0
        messages = [f'{deleted} message{" was" if deleted == 1 else "s were"} removed.']
        if deleted:
            messages.append('')
            spammers = sorted(spammers.items(), key=operator.itemgetter(1), reverse=True) if spammers else {'Unknown': 0}
            messages.extend(f'- **{author}**: {count}' for author, count in spammers)

        await ctx.send('\n'.join(messages), delete_after=10)


async def setup(bot: Mafuyu) -> None:
    await bot.add_cog(Utility(bot))
