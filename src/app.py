# Kulsh GPT | v2.47.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Process entry: build the bots, register handlers, run both platforms."""

import asyncio
from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands
from telebot import types as types
from telebot.async_telebot import AsyncTeleBot

from src import discord_cmds, discord_msg, loops, media, rich, telegram, billing
from src import admin_panel
from src.util import (
    AI_KEYS,
    ETAGEONE_API_KEY,
    DISCORD_TOKEN,
    DONATIONALERTS_TOKEN,
    DS_ALLOWED_GUILD_ID,
    TG_TOKEN,
    voice_recognition_enabled,
    typed_decorator,
    logger,
    msk_datetime_str,
    save_all_state,
)

if not AI_KEYS:
    logger.critical("❌ Не найден ни один API ключ Gemini!")
    raise SystemExit(1)
if not ETAGEONE_API_KEY:
    logger.critical("❌ Не найден ETAGEONE_API_KEY!")
    raise SystemExit(1)

tg_bot = AsyncTeleBot(TG_TOKEN)

# Без privileged intents (members intent требует включения в Developer Portal).
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

ds_bot = discord.Client(intents=intents)
ds_tree = app_commands.CommandTree(ds_bot)


async def _ds_interaction_check(interaction: discord.Interaction) -> bool:
    if admin_panel.is_blocked("ds", interaction.user.id) and not admin_panel.is_admin_ds(interaction.user.id):
        try:
            await interaction.response.send_message("Доступ ограничен.", ephemeral=True)
        except Exception:
            pass
        return False
    admin_panel.touch_user(
        "ds", interaction.user.id,
        getattr(interaction.user, "display_name", "") or interaction.user.name,
    )
    return True


ds_tree.interaction_check = _ds_interaction_check  # type: ignore[method-assign]

telegram.bind(tg_bot)
rich.bind(tg_bot)
discord_cmds.bind(ds_bot)
loops.bind(ds_bot, tg_bot)


def _callback_startswith(prefix: str) -> Callable[[types.CallbackQuery], bool]:
    def _filter(call: types.CallbackQuery) -> bool:
        return bool(call.data and call.data.startswith(prefix))
    return _filter


def _always_true(_query: types.PreCheckoutQuery) -> bool:
    return True


def _message_has_text(message: types.Message) -> bool:
    return message.text is not None


