# encoding: utf-8

from __future__ import division, print_function, unicode_literals

try:
    from GlyphsApp import Glyphs  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    Glyphs = None


STRINGS = {
    # Menu
    "menu.main": {
        "en": "Glyphs MCP Server",
        "de": "Glyphs MCP-Server",
        "fr": "Serveur MCP Glyphs",
        "es": "Servidor MCP de Glyphs",
        "pt": "Servidor Glyphs MCP",
        "zh-Hans": "Glyphs MCP 服务器",
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
            "Wait until the previous instance has finished shutting down, "
            "or cancel and close the app that is using this port."
        ),
        "fr": (
            'Impossible de démarrer le serveur MCP sur « {port} ».\n\n'
            "Attendez que l’instance précédente se ferme complètement, "
            "ou annulez et fermez l’application qui utilise ce port."
        ),
        "zh-Hans": (
            "无法在“{port}”上启动 MCP 服务器。\n\n"
            "请等待之前的实例完全关闭，或取消并关闭正在使用此端口的应用。"
        ),
    },
    "portbusy.wait": {
        "en": "Wait for Port",
        "fr": "Attendre le port",
        "zh-Hans": "等待端口",
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
    "port.label": {"en": "Port:", "fr": "Port :", "zh-Hans": "端口："},
    "port.apply": {"en": "Set", "fr": "Définir", "zh-Hans": "设置"},
    "port.invalid": {
        "en": "Enter a valid port number between 1 and 65535.",
        "fr": "Saisissez un numéro de port valide entre 1 et 65535.",
        "zh-Hans": "请输入 1 到 65535 之间的有效端口号。",
    },
    "docs.label": {"en": "Docs:", "fr": "Docs :", "zh-Hans": "文档："},
    "profile.label": {"en": "Profile:", "fr": "Profil :", "zh-Hans": "配置："},
    "debug.checkbox": {
        "en": "Log all events (debug, includes SSE)",
        "fr": "Journaliser tous les événements (debug, inclut SSE)",
        "zh-Hans": "记录所有事件（调试，包含 SSE）",
    },
    "debug.short": {"en": "Debug log", "fr": "Debug log", "zh-Hans": "调试日志"},
    "autostart.short": {"en": "Auto-start", "fr": "Démarrage auto", "zh-Hans": "自动启动"},
    "activity.label": {"en": "Activity", "fr": "Activité", "zh-Hans": "活动"},
    "activity.idle": {"en": "Idle", "fr": "Inactif", "zh-Hans": "空闲"},
    "copy.tooltip": {"en": "Copy endpoint", "fr": "Copier l’endpoint", "zh-Hans": "复制端点"},
    "docs.tooltip": {"en": "Open docs", "fr": "Ouvrir la doc", "zh-Hans": "打开文档"},
    "feedback.tooltip": {"en": "Open project page", "fr": "Ouvrir la page du projet", "zh-Hans": "打开项目页面"},
    "feedback.footer": {
        "en": "Vibe coded with ✨ by Thierry Charbonnel t@ap.cx",
        "fr": "Vibe coded with ✨ by Thierry Charbonnel t@ap.cx",
        "zh-Hans": "Vibe coded with ✨ by Thierry Charbonnel t@ap.cx",
    },
    "docs.open": {"en": "Open Docs", "fr": "Ouvrir la doc", "zh-Hans": "打开文档"},
    "endpoint.copy": {"en": "Copy Endpoint", "fr": "Copier l’endpoint", "zh-Hans": "复制端点"},
    "server.start": {"en": "Start", "fr": "Démarrer", "zh-Hans": "启动"},
    "server.starting": {"en": "Starting", "fr": "Démarrage", "zh-Hans": "正在启动"},
    "server.stop": {"en": "Stop", "fr": "Arrêter", "zh-Hans": "停止"},
    "server.stopping": {"en": "Stopping…", "fr": "Arrêt…", "zh-Hans": "正在停止…"},
    # Status values
    "status.running": {"en": "Running", "fr": "En cours", "zh-Hans": "运行中"},
    "status.stopped": {"en": "Stopped", "fr": "Arrêté", "zh-Hans": "已停止"},
    "status.starting": {"en": "Starting", "fr": "Démarrage", "zh-Hans": "正在启动"},
    "status.stopping": {"en": "Stopping…", "fr": "Arrêt…", "zh-Hans": "正在停止…"},
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
    "error.open_feedback": {
        "en": "Unable to open feedback URL:\n{url}\n\n{error}",
        "fr": "Impossible d’ouvrir l’URL de feedback :\n{url}\n\n{error}",
        "zh-Hans": "无法打开反馈链接：\n{url}\n\n{error}",
    },
    "error.start_server": {
        "en": "Failed to start server: {error}",
        "fr": "Échec du démarrage du serveur : {error}",
        "zh-Hans": "启动服务器失败：{error}",
    },
    "error.stop_server": {
        "en": "Failed to stop server: {error}",
        "fr": "Échec de l’arrêt du serveur : {error}",
        "zh-Hans": "停止服务器失败：{error}",
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
