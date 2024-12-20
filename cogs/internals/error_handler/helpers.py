from __future__ import annotations

from discord.ext import commands

from utils import DeContext, better_string
from utils.embed import Embed

from .constants import ERROR_COLOUR, HANDLER_EMOJIS


def clean_error(objects: list[str] | str, *, seperator: str, prefix: str) -> str:
    """
    Return a string with the given objects organised.

    Parameters
    ----------
    objects : list[str]
        List of iterables to prettify, this should be either list of roles or permissions.
    seperator : str
        String which seperates the given objects.
    prefix : str
        String which will be at the start of every object

    Returns
    -------
    str
        The generated string with the given parameters

    """
    return (
        better_string(
            (prefix + f"{(perm.replace('_', ' ')).capitalize()}" for perm in objects),
            seperator=seperator,
        )
        if objects is not str
        else prefix + objects
    )


def make_embed(*, title: str | None = None, description: str | None = None, ctx: DeContext | None = None) -> Embed:
    """
    Generate an embed for error handler responses.

    Parameters
    ----------
    title : str | None, optional
        The title for the embed
    description : str | None, optional
        The description for the embed
    ctx : DeContext | None, optional
        The context for the embed, if applicable

    Returns
    -------
    Embed
        The generated embed

    """
    embed = Embed(title=title, description=description, ctx=ctx, colour=ERROR_COLOUR)
    embed.set_thumbnail(url=HANDLER_EMOJIS['MafuyuUnamused2'].url)
    return embed


def generate_error_objects(
    error: commands.MissingPermissions
    | commands.BotMissingPermissions
    | commands.MissingAnyRole
    | commands.MissingRole
    | commands.BotMissingAnyRole
    | commands.BotMissingRole,
) -> list[str] | str:
    """
    Generate a list or string of given objects from the error.

    Note
    ----
    Only to be used in error handler for these errors.


    Parameters
    ----------
    error : commands.MissingPermissions
      | commands.BotMissingPermissions
      | commands.MissingAnyRole
      | commands.MissingRole
      | commands.BotMissingAnyRole
      | commands.BotMissingRole
        The error used to make the objects

    Returns
    -------
    list[str] | str
        The list or string made from given errors.

    Raises
    ------
    ValueError
        Raised when the string was empty.

    """
    missing_roles = (
        [str(f'<@&{role_id}>' if role_id is int else role_id) for role_id in error.missing_roles]
        if isinstance(error, commands.MissingAnyRole | commands.BotMissingAnyRole)
        else None
    )

    missing_role = (
        str(f'<@&{error.missing_role}>' if error.missing_role is int else error.missing_role)
        if isinstance(error, commands.MissingRole | commands.BotMissingRole)
        else None
    )

    missing_permissions = (
        error.missing_permissions
        if isinstance(error, commands.MissingPermissions | commands.BotMissingPermissions)
        else None
    )

    missings = missing_roles or missing_role or missing_permissions
    if not missings:
        msg = 'Expected Not-None value'
        raise ValueError(msg)

    return missings