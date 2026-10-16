# Kulsh GPT | v2.46.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Telegram inline keyboards and menu/start text."""

import html
from typing import Any, cast

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.util import (
    DAILY_CREDITS,
    DONATE_URL,
    GITHUB_URL,
    MINI_APP_URL,
    MODEL_DISPLAY,
    MODEL_LIST,
    JsonDict,
    json_dict,
    tr,
    get_user_config,
    get_user_credits,
    model_display_name,
)
import src.util as state


class StyledButton(InlineKeyboardButton):
    def __init__(self, text: str, style: str | None = None, **kwargs: Any) -> None:
        super().__init__(text, **kwargs)  # pyright: ignore[reportUnknownMemberType]
        self.style = style

    def to_dict(self) -> JsonDict:
        d = json_dict(cast(Any, super()).to_dict())
        if self.style:
            d['style'] = self.style
        return d


def btn(text: str, style: str | None = None, **kwargs: Any) -> StyledButton:
    return StyledButton(text, style=style, **kwargs)


def mini_app_button(lang: str, is_private: bool) -> StyledButton:
    text = tr(lang, "btn_open_mini")
    if is_private:
        return btn(text, style="primary", web_app=WebAppInfo(url=MINI_APP_URL))
    return btn(text, style="primary", url=MINI_APP_URL)


def _mode_display(cfg: JsonDict, lang: str) -> str:
    mode = str(cfg.get("communication_mode", "kent"))
    if mode == "assistant":
        return tr(lang, "mode_assistant")
    if mode == "pro":
        return tr(lang, "mode_pro")
    return tr(lang, "mode_kent")


def config_text(platform: str, chat_id: int, user_id: int) -> str:
    cfg = get_user_config(platform, chat_id, user_id)
    lang = cfg.get("language", "ru")
    prompt_safe = html.escape(cfg.get("custom_prompt") or tr(lang, "cfg_prompt_default"))
    line = "---"
    on = "✅"
    off = "❌"
    theme_disp = tr(lang, "dark") if cfg.get("theme", "dark") == "dark" else tr(lang, "light")
    credits = get_user_credits(platform, user_id)
    stream_txt = f"{on if cfg.get('streaming_enabled') else off} · {'premium' if state.premium_functions_enabled else 'off'}"
    search_txt = on if cfg.get("web_search_enabled", True) else off
    mode_txt = _mode_display(cfg, lang)
    return (
        f"# {tr(lang, 'cfg_title')}\n\n{line}\n\n"
        f"{tr(lang, 'cfg_lang')}: {tr(lang, 'russian') if lang == 'ru' else tr(lang, 'english')}\n"
        f"{tr(lang, 'cfg_theme')}: {theme_disp}\n"
        f"{tr(lang, 'cfg_mode')}: {mode_txt}\n"
        f"{tr(lang, 'cfg_model')}: {model_display_name(cfg.get('model'), lang)}\n"
        f"{tr(lang, 'cfg_temp_short')}: `{cfg.get('temperature', 0.9)}`\n"
        f"{tr(lang, 'cfg_sep')}: {on if cfg.get('separate_enabled', True) else off}\n"
        f"{tr(lang, 'cfg_stream')}: {stream_txt}\n"
        f"{tr(lang, 'cfg_stickers')}: {on if cfg.get('stickers_enabled', True) else off}\n"
        f"{tr(lang, 'cfg_autoreply')}: {on if cfg.get('random_reply_enabled') else off}\n"
        f"{tr(lang, 'cfg_random')}: {on if cfg.get('random_messages_enabled', True) else off}\n"
        f"{tr(lang, 'cfg_websearch')}: {search_txt}\n"
        f"{tr(lang, 'cfg_credits_label')}: `{credits}/{DAILY_CREDITS}`\n\n"
        f"{line}\n\n"
        f"{tr(lang, 'cfg_prompt_label')}: {prompt_safe}"
    )


