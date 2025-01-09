from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils import BaseCog, Embed
from utils.helper_functions import better_string

if TYPE_CHECKING:
    from utils import Context


class Avatar(BaseCog):
    @commands.hybrid_command(
        name='avatar',
        help="Get your or user's displayed avatar. By default, returns your server avatar",
        aliases=['av'],
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def avatar(
        self,
        ctx: Context,
        user: discord.User | discord.Member = commands.Author,
        *,
        server_avatar: bool = True,
    ) -> discord.Message:
        avatar = user.display_avatar if server_avatar is True else user.avatar or user.default_avatar

        embed = Embed(title=f"{user}'s avatar", colour=user.color, ctx=ctx).set_image(url=avatar.url)

        filetypes = set(discord.asset.VALID_ASSET_FORMATS if avatar.is_animated() else discord.asset.VALID_STATIC_FORMATS)
        urls_string = better_string(
            [f'[{filetype.upper()}]({avatar.with_format(filetype)})' for filetype in filetypes],  # pyright: ignore[reportArgumentType]
            seperator=' **|** ',
        )
        embed.description = urls_string

        return await ctx.send(embed=embed)

    @commands.hybrid_command(name='icon', help="Get the server's icon, if any")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    @commands.guild_only()
    async def guild_avatar(self, ctx: Context) -> discord.Message:
        if not ctx.guild:
            msg = 'Guild not found'
            raise commands.GuildNotFound(msg)

        icon = ctx.guild.icon
        if not icon:
            return await ctx.reply(content=f'{commands.clean_content().convert(ctx, str(ctx.guild))} does not have an icon.')

        embed = Embed(title=f"{ctx.guild}'s icon", ctx=ctx).set_image(url=icon.url)

        filetypes = set(discord.asset.VALID_ASSET_FORMATS if icon.is_animated() else discord.asset.VALID_STATIC_FORMATS)

        urls_string = better_string(
            [f'[{filetype.upper()}]({icon.with_format(filetype)})' for filetype in filetypes],  # pyright: ignore[reportArgumentType]
            seperator=' **|** ',
        )
        embed.description = urls_string

        return await ctx.send(embed=embed)
