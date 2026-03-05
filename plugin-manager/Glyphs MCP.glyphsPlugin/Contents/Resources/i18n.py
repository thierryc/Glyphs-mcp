# encoding: utf-8

from __future__ import division, print_function, unicode_literals

try:
    from GlyphsApp import Glyphs  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    Glyphs = None


STRINGS = {
    # Menu
    "menu.start": {
        "en": "Start Glyphs MCP Server",
        "de": "Glyphs MCP-Server starten",
        "fr": "Démarrer le serveur MCP",
        "es": "Iniciar el servidor MCP",
        "pt": "Iniciar o servidor Glyphs MCP",
        "zh-Hans": "启动 Glyphs MCP 服务器",
    },
    "menu.running": {
        "en": "Glyphs MCP Server is running",
        "de": "Glyphs MCP-Server läuft",
        "fr": "Le serveur MCP est en cours d'exécution",
        "es": "El servidor MCP está en ejecución",
        "pt": "O servidor MCP está em execução",
        "zh-Hans": "Glyphs MCP 服务器正在运行",
    },
    "menu.status": {
        "en": "Glyphs MCP Server Status…",
        "de": "Glyphs MCP-Server-Status…",
        "fr": "Statut du serveur MCP…",
        "es": "Estado del servidor MCP…",
        "pt": "Status do servidor MCP…",
        "zh-Hans": "Glyphs MCP 服务器状态…",
    },
    "menu.autostart": {
        "en": "Auto-start server on launch",
        "de": "Server beim Start automatisch starten",
        "fr": "Démarrer le serveur au lancement",
        "es": "Iniciar el servidor al abrir",
        "pt": "Iniciar o servidor ao abrir",
        "zh-Hans": "启动时自动启动服务器",
    },
    # Common
    "app.title": {
        "en": "Glyphs MCP Server",
        "fr": "Serveur Glyphs MCP",
        "zh-Hans": "Glyphs MCP 服务器",
    },
    "common.ok": {"en": "OK", "fr": "OK", "zh-Hans": "好"},
    "common.cancel": {"en": "Cancel", "fr": "Annuler", "zh-Hans": "取消"},
    "common.copy": {"en": "Copy", "fr": "Copier", "zh-Hans": "复制"},
    # Port busy prompt
    "portbusy.message": {
        "en": (
            'I can\'t start the MCP server on "{port}".\n\n'
            "Wait (preferred) until the previous instance has finished shutting down, "
            "or start on a custom port below."
        ),
        "fr": (
            'Impossible de démarrer le serveur MCP sur « {port} ».\n\n'
            "Attendez (recommandé) que l’instance précédente se ferme complètement, "
            "ou choisissez un port personnalisé ci-dessous."
        ),
        "zh-Hans": (
            "无法在“{port}”上启动 MCP 服务器。\n\n"
            "请等待（推荐）之前的实例完全关闭，或在下方选择自定义端口。"
        ),
    },
    "portbusy.wait": {
        "en": "Wait (preferred)",
        "fr": "Attendre (recommandé)",
        "zh-Hans": "等待（推荐）",
    },
    "portbusy.custom": {
        "en": "Start on Custom Port",
        "fr": "Démarrer sur un port personnalisé",
        "zh-Hans": "使用自定义端口启动",
    },
    "portbusy.placeholder": {
        "en": "Custom port (1–65535)",
        "fr": "Port personnalisé (1–65535)",
        "zh-Hans": "自定义端口（1–65535）",
    },
    "portbusy.invalid": {
        "en": "Enter a valid port number (1–65535).",
        "fr": "Saisissez un numéro de port valide (1–65535).",
        "zh-Hans": "请输入有效的端口号（1–65535）。",
    },
    "portbusy.range": {
        "en": "Port must be between 1 and 65535.",
        "fr": "Le port doit être compris entre 1 et 65535.",
        "zh-Hans": "端口必须在 1 到 65535 之间。",
    },
    "portbusy.inuse": {
        "en": "Port {port} is already in use. Choose another port.",
        "fr": "Le port {port} est déjà utilisé. Choisissez un autre port.",
        "zh-Hans": "端口 {port} 已被占用。请选择另一个端口。",
    },
    # Waiting panel
    "wait.info": {
        "en": "Waiting for port {port} to become available…\nThis usually takes a few seconds.",
        "fr": "En attente que le port {port} devienne disponible…\nCela prend généralement quelques secondes.",
        "zh-Hans": "正在等待端口 {port} 变为可用…\n这通常只需要几秒钟。",
    },
    # Status panel labels/buttons
    "status.label": {"en": "Status:", "fr": "État :", "zh-Hans": "状态："},
    "version.label": {"en": "Version:", "fr": "Version :", "zh-Hans": "版本："},
    "endpoint.label": {"en": "Endpoint:", "fr": "Endpoint :", "zh-Hans": "端点："},
    "docs.label": {"en": "Docs:", "fr": "Docs :", "zh-Hans": "文档："},
    "profile.label": {"en": "Profile:", "fr": "Profil :", "zh-Hans": "配置："},
    "debug.checkbox": {
        "en": "Log all events (debug, includes SSE)",
        "fr": "Journaliser tous les événements (debug, inclut SSE)",
        "zh-Hans": "记录所有事件（调试，包含 SSE）",
    },
    "docs.open": {"en": "Open Docs", "fr": "Ouvrir la doc", "zh-Hans": "打开文档"},
    "endpoint.copy": {"en": "Copy Endpoint", "fr": "Copier l’endpoint", "zh-Hans": "复制端点"},
    # Status values
    "status.running": {"en": "Running", "fr": "En cours", "zh-Hans": "运行中"},
    "status.stopped": {"en": "Stopped", "fr": "Arrêté", "zh-Hans": "已停止"},
    "status.waiting": {
        "en": "Waiting for port {port}…",
        "fr": "En attente du port {port}…",
        "zh-Hans": "正在等待端口 {port}…",
    },
    "status.autostart_waiting": {
        "en": "Auto-start waiting for port {port}…",
        "fr": "Démarrage auto : attente du port {port}…",
        "zh-Hans": "自动启动：正在等待端口 {port}…",
    },
    # Errors
    "error.open_status_window": {
        "en": "Unable to open MCP status window: {error}",
        "fr": "Impossible d’ouvrir la fenêtre d’état MCP : {error}",
        "zh-Hans": "无法打开 MCP 状态窗口：{error}",
    },
    "error.open_docs": {
        "en": "Unable to open docs URL:\n{url}\n\n{error}",
        "fr": "Impossible d’ouvrir l’URL de la doc :\n{url}\n\n{error}",
        "zh-Hans": "无法打开文档链接：\n{url}\n\n{error}",
    },
    "error.start_server": {
        "en": "Failed to start server: {error}",
        "fr": "Échec du démarrage du serveur : {error}",
        "zh-Hans": "启动服务器失败：{error}",
    },
}


def tr(key, **fmt):
    """Translate a key to the current Glyphs UI language and apply .format()."""
    loc = STRINGS.get(key)
    if isinstance(loc, dict):
        if Glyphs is not None:
            try:
                s = Glyphs.localize(loc)
            except Exception:  # pragma: no cover
                s = loc.get("en")
        else:
            s = loc.get("en")
    else:
        s = None

    if s is None:
        s = key

    if fmt:
        try:
            s = s.format(**fmt)
        except Exception:
            pass
    return s

