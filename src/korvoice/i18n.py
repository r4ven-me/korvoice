"""Small built-in Russian/English UI translation layer."""

# Translation entries are intentionally kept as complete source/target pairs.
# ruff: noqa: E501

from __future__ import annotations

import locale
import os

_language_override = "system"

# Long explanatory texts are looked up by a short id instead of their full
# English wording; both languages therefore need an explicit entry.
_EN = {
    "X11 hotkey note": "<i>X11: the combination is grabbed by the app directly; a single key is detected from the keyboard state.<br>Wayland: the GlobalShortcuts system portal is used; the compositor may show a confirmation dialog, and single modifier keys are not supported by every compositor.</i>",
    "Autotype requirements": "X11: requires xdotool.\nWayland: requires wl-clipboard, plus ydotool with a running ydotoold that has access to uinput.\nThe text is pasted with Ctrl+V — terminals usually need Ctrl+Shift+V, so autotype may not work there.\nIf autotype is unavailable, the reason appears in the tray tooltip; the clipboard and history keep working.",
    "GigaAM chunk note": "GigaAM rejects audio longer than 25 seconds in one call — long recordings are split at the nearest pause. Keep some headroom below 25 seconds (default 20).",
    "GigaAM model note": "<i>The model (~1 GB, cached in ~/.cache/gigaam) loads in the background right after korvoice starts, not on first use, and reloads in the background as soon as the model or device on this tab is changed.</i>",
    "Clipboard history note": "Clipboard managers that honour the “secret” hint (Klipper, CopyQ, cliphist and others) skip text marked this way. Other managers may ignore it. Not available on Wayland: wl-copy can't attach the hint.",
}