def register_telegram() -> None:
    deco = typed_decorator
    def _guard_msg(fn: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapped(message: types.Message, *args: Any, **kwargs: Any) -> Any:
            if await admin_panel.take_admin_input(tg_bot, message):
                return None
            user = getattr(message, "from_user", None)
            if user and admin_panel.is_blocked("tg", user.id) and not admin_panel.is_admin_tg(user.id):
                return None
            if user and not getattr(user, "is_bot", False):
                admin_panel.touch_user("tg", user.id, getattr(user, "full_name", "") or "")
            return await fn(message, *args, **kwargs)
        return wrapped

    def _guard_call(fn: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapped(call: types.CallbackQuery, *args: Any, **kwargs: Any) -> Any:
            user = call.from_user
            if admin_panel.is_blocked("tg", user.id) and not admin_panel.is_admin_tg(user.id):
                try:
                    await tg_bot.answer_callback_query(call.id)
                except Exception:
                    pass
                return None
            return await fn(call, *args, **kwargs)
        return wrapped

    deco(getattr(tg_bot, "callback_query_handler"))(func=_callback_startswith("cfg:"))(_guard_call(telegram.handle_cfg_callback))
    deco(getattr(tg_bot, "callback_query_handler"))(func=_callback_startswith("menu:"))(_guard_call(telegram.handle_menu_callback))
    deco(getattr(tg_bot, "callback_query_handler"))(func=_callback_startswith("adm:"))(telegram.handle_admin_callback)
    deco(getattr(tg_bot, "message_handler"))(commands=["start"])(_guard_msg(telegram.handle_start))
    deco(getattr(tg_bot, "message_handler"))(commands=["menu"])(_guard_msg(telegram.handle_menu))
    deco(getattr(tg_bot, "message_handler"))(commands=["help"])(_guard_msg(telegram.handle_help))
    deco(getattr(tg_bot, "message_handler"))(commands=["status"])(_guard_msg(telegram.handle_status))
    deco(getattr(tg_bot, "message_handler"))(commands=["donate"])(_guard_msg(telegram.handle_donate))
    deco(getattr(tg_bot, "message_handler"))(commands=["donate_stars"])(_guard_msg(telegram.handle_donate_stars))
    deco(getattr(tg_bot, "message_handler"))(commands=["credits"])(_guard_msg(telegram.handle_credits))
    deco(getattr(tg_bot, "message_handler"))(commands=["balance"])(_guard_msg(telegram.handle_balance))
    deco(getattr(tg_bot, "message_handler"))(commands=["profile"])(_guard_msg(telegram.handle_profile))
    deco(getattr(tg_bot, "message_handler"))(commands=["support"])(_guard_msg(telegram.handle_support))
    deco(getattr(tg_bot, "message_handler"))(commands=["adminpanel12345"])(_guard_msg(telegram.handle_admin_secret))
    deco(getattr(tg_bot, "message_handler"))(commands=["togglepremiumfunctionsadmin"])(_guard_msg(telegram.handle_toggle_premium))
    deco(getattr(tg_bot, "pre_checkout_query_handler"))(func=_always_true)(telegram.handle_pre_checkout)
    deco(getattr(tg_bot, "message_handler"))(content_types=["successful_payment"])(telegram.handle_successful_payment)
    deco(getattr(tg_bot, "message_handler"))(content_types=["photo", "video", "animation", "document", "sticker"])(_guard_msg(media.handle_tg_media))
    deco(getattr(tg_bot, "message_handler"))(func=_message_has_text, content_types=["text"])(_guard_msg(media.handle_tg_text))


def register_discord() -> None:
    tree = ds_tree
    tree.command(name="start", description="Greeting / Приветствие")(discord_cmds.ds_slash_start)
    tree.command(name="menu", description="Menu / Меню")(discord_cmds.ds_slash_menu)
    tree.command(name="help", description="Command list / Список команд")(discord_cmds.ds_slash_help)
    tree.command(name="status", description="Bot status / Состояние бота")(discord_cmds.ds_slash_status)
    tree.command(name="donate", description="Support the project / Поддержать проект")(discord_cmds.ds_slash_donate)
    tree.command(name="credits", description="Credits balance / Баланс кредитов")(discord_cmds.ds_slash_credits)
    tree.command(name="balance", description="Balance and top-up / Баланс и пополнение")(discord_cmds.ds_slash_balance)
    tree.command(name="profile", description="Profile / Профиль")(discord_cmds.ds_slash_profile)
    tree.command(name="support", description="Contact support / Поддержка")(discord_cmds.ds_slash_support)
    tree.command(name="config", description="Channel settings / Настройки канала")(discord_cmds.ds_slash_config)
    tree.command(name="logs", description="Server logs (admins) / Логи сервера (админам)")(discord_cmds.ds_slash_logs)
    tree.command(name="groupinfo", description="Server info / Инфо о сервере")(discord_cmds.ds_slash_groupinfo)

    @tree.command(name="avatar", description="Describe avatar / Описать аватарку")
    @app_commands.describe(user="Whose avatar to describe / Чью аватарку описать")
    async def avatar(interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        await discord_cmds.ds_slash_avatar(interaction, user)

    @tree.command(name="recall", description="Recall recent media / Вспомнить недавние медиа")
    @app_commands.describe(count="How many last items / Сколько последних элементов")
    async def recall(interaction: discord.Interaction, count: int = 3) -> None:
        await discord_cmds.ds_slash_recall(interaction, count)

    @tree.command(name="search", description="Web search / Поиск в интернете")
    @app_commands.describe(query="What to search / Что искать")
    async def search(interaction: discord.Interaction, query: str) -> None:
        await discord_cmds.ds_slash_search(interaction, query)

    @tree.command(name="chart", description="Generate infographic / Сгенерировать инфографику")
    @app_commands.describe(description="Describe the chart / Опиши график")
    async def chart(interaction: discord.Interaction, description: str) -> None:
        await discord_cmds.ds_slash_chart(interaction, description)

    @tree.command(name="psl", description="Looksmaxxing analysis / Оценка внешности")
    @app_commands.describe(image="Photo / Фото", advice="Include advice / Показать рекомендации")
    async def psl(interaction: discord.Interaction, image: discord.Attachment, advice: bool = False) -> None:
        await discord_cmds.ds_slash_psl(interaction, image, advice)

    @tree.command(name="battle", description="Two-photo battle / Баттл двух фото")
    @app_commands.describe(image1="First photo / Первое фото", image2="Second photo / Второе фото")
    async def battle(interaction: discord.Interaction, image1: discord.Attachment, image2: discord.Attachment) -> None:
        await discord_cmds.ds_slash_battle(interaction, image1, image2)

    @tree.command(name="femboy", description="Femboy Rate / Оценка фембойности")
    @app_commands.describe(image="Photo / Фото", advice="Include advice / Показать рекомендации")
    async def femboy(interaction: discord.Interaction, image: discord.Attachment, advice: bool = False) -> None:
        await discord_cmds.ds_slash_femboy(interaction, image, advice)

    @tree.command(name="femboy-battle", description="Femboy battle / Фембой-баттл")
    @app_commands.describe(image1="First photo / Первое фото", image2="Second photo / Второе фото")
    async def femboy_battle(interaction: discord.Interaction, image1: discord.Attachment, image2: discord.Attachment) -> None:
        await discord_cmds.ds_slash_femboy_battle(interaction, image1, image2)

    @tree.command(name="userinfo", description="User profile info / Инфо о пользователе")
    @app_commands.describe(user="User to inspect / Пользователь (оставь пусто для себя)")
    async def userinfo(interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        await discord_cmds.ds_slash_userinfo(interaction, user)

    ds_bot.event(discord_msg.on_message)


def register() -> None:
    register_telegram()
    register_discord()


def _smoke_check() -> None:  # pyright: ignore[reportUnusedFunction]
    def _need(mod: Any, name: str) -> None:
        obj = getattr(mod, name, None)
        if obj is None:
            raise RuntimeError(f"{getattr(mod, '__name__', '?')}.{name} отсутствует")
        if not callable(obj):
            raise RuntimeError(f"{getattr(mod, '__name__', '?')}.{name} — не callable")

    for name in ("bind", "handle_start", "handle_menu", "handle_help", "handle_status",
                 "handle_donate", "handle_donate_stars", "handle_credits",
                 "handle_toggle_premium", "handle_pre_checkout", "handle_successful_payment",
                 "handle_cfg_callback", "handle_menu_callback"):
        _need(telegram, name)

    for name in ("bind", "send_tg_html", "reply_tg_html", "send_formatted", "send_rich_message"):
        _need(rich, name)

    for name in ("handle_tg_media", "handle_tg_text"):
        _need(media, name)

    _need(discord_msg, "on_message")

    for name in ("bind", "ds_slash_start", "ds_slash_menu", "ds_slash_help", "ds_slash_status",
                 "ds_slash_donate", "ds_slash_credits", "ds_slash_config", "ds_slash_logs",
                 "ds_slash_groupinfo", "ds_slash_userinfo", "ds_slash_avatar", "ds_slash_recall",
                 "ds_slash_search", "ds_slash_chart", "ds_slash_psl", "ds_slash_battle",
                 "ds_slash_femboy", "ds_slash_femboy_battle"):
        _need(discord_cmds, name)

    _need(loops, "bind")

    for optional_name in ("random_post_loop", "series_reminder_loop",
                          "donation_alerts_listener", "periodic_config_save_loop"):
        if getattr(loops, optional_name, None) is None:
            print(f"WARN: loops.{optional_name} отсутствует — соответствующая функция отключена")


async def main() -> None:
    register()

    try:
        from src import cloud
        if cloud.enabled():
            cloud.migrate_legacy(billing.balances)
            logger.info("☁️ Общее хранилище аккаунтов подключено")
        else:
            logger.warning("☁️ Общее хранилище не настроено (KV_REST_API_URL/TOKEN) — баланс локальный")
    except Exception as e:
        logger.warning(f"cloud init: {e}")

    if callable(getattr(loops, "random_post_loop", None)):
        asyncio.create_task(loops.random_post_loop())
    else:
        logger.warning("random_post_loop отсутствует — пропускаю")

    if callable(getattr(loops, "periodic_config_save_loop", None)):
        asyncio.create_task(loops.periodic_config_save_loop())
    else:
        logger.warning("⚠️ periodic_config_save_loop отсутствует — настройки НЕ будут сохраняться автоматически")

    @ds_bot.event
    async def on_ready() -> None:
        logger.info(f"Discord {ds_bot.user} запущен, discord.py {discord.__version__}")
        if not voice_recognition_enabled:
            logger.info("ℹ️ Распознавание голоса отключено")
        try:
            synced = await ds_tree.sync()
            logger.info(f"Синхронизировано slash-команд (глобально): {len(synced)}")
        except Exception as e:
            logger.error(f"Не удалось синхронизировать slash-команды (global): {e}")
        if DS_ALLOWED_GUILD_ID:
            try:
                guild = discord.Object(id=DS_ALLOWED_GUILD_ID)
                ds_tree.copy_global_to(guild=guild)
                synced_g = await ds_tree.sync(guild=guild)
                logger.info(f"Синхронизировано slash-команд (guild {DS_ALLOWED_GUILD_ID}): {len(synced_g)}")
            except Exception as e:
                logger.error(f"Не удалось синхронизировать slash-команды (guild): {e}")
        _series_loop = getattr(loops, "series_reminder_loop", None)
        if callable(_series_loop):
            asyncio.create_task(loops.series_reminder_loop())
        if DONATIONALERTS_TOKEN:
            _don_loop = getattr(loops, "donation_alerts_listener", None)
            if callable(_don_loop):
                asyncio.create_task(loops.donation_alerts_listener())

    async def start_discord() -> None:
        try:
            await ds_bot.start(DISCORD_TOKEN)
        except discord.PrivilegedIntentsRequired as e:
            logger.critical(
                "❌ Discord требует privileged intents, которые не включены в Developer Portal.\n"
                f"Детали: {e}"
            )
            raise
        except Exception as e:
            logger.error(f"❌ Discord start: {e}")
            raise

    async def start_telegram() -> None:
        ru_commands = [
            types.BotCommand("start", "🚀 Запустить Кульша"),
            types.BotCommand("menu", "📖 Открыть меню"),
            types.BotCommand("balance", "💳 Баланс и пополнение"),
            types.BotCommand("profile", "👤 Профиль и статистика"),
            types.BotCommand("support", "💬 Написать в поддержку"),
            types.BotCommand("help", "📚 Список всех команд"),
            types.BotCommand("status", "🟢 Состояние бота"),
            types.BotCommand("credits", "💎 Дневные кредиты"),
            types.BotCommand("donate", "❤️ Поддержать проект"),
        ]
        en_commands = [
            types.BotCommand("start", "🚀 Start Kulsh"),
            types.BotCommand("menu", "📖 Open the menu"),
            types.BotCommand("balance", "💳 Balance and top-up"),
            types.BotCommand("profile", "👤 Profile and stats"),
            types.BotCommand("support", "💬 Contact support"),
            types.BotCommand("help", "📚 All commands"),
            types.BotCommand("status", "🟢 Bot status"),
            types.BotCommand("credits", "💎 Daily credits"),
            types.BotCommand("donate", "❤️ Support the project"),
        ]
        try:
            await tg_bot.set_my_commands(ru_commands)
            await tg_bot.set_my_commands(en_commands, language_code="en")
            logger.info("Список команд Telegram обновлён")
        except Exception as e:
            logger.warning(f"set_my_commands: {e}")
        await tg_bot.polling(non_stop=True)

    asyncio.create_task(billing.donation_poll_loop())
    await asyncio.gather(start_discord(), start_telegram())


def run() -> None:
    logger.info(f">>> 🍷🗿 Кульш в эфире. МСК: {msk_datetime_str()}")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        # При выходе обязательно сохраняем всё состояние на диск,
        # чтобы не терять настройки при рестартах.
        try:
            save_all_state()
            logger.info("💾 Состояние сохранено перед выходом")
        except Exception as e:
            logger.warning(f"save on exit: {e}")


if __name__ == "__main__":
    run()