def build_main_config_keyboard(platform: str, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    cfg = get_user_config(platform, chat_id, user_id)
    lang = cfg.get("language", "ru")
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "cfg_lang"), style=None, callback_data="cfg:lang"),
        btn(tr(lang, "cfg_theme"), style=None, callback_data="cfg:theme"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(f"{tr(lang, 'cfg_mode')}: {_mode_display(cfg, lang)}",
            style="primary", callback_data="cfg:mode"),
        btn(f"{tr(lang, 'cfg_model')}: {model_display_name(cfg.get('model'), lang)}",
            style=None, callback_data="cfg:model"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(f"{tr(lang, 'cfg_temp_short')}: {cfg.get('temperature', 0.9)}",
            style=None, callback_data="cfg:temp"),
        btn(f"{tr(lang, 'cfg_websearch')}: {'✅' if cfg.get('web_search_enabled', True) else '❌'}",
            style=None, callback_data="cfg:websearch"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(f"{tr(lang, 'cfg_sep')}: {'✅' if cfg.get('separate_enabled', True) else '❌'}",
            style=None, callback_data="cfg:separate"),
        btn(f"{tr(lang, 'cfg_stream')}: {'✅' if cfg.get('streaming_enabled') else '❌'}",
            style=None, callback_data="cfg:streaming"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(f"{tr(lang, 'cfg_stickers')}: {'✅' if cfg.get('stickers_enabled', True) else '❌'}",
            style=None, callback_data="cfg:stickers"),
        btn(f"{tr(lang, 'cfg_autoreply')}: {'✅' if cfg.get('random_reply_enabled') else '❌'}",
            style=None, callback_data="cfg:autoreply"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(f"{tr(lang, 'cfg_random')}: {'✅' if cfg.get('random_messages_enabled', True) else '❌'}",
            style=None, callback_data="cfg:random"),
        btn(tr(lang, "cfg_edit_prompt"), style="primary", callback_data="cfg:prompt"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "cfg_reset_memory"), style="danger", callback_data="cfg:reset_memory"),
        btn(tr(lang, "cfg_reset_prompt"), style="danger", callback_data="cfg:reset_prompt"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "cfg_apply_close"), style="success", callback_data="cfg:apply")
    )
    return kb


def build_model_keyboard(platform: str, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    cfg = get_user_config(platform, chat_id, user_id)
    lang = cfg.get("language", "ru")
    cur = cfg.get("model")
    kb = InlineKeyboardMarkup()
    auto_mark = "🔘" if not cur else "▫️"
    kb.row(btn(f"{auto_mark} {tr(lang, 'cfg_auto')}", style=None, callback_data="cfg:model_set:auto"))  # pyright: ignore[reportUnknownMemberType]
    row: list[StyledButton] = []
    for idx, model in enumerate(MODEL_LIST):
        mark = "🔘" if cur == model else "▫️"
        row.append(btn(f"{mark} {MODEL_DISPLAY.get(model, model)}", style=None, callback_data=f"cfg:model_set:{idx}"))
        if len(row) == 2:
            kb.row(*row)  # pyright: ignore[reportUnknownMemberType]
            row = []
    if row:
        kb.row(*row)  # pyright: ignore[reportUnknownMemberType]
    kb.row(btn(tr(lang, "cfg_back"), style="primary", callback_data="cfg:model_back"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def build_mode_keyboard(platform: str, chat_id: int, user_id: int, is_private: bool = True) -> InlineKeyboardMarkup:
    cfg = get_user_config(platform, chat_id, user_id)
    lang = cfg.get("language", "ru")
    cur = str(cfg.get("communication_mode", "kent"))
    kb = InlineKeyboardMarkup()

    def mark(mode: str) -> str:
        return "🔘" if cur == mode else "▫️"

    kb.row(btn(f"{mark('kent')} {tr(lang, 'mode_kent')}",  # pyright: ignore[reportUnknownMemberType]
               style="primary" if cur == "kent" else None,
               callback_data="cfg:mode_set:kent"))
    kb.row(btn(f"{mark('assistant')} {tr(lang, 'mode_assistant')}",  # pyright: ignore[reportUnknownMemberType]
               style="primary" if cur == "assistant" else None,
               callback_data="cfg:mode_set:assistant"))
    if is_private:
        kb.row(btn(f"{mark('pro')} {tr(lang, 'mode_pro')}",  # pyright: ignore[reportUnknownMemberType]
                   style="primary" if cur == "pro" else None,
                   callback_data="cfg:mode_set:pro"))
    kb.row(btn(tr(lang, "cfg_back_slash"), style="primary", callback_data="cfg:sub_back"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def build_lang_keyboard(platform: str, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    cfg = get_user_config(platform, chat_id, user_id)
    cur = cfg.get("language", "ru")
    lang = cfg.get("language", "ru")
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(f"{'🔘' if cur == 'ru' else '▫️'} Русский 🇷🇺",
            style="primary" if cur == "ru" else None, callback_data="cfg:lang_set:ru"),
        btn(f"{'🔘' if cur == 'en' else '▫️'} English 🇬🇧",
            style="primary" if cur == "en" else None, callback_data="cfg:lang_set:en"),
    )
    kb.row(btn(tr(lang, "cfg_back_slash"), style="primary", callback_data="cfg:sub_back"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def build_theme_keyboard(platform: str, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    cfg = get_user_config(platform, chat_id, user_id)
    cur = cfg.get("theme", "dark")
    lang = cfg.get("language", "ru")
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(f"{'🔘' if cur == 'dark' else '▫️'} {'Тёмная 🌑' if lang == 'ru' else 'Dark 🌑'}",
            style="primary" if cur == "dark" else None, callback_data="cfg:theme_set:dark"),
        btn(f"{'🔘' if cur == 'light' else '▫️'} {'Светлая ☀️' if lang == 'ru' else 'Light ☀️'}",
            style="primary" if cur == "light" else None, callback_data="cfg:theme_set:light"),
    )
    kb.row(btn(tr(lang, "cfg_back_slash"), style="primary", callback_data="cfg:sub_back"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def build_temp_keyboard(platform: str, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    cfg = get_user_config(platform, chat_id, user_id)
    cur = cfg.get("temperature", 0.9)
    lang = cfg.get("language", "ru")
    kb = InlineKeyboardMarkup()
    values = [0.2, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5]
    row: list[StyledButton] = []
    for v in values:
        mark = "🔘" if abs(cur - v) < 0.01 else "▫️"
        row.append(btn(f"{mark} {v}", style=None, callback_data=f"cfg:temp_set:{v}"))
    kb.row(*row[:4])  # pyright: ignore[reportUnknownMemberType]
    kb.row(*row[4:])  # pyright: ignore[reportUnknownMemberType]
    kb.row(btn(tr(lang, "cfg_back_slash"), style="primary", callback_data="cfg:sub_back"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def model_picker_text(platform: str, chat_id: int, user_id: int) -> str:
    cfg = get_user_config(platform, chat_id, user_id)
    lang = cfg.get("language", "ru")
    return (
        f"# {tr(lang, 'cfg_choose_model')}\n\n---\n\n"
        f"{tr(lang, 'cfg_current')}: {model_display_name(cfg.get('model'), lang)}\n\n"
        f"**{tr(lang, 'cfg_auto')}** — {tr(lang, 'cfg_auto_hint')}"
    )


def mode_picker_text(platform: str, chat_id: int, user_id: int, is_private: bool = True) -> str:
    cfg = get_user_config(platform, chat_id, user_id)
    lang = cfg.get("language", "ru")
    lines = [
        f"# {tr(lang, 'cfg_choose_mode')}",
        "",
        "---",
        "",
        f"- **{tr(lang, 'mode_kent')}** — {tr(lang, 'mode_kent_hint')}",
        f"- **{tr(lang, 'mode_assistant')}** — {tr(lang, 'mode_assistant_hint')}",
    ]
    if is_private:
        lines.append(f"- **{tr(lang, 'mode_pro')}** — {tr(lang, 'mode_pro_hint')}")
    return "\n".join(lines)


# ============================================================
# МЕНЮ / START
# ============================================================
def build_menu_text(lang: str) -> str:
    # Таблица: K | *U* | L | *S* | H  → K, L, H — без заливки (is_header=False),
    # U и S — с заливкой (is_header=True через *одинарные* звёздочки).
    return (
        "|K|*U*|L|*S*|H|\n\n"
        f"# {tr(lang, 'menu_title')}\n\n"
        f"---\n\n"
        f"{tr(lang, 'menu_intro')}\n\n"
        f"**{tr(lang, 'menu_available')}**\n\n"
        f"- {tr(lang, 'menu_mini_app')}\n"
        f"- {tr(lang, 'menu_settings_item')}\n"
        f"- {tr(lang, 'menu_commands')}\n"
        f"- {tr(lang, 'menu_donate_item')}\n"
        f"- {tr(lang, 'menu_github_item')}"
    )


def build_start_text(lang: str) -> str:
    return (
        f"# {tr(lang, 'start_title')}\n\n"
        f"---\n\n"
        f"{tr(lang, 'start_intro')}\n\n"
        f"**{tr(lang, 'start_where')}**\n\n"
        f"- {tr(lang, 'start_mini_app')}\n"
        f"- {tr(lang, 'start_menu')}\n"
        f"- {tr(lang, 'start_config')}\n\n"
        f"🍷🗿 {MINI_APP_URL}"
    )


def build_menu_keyboard(lang: str, is_private: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(mini_app_button(lang, is_private))  # pyright: ignore[reportUnknownMemberType]
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "btn_settings"), style="success", callback_data="menu:settings"),
        btn(tr(lang, "btn_commands"), style=None, callback_data="menu:help"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "btn_donate"), style=None, url=DONATE_URL),
        btn(tr(lang, "btn_github"), style=None, url=GITHUB_URL),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "btn_close"), style="danger", callback_data="menu:close")
    )
    return kb


def build_start_keyboard(lang: str, is_private: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(mini_app_button(lang, is_private))  # pyright: ignore[reportUnknownMemberType]
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "btn_menu"), style="success", callback_data="menu:open"),
        btn(tr(lang, "btn_settings"), style=None, callback_data="menu:settings"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(tr(lang, "btn_donate"), style=None, url=DONATE_URL),
        btn(tr(lang, "btn_github"), style=None, url=GITHUB_URL),
    )
    return kb