_RU = {
    "Settings — korvoice": "Настройки — korvoice",
    "General": "Основные",
    "Output": "Вывод",
    "Model": "Модель",
    "About": "О программе",
    "Save": "Сохранить",
    "Cancel": "Отмена",
    "System": "Системная",
    "Language:": "Язык:",
    "System language": "Системный язык",
    "Russian": "Русский",
    "Nord Dark": "Nord тёмная",
    "Nord Light": "Nord светлая",
    "Theme:": "Тема:",
    "Auto (theme)": "Авто (по теме)",
    "Dark": "Тёмная",
    "Light": "Светлая",
    "Tray icon:": "Иконка в трее:",
    "The system tray's own background isn't always the same as the app's theme — pick a fixed icon colour if \"Auto\" is hard to see.": "Фон системного трея не всегда совпадает с темой приложения — выберите фиксированный цвет, если вариант «Авто» плохо виден.",
    "Push-to-talk: hold the hotkey while speaking, release to transcribe.\nToggle: press once to start recording, press again to stop.": "Удержание: держите горячую клавишу во время речи и отпустите для распознавания.\nПереключатель: нажмите один раз для начала записи и ещё раз для остановки.",
    "A lone modifier key (Ctrl/Shift/Alt/Super) can't be captured by pressing it into the combination field below — pick it here.": "Одиночную клавишу-модификатор (Ctrl/Shift/Alt/Super) нельзя записать в поле сочетания ниже — выберите её здесь.",
    "Recording mode:": "Режим записи:",
    "Push-to-talk (hold the key)": "Удержание клавиши",
    "Toggle (press to start/stop)": "Переключатель (нажать для старта/остановки)",
    "Use the combination below": "Использовать сочетание ниже",
    "Single key:": "Одиночная клавиша:",
    "Right Ctrl": "Правый Ctrl",
    "Left Ctrl": "Левый Ctrl",
    "Right Shift": "Правый Shift",
    "Left Shift": "Левый Shift",
    "Right Alt": "Правый Alt",
    "Left Alt": "Левый Alt",
    "Right Super": "Правый Super",
    "Left Super": "Левый Super",
    "Clear": "Очистить",
    "...or combination:": "...или сочетание:",
    "Start at login": "Запускать при входе",
    "Settings file: {path}": "Файл настроек: {path}",
    "X11 hotkey note": "<i>X11: сочетание захватывается приложением напрямую; одиночная клавиша определяется по состоянию клавиатуры.<br>Wayland: используется системный портал GlobalShortcuts; композитор может показать диалог подтверждения, а одиночные модификаторы поддерживаются не всеми композиторами.</i>",
    "Deliver recognized text to (any combination):": "Куда выводить распознанный текст:",
    "Clipboard": "Буфер обмена",
    "Keep recognized text in the clipboard": "Оставлять распознанный текст в буфере обмена",
    "X11 autotype uses the clipboard temporarily. When this option is off, the previous contents are restored after pasting. A clipboard history manager may still capture the temporary text.": "Автовставка в X11 временно использует буфер обмена. Если этот флажок выключен, прежнее содержимое восстанавливается после вставки. Менеджер истории буфера всё равно может увидеть временный текст.",
    "Autotype into the focused window": "Вставлять в активное окно",
    "History window": "Окно истории",
    "Keep history between restarts": "Сохранять историю между запусками",
    "Remove hesitation sounds (eh, eh-eh, um, mm)": "Удалять слова-паразиты (э, э-э, эм, м-м)",
    "After recognized text:": "После распознанного текста:",
    "Nothing": "Ничего",
    "Space": "Пробел",
    "New line": "Новая строка",
    "Blank line": "Пустая строка",
    "Custom…": "Свой вариант…",
    "Text appended verbatim": "Текст, добавляемый без изменений",
    "Autotype requirements": "X11: требуется xdotool.\nWayland: требуются wl-clipboard, а также ydotool и запущенный ydotoold с доступом к uinput.\nТекст вставляется через Ctrl+V — терминалам обычно нужен Ctrl+Shift+V, поэтому в них автовставка может не сработать.\nЕсли автовставка недоступна, причина появится в подсказке трея; буфер обмена и история продолжат работать.",
    "Hide from clipboard history:": "Скрывать от истории буфера:",
    "Only temporary paste text": "Только временный текст вставки",
    "All recognized text": "Весь распознанный текст",
    "Clipboard history note": "Менеджеры буфера обмена, учитывающие пометку «секретно» (Klipper, CopyQ, cliphist и другие), не сохраняют такой текст. Остальные могут её игнорировать. В Wayland недоступно: wl-copy не умеет добавлять пометку.",
    "wl-copy not found — install wl-clipboard for autotype on Wayland": "wl-copy не найден — установите wl-clipboard для автовставки в Wayland",
    "Model:": "Модель:",
    "Inference device:": "Устройство вычислений:",
    "Auto (GPU if available, else CPU)": "Авто (GPU при наличии, иначе CPU)",
    "Max chunk length, s:": "Максимальная длина фрагмента, с:",
    "System default": "Системный по умолчанию",
    "Microphone:": "Микрофон:",
    "GigaAM chunk note": "GigaAM не принимает аудио длиннее 25 секунд за один вызов — длинные записи делятся по ближайшей паузе. Оставьте запас до 25 секунд (по умолчанию 20).",
    "GigaAM model note": "<i>Модель (~1 ГБ, кешируется в ~/.cache/gigaam) загружается в фоне сразу после запуска korvoice, а не при первом использовании, и перезагружается в фоне сразу после смены модели или устройства на этой вкладке.</i>",
    "Mode": "Режим",
    "Push-to-talk": "Удержание клавиши",
    "Toggle": "Переключатель",
    "Open history": "Открыть историю",
    "Settings": "Настройки",
    "Quit": "Выход",
    "Start recording": "Начать запись",
    "Stop recording": "Остановить запись",
    "Recognizing…": "Распознавание…",
    "idle": "ожидание",
    "recording…": "запись…",
    "recognizing…": "распознавание…",
    "Mode: {mode}, hotkey: {hotkey}": "Режим: {mode}, клавиша: {hotkey}",
    "Hotkey unavailable: {message}": "Горячая клавиша недоступна: {message}",
    "Could not start recording: {message}": "Не удалось начать запись: {message}",
    "Selected microphone is unavailable; using the system default.": "Выбранный микрофон недоступен; используется системный микрофон.",
    "Recognition failed: {message}": "Ошибка распознавания: {message}",
    "Autotype unavailable: {message}": "Автовставка недоступна: {message}",
    "xdotool not found — install it for autotype on X11 (e.g. sudo apt install xdotool)": "xdotool не найден — установите его для автовставки в X11 (например: sudo apt install xdotool)",
    "ydotool not found — install it and run ydotoold for autotype on Wayland": "ydotool не найден — установите его и запустите ydotoold для автовставки в Wayland",
    "korvoice — History": "korvoice — История",
    "Copy all": "Копировать всё",
    "Version {version}": "Версия {version}",
    "Author:": "Автор:",
    "License:": "Лицензия:",
    "Website:": "Сайт:",
    "GitHub:": "GitHub:",
    "Telegram channel:": "Telegram-канал:",
    "Telegram chat:": "Telegram-чат:",
    "About korvoice": "О программе korvoice",
    "Push-to-talk / toggle Russian voice input for Linux, powered by the local GigaAM speech model — tray, Nord GUI, no cloud.": "Локальный голосовой ввод на русском языке для Linux на базе GigaAM — системный трей, интерфейс Nord, без облака.",
    "Close": "Закрыть",
    "No hotkey is set — recording would only start from the tray menu (or its left-click). Save without a hotkey?": "Горячая клавиша не задана — запись можно будет начать только из меню трея или щелчком по нему. Сохранить без горячей клавиши?",
    "Failed to configure autostart: {message}": "Не удалось настроить автозапуск: {message}",
    "v3 CTC + punctuation (default)": "v3 CTC + пунктуация (по умолчанию)",
    "v3 RNNT + punctuation (more accurate)": "v3 RNNT + пунктуация (точнее)",
    "v3 CTC (no punctuation)": "v3 CTC (без пунктуации)",
    "v3 RNNT (no punctuation)": "v3 RNNT (без пунктуации)",
    "Enable wake word": "Включить кодовое слово",
    "Wake phrase:": "Кодовая фраза:",
    "e.g. привет корвойс": "например, привет корвойс",
    "Wake-word model found.": "Модель кодового слова найдена.",
    "Wake word unavailable: {message}": "Кодовое слово недоступно: {message}",
    "Wake word is enabled but no phrase is set — it will stay inactive "
    "until you add one.": "Кодовое слово включено, но фраза не задана — оно останется "
    "неактивным, пока вы её не укажете.",
    "Wake word is enabled but {message} — it will stay inactive until "
    "that's fixed.": "Кодовое слово включено, но {message} — оно останется неактивным, "
    "пока это не будет исправлено.",
    'Wake word armed: listening for "{phrase}"':
        "Кодовое слово активно: ожидание фразы «{phrase}»",
}


def system_language(environ: dict[str, str] | None = None) -> str:
    """Returns ``ru`` for a Russian system locale, otherwise ``en``."""
    env = os.environ if environ is None else environ
    value = next((env.get(key, "") for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")
                  if env.get(key)), "")
    if not value:
        value = locale.getlocale()[0] or ""
    code = value.split(":", 1)[0].split(".", 1)[0].split("_", 1)[0].lower()
    return "ru" if code == "ru" else "en"


def set_language(language: str) -> None:
    """Selects ``ru``, ``en`` or automatic system-language detection."""
    global _language_override
    _language_override = language if language in {"ru", "en"} else "system"


def current_language() -> str:
    return system_language() if _language_override == "system" else _language_override


def tr(text: str, **values: object) -> str:
    table = _RU if current_language() == "ru" else _EN
    translated = table.get(text, text)
    return translated.format(**values) if values else translated
