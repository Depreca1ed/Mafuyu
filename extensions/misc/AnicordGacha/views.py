from __future__ import annotations

import datetime
import operator
from typing import TYPE_CHECKING, Self

import discord
from discord.ext import menus

from extensions.misc.AnicordGacha.bases import GachaUser, PulledCard
from extensions.misc.AnicordGacha.constants import PULL_INTERVAL, RARITY_EMOJIS
from extensions.misc.AnicordGacha.utils import get_burn_worths
from utilities.bases.bot import Mafuyu
from utilities.embed import Embed
from utilities.functions import fmt_str, timestamp_str
from utilities.pagination import Paginator
from utilities.timers import ReservedTimerType
from utilities.view import BaseView

if TYPE_CHECKING:
    from utilities.bases.bot import Mafuyu
    from utilities.bases.context import MafuContext


class GachaPullView(BaseView):
    def __init__(
        self,
        ctx: MafuContext,
        user: discord.User | discord.Member,
        pull_message: discord.Message | None,
        gacha_user: GachaUser,
    ) -> None:
        super().__init__()
        self.ctx = ctx
        self.user = user
        self.pull_message = pull_message
        self.gacha_user = gacha_user

        self.__pulls_synced: bool = False
        self.__pulls: list[PulledCard] = []

        self._update_display()

    @classmethod
    async def start(
        cls,
        ctx: MafuContext,
        *,
        user: discord.User | discord.Member,
        pull_message: discord.Message | None,
    ) -> discord.InteractionCallbackResponse[Mafuyu] | discord.Message | None:
        gacha_user = await GachaUser.from_fetched_record(ctx.bot.pool, user=user)

        c = cls(ctx, user, pull_message, gacha_user)

        if c.pull_message:
            is_message_syncronised: bool = bool(
                await ctx.bot.pool.fetchval(
                    """
                SELECT
                    EXISTS (
                        SELECT
                            *
                        FROM
                            GachaPulledCards
                        WHERE
                            user_id = $1
                            AND message_id = $2
                    );
                """,
                    user.id,
                    c.pull_message.id,
                )
            )

            c.__pulls_synced = is_message_syncronised
            c._update_display()

        embed = c.embed()

        return await ctx.reply(embed=embed, view=c, ephemeral=True)

    def embed(self) -> Embed:
        embed = Embed(title='Anicord Gacha Bot Helper', colour=self.user.color)

        s: list[str] = []

        if self.gacha_user.timer is None:
            s.append('- You do not have a pull reminder setup yet.')

        now = datetime.datetime.now(tz=datetime.UTC)

        next_pull = (
            self.gacha_user.timer.expires
            if self.gacha_user.timer  # If we have a pull timer already, use that
            else self.pull_message.created_at + PULL_INTERVAL
            if self.pull_message and self.pull_message.created_at + PULL_INTERVAL >= now
            else None
        )

        if next_pull:
            s.append(f'> **Next Pull in :** {timestamp_str(next_pull, with_time=True)}')
            if self.gacha_user.timer:
                s.append('-# You will be reminded in DMs when you can pull again.')

        if self.__pulls:
            burn_worth = get_burn_worths(self.__pulls)

            p_s: list[str] = []
            for k, v in burn_worth.items():
                p_s.append(f'`{k}` {RARITY_EMOJIS[k]} `[{int(v / (5 * k))}]`: `{v}` blombos')

            p_s.append(f'> Total: `{sum(burn_worth.values())}` blombos')

            embed.add_field(
                name='Estimated burn worth:',
                value=fmt_str(p_s, seperator='\n'),
            )

        embed.description = fmt_str(s, seperator='\n')

        return embed

    def _update_display(self) -> None:
        self.clear_items()

        is_timer = self.gacha_user.timer is not None

        if self.pull_message:
            self.add_item(self.remind_me_button)

            if self.__pulls_synced is False:
                self.add_item(self.sync_pulls)

        elif self.pull_message is None and is_timer:
            self.add_item(self.remind_me_button)

        self.remind_me_button.style = discord.ButtonStyle.red if is_timer else discord.ButtonStyle.green
        self.remind_me_button.label = 'Cancel reminder' if is_timer else 'Remind me'

        self.add_item(self.auto_remind_toggle)
        self.auto_remind_toggle.style = (
            discord.ButtonStyle.green if self.gacha_user.config_data['autoremind'] else discord.ButtonStyle.red
        )

    @discord.ui.button(emoji='\U000023f0', label='Remind me', style=discord.ButtonStyle.gray)
    async def remind_me_button(
        self, interaction: discord.Interaction[Mafuyu], _: discord.ui.Button[Self]
    ) -> None | discord.InteractionCallbackResponse[Mafuyu]:
        # Bad implementation incoming

        if self.gacha_user.timer:
            await self.ctx.bot.timer_manager.cancel_timer(
                user=interaction.user,
                reserved_type=ReservedTimerType.ANICORD_GACHA,
            )
            self.gacha_user.timer = None  # Timer gone.
            self._update_display()

            return await interaction.response.edit_message(
                content='Successfully removed pull reminder',
                embed=self.embed(),
                view=self,
            )

        if not self.pull_message:
            # Never will occur
            await interaction.response.defer()
            return None

        remind_time = self.pull_message.created_at + PULL_INTERVAL

        self.gacha_user.timer = await self.ctx.bot.timer_manager.create_timer(
            remind_time,
            user=interaction.user,
            reserved_type=ReservedTimerType.ANICORD_GACHA,
        )
        self._update_display()

        return await interaction.response.edit_message(
            content='Successfully created a pull reminder',
            embed=self.embed(),
            view=self,
        )

    @discord.ui.button(emoji='\U0001f4e5', label='Syncronize pulls', style=discord.ButtonStyle.grey)
    async def sync_pulls(self, interaction: discord.Interaction[Mafuyu], _: discord.ui.Button[Self]) -> None:
        assert self.pull_message is not None

        embed = self.pull_message.embeds[0]

        assert embed.description is not None

        pulls = [_ for _ in (PulledCard.parse_from_str(_) for _ in embed.description.split('\n')) if _ is not None]

        for card in pulls:
            await self.gacha_user.add_card(
                self.ctx.bot.pool,
                card=card,
                pull_message=self.pull_message,
            )
            self.__pulls.append(card)

        self.__pulls_synced = True
        self._update_display()

        await interaction.response.edit_message(
            content=f'Your {len(pulls)} cards have been added to tracking database',
            embed=self.embed(),
            view=self,
        )

    @discord.ui.button(label='Toggle auto remind')
    async def auto_remind_toggle(self, interaction: discord.Interaction[Mafuyu], _: discord.ui.Button[Self]) -> None:
        data = await self.ctx.bot.pool.fetchrow(
            """
            UPDATE GachaData
            SET
                autoremind = $1
            WHERE
                user_id = $2
            RETURNING
                *
            """,
            not self.gacha_user.config_data['autoremind'],
            interaction.user.id,
        )
        if data:
            self.gacha_user = GachaUser(self.user, timer=self.gacha_user.timer, config_data=data)
        self._update_display()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction[Mafuyu]) -> bool:
        if interaction.user and interaction.user.id == self.user.id:
            return True
        await interaction.response.send_message('This is not for you', ephemeral=True)
        return False


