# Kulsh GPT | v2.46.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Russian/English UI strings."""

import re
from typing import Any

TEXTS: dict[str, tuple[str, str]] = {
    "cfg_title":               ("⚙️ Настройки", "⚙️ Settings"),
    "cfg_lang":                ("🌐 Язык", "🌐 Language"),
    "cfg_theme":               ("🌓 Тема", "🌓 Theme"),
    "cfg_model":               ("🧠 Модель", "🧠 Model"),
    "cfg_mode":                ("🧩 Режим", "🧩 Mode"),
    "cfg_temp_short":          ("🎛 Темп.", "🎛 Temp"),
    "cfg_sep":                 ("💬 Разбивка", "💬 Split"),
    "cfg_stream":              ("📡 Стриминг", "📡 Streaming"),
    "cfg_stickers":            ("🎨 Стикеры", "🎨 Stickers"),
    "cfg_autoreply":           ("🗣 Автоотв.", "🗣 Auto-reply"),
    "cfg_random":              ("📢 Рандом", "📢 Random"),
    "cfg_reactions":           ("😀 Реакции", "😀 Reactions"),
	"cfg_reactions_on":        ("Реакции: включены ✅", "Reactions: on ✅"),
	"cfg_reactions_off":       ("Реакции: выключены ❌", "Reactions: off ❌"),
	"ds_setting_reactions":    ("Реакции: {0}", "Reactions: {0}"),
    "cfg_websearch":           ("🔎 Веб-поиск", "🔎 Web search"),
    "cfg_edit_prompt":         ("📝 Изменить промпт", "📝 Edit prompt"),
    "cfg_reset_memory":        ("🧹 Сбросить память", "🧹 Reset memory"),
    "cfg_reset_prompt":        ("♻️ Сбросить промпт", "♻️ Reset prompt"),
    "cfg_apply_close":         ("✅ Применить и закрыть", "✅ Apply & close"),
    "cfg_back":                ("🔙 Назад", "🔙 Back"),
    "cfg_back_slash":          ("🔙 Назад / Back", "🔙 Back"),
    "cfg_auto":                ("🎲 Авто", "🎲 Auto"),
    "cfg_choose_model":        ("🧠 Выбор модели", "🧠 Model selection"),
    "cfg_choose_mode":         ("🧩 Выбор режима общения", "🧩 Communication mode"),
    "cfg_current":             ("Текущая", "Current"),
    "cfg_auto_hint":           ("перебор всех моделей", "try all models"),
    "cfg_prompt_label":        ("📝 Кастомный промпт", "📝 Custom prompt"),
    "cfg_prompt_default":      ("стандартный", "default"),
    "cfg_credits_label":       ("💎 Кредиты", "💎 Credits"),

    "cfg_updated":             ("Обновлено", "Updated"),
    "cfg_model_auto":          ("Модель: авто", "Model: auto"),
    "cfg_model_set":           ("Модель: {0}", "Model: {0}"),
    "cfg_lang_set_ru":         ("Язык: русский 🇷🇺", "Language: Russian 🇷🇺"),
    "cfg_lang_set_en":         ("Язык: английский 🇬🇧", "Language: English 🇬🇧"),
    "cfg_theme_dark":          ("Тема: тёмная 🌑", "Theme: dark 🌑"),
    "cfg_theme_light":         ("Тема: светлая ☀️", "Theme: light ☀️"),
    "cfg_temp":                ("🌡 {0}", "🌡 {0}"),
    "cfg_prompt_reset":        ("Промпт сброшен", "Prompt reset"),
    "cfg_memory_reset":        ("Память сброшена", "Memory reset"),
    "cfg_done":                ("Готово ✅", "Done ✅"),
    "cfg_mutex": (
        "«Разбивка» и «Стриминг» взаимно исключаемы. Сначала отключи вторую настройку.",
        "Split and Streaming are mutually exclusive. Disable the other first.",
    ),
    "cfg_premium_off":         ("расширенные функции отключены", "extended features disabled"),
    "cfg_not_yours":           ("это не твои настройки 🤚", "not your settings 🤚"),
    "cfg_edit_prompt_ask": (
        "Отправьте новый кастомный промпт ответом на это сообщение.\n"
        "Для отмены — ответьте <code>отмена</code> или <code>cancel</code>.",
        "Send the new custom prompt as a reply to this message.\n"
        "To cancel — reply <code>отмена</code> or <code>cancel</code>.",
    ),
    "prompt_saved":            ("Промпт сохранён ({0} символов)", "Prompt saved ({0} chars)"),
    "prompt_cancelled":        ("Изменение промпта отменено", "Prompt edit cancelled"),

    # ---- Режимы общения ----
    "mode_kent":               ("kulsh.ai〢Кент", "kulsh.ai〢Kent"),
    "mode_assistant":          ("kulsh.ai〢Ассистент", "kulsh.ai〢Assistant"),
    "mode_pro":                ("kulsh.ai〢Pro", "kulsh.ai〢Pro"),
    "mode_kent_hint":          ("По умолчанию", "Default"),
    "mode_assistant_hint":     ("Помощь по делу, структура", "Helpful, structured"),
    "mode_pro_hint":           ("Размышление и перепроверка (только в ЛС)", "Reasoning & self-check (DM only)"),
    "mode_set":                ("Режим: {0}", "Mode: {0}"),
    "mode_need_dm":            ("Режим Pro доступен только в личном чате с ботом.", "Pro mode is only available in DM."),

    # ---- Меню ----
    "menu_title":              ("Кульш AI — главное меню", "Kulsh AI — Main Menu"),
    "menu_intro": (
        "Открытая языковая модель с набором встроенных инструментов, "
        "веб-поиском и генерацией инфографики.",
        "Open-source language model with built-in tools, web search and infographic generation.",
    ),
    "menu_available":          ("Доступно:", "Available:"),
    "menu_mini_app":           ("Mini App — расширенный чат с ИИ",
                                "Mini App — extended AI chat"),
    "menu_settings_item":      ("Настройки — язык, тема, модель, промпт, поиск",
                                "Settings — language, theme, model, prompt, search"),
    "menu_commands":           ("Команды — полный список возможностей",
                                "Commands — full feature list"),
    "menu_donate_item":        ("Донат — поддержка разработки", "Donate — support development"),
    "menu_github_item":        ("GitHub — исходный код проекта", "GitHub — project source code"),

    # ---- START ----
    "start_title":             ("🍷🗿 Кульш на связи", "🍷🗿 Kulsh is online"),
    "start_intro": (
        "Открытая языковая модель с анализом изображений, веб-поиском, "
        "генерацией инфографики и настройкой под себя. Telegram и Discord.",
        "Open-source language model with image analysis, web search, "
        "infographic generation and personal config. Telegram and Discord.",
    ),
    "start_where":             ("🚀 С чего начать:", "🚀 Where to start:"),
    "start_mini_app":          ("Mini App — расширенный чат с ИИ",
                                "Mini App — extended AI chat"),
    "start_menu":              ("Меню — все разделы и настройки",
                                "Menu — all sections and settings"),
    "start_config":            ("<code>кульш конфиг</code> — тонкая настройка под тебя",
                                "<code>kulsh config</code> — tune the bot"),

    "btn_open_mini":           ("🚀 Открыть Mini App", "🚀 Open Mini App"),
    "btn_settings":            ("⚙️ Настройки", "⚙️ Settings"),
    "btn_commands":            ("📖 Команды", "📖 Commands"),
    "btn_menu":                ("📖 Меню", "📖 Menu"),
    "btn_donate":              ("💎 Донат", "💎 Donate"),
    "btn_github":              ("🔗 GitHub", "🔗 GitHub"),
    "btn_close":               ("❌ Закрыть", "❌ Close"),

    # ---- ДОНАТ ----
    "donate_title":            ("💎 Поддержать Кульша", "💎 Support Kulsh"),
    "donate_intro": (
        "💖 Донаты идут на серверы, домены и дальнейшую разработку проекта.",
        "💖 Donations go to servers, domains and further development.",
    ),
    "donate_methods":          ("💰 Способы:", "💰 Methods:"),
    "donate_online":           ("Онлайн-донат", "Online donation"),
    "donate_stars_hint":       ("Telegram Stars — <code>/donate_stars &lt;N&gt;</code>",
                                "Telegram Stars — <code>/donate_stars &lt;N&gt;</code>"),
    "donate_stars_need":       ("Укажите количество звёзд: <code>/donate_stars 100</code>",
                                "Specify star amount: <code>/donate_stars 100</code>"),
    "donate_stars_bad":        ("Неверное количество звёзд.", "Invalid star amount."),
    "donate_thanks":           ("🍷🗿 Спасибо за {0} звёзд, кент!", "🍷🗿 Thanks for {0} stars, mate!"),
    "donate_invoice_fail":     ("Не удалось выставить счёт: {0}", "Failed to create invoice: {0}"),
    "credits_balance":         ("💎 Кредиты: {0}/{1}", "💎 Credits: {0}/{1}"),

    "top_donators_title":      ("🏆 Топ донатеров:", "🏆 Top donators:"),
    "top_donators_empty":      ("Пока никто не донатил. Будь первым, бро 🍷🗿\n{0}",
                                "No donations yet. Be the first, bro 🍷🗿\n{0}"),
    "top_donators_item":       ("{0}. {1} — {2} очков", "{0}. {1} — {2} points"),

    "avatar_fail":             ("не смог получить аватарку", "failed to fetch avatar"),
    "avatar_none":             ("у {0} аватарки нет, пусто", "{0} has no avatar"),
    "recall_fail":             ("не нашёл ничего в памяти", "nothing found in memory"),

    # ---- PSL ----
    "psl_need_photo":          ("📸 Жду фото для анализа. Отправь его с пометкой 'looksmaxxing'.",
                                "📸 Waiting for a photo. Send it marked 'looksmaxxing'."),
    "psl_analyzing":           ("⏳ Анализирую внешность...", "⏳ Analyzing your face..."),
    "psl_report":              ("📊 Результаты looksmaxxing", "📊 Looksmaxxing results"),
    "psl_title":               ("📊 РЕЗУЛЬТАТЫ LOOKSMAXXING", "📊 LOOKSMAXXING RESULTS"),
    "psl_gender":              ("🧬 Пол:", "🧬 Gender:"),
    "psl_score":               ("📈 PSL:", "📈 PSL:"),
    "psl_tier":                ("👑 Tier:", "👑 Tier:"),
    "psl_potential":           ("🔮 Потенциал:", "🔮 Potential:"),
    "psl_analysis":            ("📝 Анализ:", "📝 Analysis:"),
    "psl_advice":              ("⚡ Рекомендации:", "⚡ Recommendations:"),
    "psl_not_a_face":          ("🤔 на фото не человек — тут нечего оценивать по PSL. кинь настоящую фотку лица.",
                                "🤔 that's not a human face — nothing to rate. Send a real face photo."),

    "battle_need_photos":      ("Для баттла пришлите два фото одним альбомом с командой 'кульш баттл'.",
                                "For a battle, send two photos in a single album with 'kulsh battle'."),
    "battle_waiting":          ("⚔️ Сравниваю лица...", "⚔️ Comparing faces..."),
    "battle_caption":          ("⚔️ Результат баттла", "⚔️ Battle result"),
    "battle_title":            ("⚔️ РЕЗУЛЬТАТ БАТТЛА", "⚔️ BATTLE RESULT"),
    "battle_winner":           ("🥇 Победитель:", "🥇 Winner:"),
    "battle_first":            ("Первое фото", "First photo"),
    "battle_second":           ("Второе фото", "Second photo"),
    "battle_reason":           ("🔍 Причина:", "🔍 Reason:"),
    "battle_photo1":           ("📊 Фото 1:", "📊 Photo 1:"),
    "battle_photo2":           ("📊 Фото 2:", "📊 Photo 2:"),

    # ---- FEMBOY RATE ----
    "femboy_need_photo":       ("📸 Жду фото для Femboy Rate. Отправь с командой 'femboy rate'.",
                                "📸 Waiting for a photo. Send with 'femboy rate'."),
    "femboy_analyzing":        ("🌸 Анализирую нежность...", "🌸 Analyzing softness..."),
    "femboy_report":           ("🌸 Результаты Femboy Rate", "🌸 Femboy Rate results"),
    "femboy_title":            ("🌸 РЕЗУЛЬТАТЫ FEMBOY RATE", "🌸 FEMBOY RATE RESULTS"),
    "femboy_gender":           ("🧬 Пол:", "🧬 Gender:"),
    "femboy_score":            ("💫 FMB:", "💫 FMB:"),
    "femboy_tier":             ("👑 Tier:", "👑 Tier:"),
    "femboy_potential":        ("🔮 Потенциал:", "🔮 Potential:"),
    "femboy_analysis":         ("📝 Анализ:", "📝 Analysis:"),
    "femboy_advice":           ("⚡ Рекомендации:", "⚡ Recommendations:"),

    "femboy_battle_need_photos": (
        "Для фембой-баттла пришлите два фото одним альбомом с командой 'фембой баттл'.",
        "For a femboy battle, send two photos in a single album with 'femboy battle'.",
    ),
    "femboy_battle_waiting":   ("🌸 Сравниваю нежность...", "🌸 Comparing softness..."),
    "femboy_battle_caption":   ("🌸 Результат фембой-баттла", "🌸 Femboy battle result"),
    "femboy_battle_title":     ("🌸 РЕЗУЛЬТАТ ФЕМБОЙ-БАТТЛА", "🌸 FEMBOY BATTLE RESULT"),
    "femboy_battle_winner":    ("💫 Победитель:", "💫 Winner:"),
    "femboy_battle_first":     ("Первое фото", "First photo"),
    "femboy_battle_second":    ("Второе фото", "Second photo"),
    "femboy_battle_reason":    ("🔍 Причина:", "🔍 Reason:"),
    "femboy_battle_photo1":    ("📊 Фото 1:", "📊 Photo 1:"),
    "femboy_battle_photo2":    ("📊 Фото 2:", "📊 Photo 2:"),

    # ---- STATUS ----
    "status_title":            ("Статус Кульша", "Kulsh status"),
    "status_online":           ("В сети и работает", "Online and working"),
    "status_uptime":           ("Время работы", "Uptime"),
    "status_latency":          ("Отклик", "Latency"),
    "status_mode":             ("Режим", "Mode"),
    "status_mood":             ("Настроение", "Mood"),
    "status_mood_value":       ("отличное 🍷🗿", "excellent 🍷🗿"),

    "logs_no_access":          ("не для тебя писано", "not for you"),
    "logs_cant_check":         ("не могу проверить права", "cannot verify permissions"),
    "logs_read_error":         ("Ошибка чтения логов: {0}", "Log read error: {0}"),

    "tool_unpacking":          ("📦 Распаковываю архив...", "📦 Unpacking archive..."),
    "tool_unpacked":           ("📦 Распаковал.\n\n📄 {0}", "📦 Unpacked.\n\n📄 {0}"),
    "tool_analyzing":          ("🧠 Анализирую {0} файл(ов)...", "🧠 Analyzing {0} file(s)..."),
    "tool_editing":            ("✏️ Редактирую {0} файл(ов)...", "✏️ Editing {0} file(s)..."),
    "tool_repacking":          ("🗜 Собираю архив обратно...", "🗜 Repacking archive..."),
    "tool_sending":            ("📤 Отправляю готовый архив...", "📤 Sending the archive..."),
    "tool_done":               ("✅ Готово", "✅ Done"),
    "tool_error":              ("❌ Ошибка: {0}", "❌ Error: {0}"),
    "tool_no_changes":         ("🤔 ИИ не предложил изменений. {0}", "🤔 AI made no changes. {0}"),
    "tool_parse_fail":         ("❌ Не смог распарсить ответ ИИ: {0}", "❌ Failed to parse AI response: {0}"),
    "tool_no_credits": (
        "💎 Недостаточно кредитов для редактирования архива.\nНужно {0}, у тебя {1}/{2}.",
        "💎 Not enough credits to edit the archive.\nNeed {0}, you have {1}/{2}.",
    ),
    "tool_download_fail":      ("не смог скачать файл: {0}", "failed to download file: {0}"),
    "tool_review_empty":       ("что тут?", "what's here?"),

    "ai_error_400":            ("Ошибка запроса к API (400).", "API request error (400)."),
    "ai_error_generic":        ("Ошибка API.", "API error."),
    "ai_blocked":              ("Блокировка контента.", "Content blocked."),
    "ai_unknown":              ("Ошибка. Что-то пошло не так.", "Error. Something went wrong."),
    "ai_no_models":            ("Все модели и ключи недоступны, попробуй позже 🍷🗿",
                                "All models and keys are unavailable, try later 🍷🗿"),
    "ai_json_fail":            ("Не удалось распарсить ответ ИИ.", "Failed to parse AI response."),
    "ai_custom_prefix":        ("Твои обязательные инструкции: ", "Your mandatory instructions: "),

    "on":                      ("вкл", "on"),
    "off":                     ("выкл", "off"),
    "dark":                    ("тёмная", "dark"),
    "light":                   ("светлая", "light"),
    "russian":                 ("Русский 🇷🇺", "Russian 🇷🇺"),
    "english":                 ("Английский 🇬🇧", "English 🇬🇧"),

    # ---- поиск ----
    "search_starting":         ("🔎 Ищу: {0}", "🔎 Searching: {0}"),
    "search_nothing":          ("🔎 Ничего не нашёл по запросу.", "🔎 Nothing found."),
    "search_off":              ("🔎 Веб-поиск выключен в настройках.",
                                "🔎 Web search is disabled in settings."),
    "search_need_query":       ("Использование: <code>кульш поиск &lt;запрос&gt;</code>",
                                "Usage: <code>kulsh search &lt;query&gt;</code>"),
    "search_source":           ("Источник", "Source"),
    "search_results_header":   ("🔎 Результаты поиска по запросу: {0}",
                                "🔎 Search results for: {0}"),

    # ---- chart ----
    "chart_error":             ("❌ Не удалось построить график: {0}", "❌ Chart error: {0}"),
    "chart_built":             ("📊 Инфографика готова", "📊 Infographic ready"),
    "chart_building":          ("📊 Строю инфографику...", "📊 Rendering infographic..."),
    "chart_usage":             ("Использование: <code>кульш график &lt;описание&gt;</code>",
                                "Usage: <code>kulsh chart &lt;description&gt;</code>"),

    # ---- Discord ----
    "ds_only_admins":          ("только админы могут менять конфиг", "only admins can change config"),
    "ds_need_specify_ru_en":   ("Укажите <code>ru</code> или <code>en</code>.", "Specify <code>ru</code> or <code>en</code>."),
    "ds_need_specify_theme":   ("Укажите <code>тёмная</code> или <code>светлая</code>.", "Specify <code>dark</code> or <code>light</code>."),
    "ds_setting_lang":         ("Язык: {0}", "Language: {0}"),
    "ds_setting_theme":        ("Тема: {0}", "Theme: {0}"),
    "ds_setting_series":       ("Серия: {0}", "Series: {0}"),
    "ds_setting_stickers":     ("Стикеры: {0}", "Stickers: {0}"),
    "ds_setting_sep":          ("Разбивка: {0}", "Split: {0}"),
    "ds_setting_autoreply":    ("Автоответ: {0}", "Auto-reply: {0}"),
    "ds_setting_random":       ("Рандом: {0}", "Random: {0}"),
    "ds_setting_websearch":    ("Веб-поиск: {0}", "Web search: {0}"),
    "ds_setting_temp":         ("Температура: {0}", "Temperature: {0}"),
    "ds_setting_prompt_reset": ("Промпт сброшен", "Prompt reset"),
    "ds_setting_prompt_set":   ("Промпт установлен", "Prompt set"),
    "ds_setting_prompt_need":  ("Введите текст или 'сброс'", "Send text or 'reset'"),
    "ds_setting_model":        ("Модель: {0}", "Model: {0}"),
    "ds_setting_model_auto":   ("Модель: авто", "Model: auto"),
    "ds_setting_model_bad":    ("Введите номер или 'авто'.", "Enter number or 'auto'."),
    "ds_setting_model_badnum": ("Неверный номер", "Invalid number"),
    "ds_setting_temp_bad":     ("Введите число 0.0-2.0", "Enter number 0.0-2.0"),
    "ds_setting_mode":         ("Режим: {0}", "Mode: {0}"),
    "ds_unknown_param":        ("Неизвестный параметр. Используйте 'кульш конфиг'.",
                                "Unknown parameter. Use 'kulsh config'."),
    "ds_update_no_access":     ("ты кто бля, обновлять меня будешь?", "who are you to update me?"),
    "ds_update_start":         ("ща попробую обновиться (с автооткатом при ошибке)...",
                                "trying to update (auto-rollback on error)..."),
    "ds_update_uptodate":      ("я и так свежий:\n```\n{0}\n```", "already up to date:\n```\n{0}\n```"),
    "ds_update_ok":            ("изменения подтянуты, перезапускаюсь:\n```\n{0}\n```",
                                "changes pulled, restarting:\n```\n{0}\n```"),
    "ds_update_rolled": (
        "новый коммит содержит ошибки — я откатился к предыдущей версии. "
        "Бот продолжает работать.\n```\n{0}\n```",
        "new commit contains errors — rolled back. Bot continues working.\n```\n{0}\n```",
    ),
    "ds_update_error":         ("ошибка обновления:\n```\n{0}\n```", "update error:\n```\n{0}\n```"),
    "ds_voice_not_in":         ("ты не в войсе, куда заходить?", "you're not in voice, where should I go?"),
    "ds_voice_joined":         ("залетел в {0} 🍷🗿", "joined {0} 🍷🗿"),
    "ds_voice_cant_join":      ("не могу зайти.", "cannot join."),
    "ds_voice_left":           ("пока кенты", "bye mates"),
    "ds_voice_not_in_bot":     ("я и так не там", "I'm not there anyway"),
    "ds_attachments_error":    ("не могу глянуть, сломалась", "cannot look, broken"),
    "ds_no_memory":            ("не нашёл ничего в памяти", "nothing found in memory"),
    "ds_avatar_none":          ("не смог получить аватарку", "failed to fetch avatar"),
    "ds_logs_content":         ("🍷🗿 Логи сервера:", "🍷🗿 Server logs:"),
    "ds_prompt_ask":           ("отправь новый промпт следующим сообщением (или `отмена`)",
                                "send the new prompt as your next message (or `cancel`)"),
    "ds_menu_placeholder":     ("⚙️ Выбери раздел", "⚙️ Pick a section"),

    "help_body": (
        "🍷🗿 <b>Команды Кульша</b>\n\n"
        "<b>Общие:</b>\n"
        "/start — приветствие\n"
        "/menu — интерактивное меню\n"
        "/help — эта справка\n"
        "/status — состояние бота\n"
        "/donate — поддержать проект\n"
        "/donate_stars &lt;N&gt; — донат через Telegram Stars\n"
        "/credits — баланс кредитов\n\n"
        "<b>Настройки:</b>\n"
        "<code>кульш конфиг</code> — настройки (инлайн)\n\n"
        "<b>Утилиты:</b>\n"
        "<code>кульш аватарка</code> — описать аватарку\n"
        "<code>кульш вспомни медиа [N]</code> — вспомнить N медиа\n"
        "<code>кульш поиск &lt;запрос&gt;</code> — поиск в интернете\n"
        "<code>кульш график &lt;описание&gt;</code> — сгенерировать инфографику\n"
        "<code>нарисуй ...</code> — попроси Кульша нарисовать картинку (сам решит и нарисует)\n"
        "<code>кульш логи</code> — логи (админам)\n\n"
        "<b>Развлечения:</b>\n"
        "<code>кульш psl</code> — looksmaxxing\n"
        "<code>кульш psl совет</code> — + рекомендации\n"
        "<code>кульш battle</code> — баттл (альбом)\n"
        "<code>фембой рейт</code> / <code>femboy rate</code> — Femboy Rate\n"
        "<code>фембой баттл</code> / <code>femboy battle</code> — фембой-баттл (альбом)\n"
        "<code>кульш донаты</code> — топ донатеров\n\n"
        "<b>Инструменты (ЛС):</b>\n"
        "Отправь архив/текстовый файл — бот распакует, изменит, соберёт и вернёт.\n\n"
        "🚀 Mini App: {0}\n"
        "🔗 GitHub: {1}",
        "🍷🗿 <b>Kulsh commands</b>\n\n"
        "<b>General:</b>\n"
        "/start — greeting\n"
        "/menu — interactive menu\n"
        "/help — this help\n"
        "/status — bot status\n"
        "/donate — support the project\n"
        "/donate_stars &lt;N&gt; — donate via Telegram Stars\n"
        "/credits — credits balance\n\n"
        "<b>Settings:</b>\n"
        "<code>kulsh config</code> — settings (inline)\n\n"
        "<b>Utilities:</b>\n"
        "<code>kulsh avatar</code> — describe avatar\n"
        "<code>kulsh recall [N]</code> — recall N media\n"
        "<code>kulsh search &lt;query&gt;</code> — web search\n"
        "<code>kulsh chart &lt;description&gt;</code> — generate infographic\n"
        "<code>draw ...</code> — ask Kulsh to draw an image (he decides and draws it himself)\n"
        "<code>kulsh logs</code> — logs (admins)\n\n"
        "<b>Entertainment:</b>\n"
        "<code>kulsh psl</code> — looksmaxxing\n"
        "<code>kulsh psl advice</code> — + recommendations\n"
        "<code>kulsh battle</code> — battle (album)\n"
        "<code>femboy rate</code> — Femboy Rate\n"
        "<code>femboy battle</code> — femboy battle (album)\n"
        "<code>kulsh donations</code> — top donators\n\n"
        "<b>Tools (DM):</b>\n"
        "Send an archive/text file — bot unpacks, edits, repacks and returns it.\n\n"
        "🚀 Mini App: {0}\n"
        "🔗 GitHub: {1}",
    ),
}


def tr(lang: str, key: str, *args: Any, **kwargs: Any) -> str:
    entry = TEXTS.get(key)
    if not entry:
        return key
    ru, en = entry
    text = ru if lang == "ru" else en
    if args or kwargs:
        try:
            return text.format(*args, **kwargs)
        except Exception:
            return text
    return text


def html_to_md(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<u>(.*?)</u>', r'__\1__', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<ins>(.*?)</ins>', r'__\1__', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<s>(.*?)</s>', r'~~\1~~', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<strike>(.*?)</strike>', r'~~\1~~', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<del>(.*?)</del>', r'~~\1~~', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<pre>(.*?)</pre>', lambda m: '```\n' + m.group(1) + '\n```', text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return text