class GachaPersonalCardsSorter(menus.ListPageSource):
    def __init__(
        self,
        bot: Mafuyu,
        entries: list[PulledCard],
        *,
        sort_type: int,
        user: discord.User | discord.Member,
    ) -> None:
        self.bot = bot
        self.sort_type = sort_type
        self.user = user

        entries_sorted = list(enumerate(self.sort_cards(entries)))
        super().__init__(entries_sorted, per_page=10)

    async def format_page(
        self,
        _: Paginator,
        entry: list[tuple[int, list[tuple[str, int]] | list[tuple[tuple[int, str, int], int]]]],
    ) -> Embed:
        embed = Embed(
            title='Most pulled cards',
            description='These are your most pulled cards sorted according to what is selected',
            colour=self.user.color,
        )

        embed.set_thumbnail(url=self.user.display_avatar.url)

        match self.sort_type:
            case 2:
                embed.add_field(
                    name='Sorted by character',
                    value='\n'.join([f'{i[0] + 1}. **{i[1][0]}** \n  - Pulled `{i[1][1]}` times' for i in entry]),
                )
            case _:
                embed.add_field(
                    name='Sorted on per card basis',
                    value='\n'.join([
                        (
                            f'{i[0] + 1}. {RARITY_EMOJIS[int(i[1][0][2])]} **{i[1][0][0]} ({i[1][0][1]})**\n'  # pyright: ignore[reportArgumentType, reportGeneralTypeIssues]
                            f'  - Pulled `{i[1][1]}` times'
                        )
                        for i in entry
                    ]),
                )

        return embed

    def sort_cards(self, entries: list[PulledCard]) -> list[tuple[str, int]] | list[tuple[tuple[int, str, int], int]]:
        match self.sort_type:
            case 2:
                c2: dict[str, int] = {}

                for card in entries:
                    c2[card.name or 'Misc'] = c2.get(card.name or 'Misc', 0) + 1

                return sorted(c2.items(), key=operator.itemgetter(1), reverse=True)
            case _:  # Also handles 1
                c1: dict[tuple[int, str, int], int] = {}

                for card in entries:
                    c1[card.id, card.name, card.rarity] = c1.get((card.id, card.name, card.rarity), 0) + 1

                return sorted(c1.items(), key=operator.itemgetter(1), reverse=True)


class GachaStatisticsView(BaseView):
    current: list[PulledCard]
    query: datetime.timedelta | tuple[datetime.datetime | None, datetime.datetime | None] | None

    sort_type: int | None

    ctx: MafuContext

    def __init__(
        self,
        pulls: list[PulledCard],
        user: discord.User | discord.Member,
    ) -> None:
        self.pulls = pulls
        self.user = user
        self.query = None
        self.sort_type = None
        super().__init__()
        self.clear_items()
        self.add_item(self.view_select)

    @classmethod
    async def start(
        cls,
        ctx: MafuContext,
        *,
        pulls: list[PulledCard],
        user: discord.User | discord.Member,
    ) -> None:
        c = cls(pulls, user)
        c.ctx = ctx
        c.current = pulls

        embed = c.embed()

        c.message = await ctx.reply(embed=embed, view=c)

    def embed(self) -> Embed:
        burn_worths = get_burn_worths(self.current)

        embed = Embed(title=f'Pulled cards statistics for {self.user}', colour=self.user.color)
        embed.set_thumbnail(url=self.user.display_avatar.url)

        p_s: list[str] = []
        for k, v in burn_worths.items():
            p_s.append(f'`{k}` {RARITY_EMOJIS[k]} `[{int(v / (5 * k))}]`: `{v}` blombos')

        p_s.append(f'> Total `[{len(self.current)}]`: `{sum(burn_worths.values())}` blombos')

        embed.add_field(
            value=fmt_str(p_s, seperator='\n'),
        )

        if (first_sync_time := self._get_first_pull(self.pulls)) and first_sync_time and first_sync_time.message_id:
            messages: list[int] = []
            for p in self.pulls:
                if p.message_id and p.message_id not in messages:
                    messages.append(p.message_id)

            times_pulled = len(messages)

            days = (
                datetime.datetime.now(tz=datetime.UTC) - discord.utils.snowflake_time(first_sync_time.message_id)
            ).total_seconds() / 86400

            rate = times_pulled / days
            if days <= 1:
                rate = times_pulled

            embed.add_field(
                value=fmt_str(
                    (
                        '- **Syncing Since:** '
                        + timestamp_str(
                            discord.utils.snowflake_time(first_sync_time.message_id),
                            with_time=True,
                        ),
                        f'  - **Rate :** {rate:.2f} pullall(s) per day',
                        f'  - **Total :** {times_pulled} pullall(s)',
                    ),
                    seperator='\n',
                ),
            )

        return embed

    def _get_first_pull(self, pulls: list[PulledCard]) -> PulledCard | None:
        return next(
            (
                _
                for _ in sorted(
                    (_ for _ in pulls),
                    key=lambda p: discord.utils.snowflake_time(p.message_id).timestamp() if p.message_id else 0,
                )
                if _.message_id
            ),
            None,
        )

    @discord.ui.select(
        placeholder='Select a view',
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label='View total pulls with rarity and pull rate',
                value='1',
                description="See how much you've pulled and how much you've gained along with the rate of pulls per day",
                emoji=RARITY_EMOJIS[1],
            ),
            discord.SelectOption(
                label='View most owned',
                value='2',
                description="See what cards you've pulled multiple times",
                emoji=RARITY_EMOJIS[2],
            ),
        ],
    )
    async def view_select(
        self, interaction: discord.Interaction[Mafuyu], s: discord.ui.Select[Self]
    ) -> discord.InteractionCallbackResponse[Mafuyu] | None:
        if s.values:
            match int(s.values[0]):
                case 1:
                    return await interaction.response.edit_message(embed=self.embed(), view=self)
                case 2:
                    await interaction.response.defer()

                    self.sort_type = 1

                    v = Paginator(
                        GachaPersonalCardsSorter(
                            interaction.client,
                            self.current,
                            sort_type=self.sort_type,
                            user=self.user,
                        ),
                        ctx=self.ctx,
                    )

                    v.add_item(self.sort_select)

                    v.add_item(s)

                    await v.start(message=self.message)

                case _:
                    pass
        return None

    @discord.ui.select(
        placeholder='Sort by',
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label='Card',
                value='1',
                emoji=RARITY_EMOJIS[1],
            ),
            discord.SelectOption(
                label='Character',
                value='2',
                emoji=RARITY_EMOJIS[2],
            ),
        ],
    )
    async def sort_select(self, interaction: discord.Interaction[Mafuyu], s: discord.ui.Select[Self]) -> None:
        self.sort_type = int(s.values[0])
        await interaction.response.defer()

        v = Paginator(
            GachaPersonalCardsSorter(
                interaction.client,
                self.current,
                sort_type=self.sort_type,
                user=self.user,
            ),
            ctx=self.ctx,
        )

        v.add_item(s)

        v.add_item(self.view_select)

        await v.start(message=self.message)
