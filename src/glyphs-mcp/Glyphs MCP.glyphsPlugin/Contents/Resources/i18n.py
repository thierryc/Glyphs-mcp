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
    "menu.update_available": {
        "en": "{name} — Update Available",
        "de": "{name} — Update verfügbar",
        "fr": "{name} — Mise à jour disponible",
        "es": "{name} — Actualización disponible",
        "pt": "{name} — Atualização disponível",
        "zh-Hans": "{name} — 有可用更新",
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
    # Update notifications
    "update.check_now": {
        "en": "Check Now",
        "de": "Jetzt prüfen",
        "fr": "Vérifier",
        "es": "Buscar ahora",
        "pt": "Verificar agora",
        "zh-Hans": "立即检查",
    },
    "update.checking_short": {
        "en": "Checking…",
        "de": "Prüfe…",
        "fr": "Vérification…",
        "es": "Buscando…",
        "pt": "Verificando…",
        "zh-Hans": "正在检查…",
    },
    "update.disable_checks": {
        "en": "Disable Update Checks",
        "de": "Update-Prüfung deaktivieren",
        "fr": "Désactiver les vérifications",
        "es": "Desactivar comprobaciones",
        "pt": "Desativar verificações",
        "zh-Hans": "停用更新检查",
    },
    "update.enable_checks": {
        "en": "Enable Update Checks",
        "de": "Update-Prüfung aktivieren",
        "fr": "Activer les vérifications",
        "es": "Activar comprobaciones",
        "pt": "Ativar verificações",
        "zh-Hans": "启用更新检查",
    },
    "update.action": {
        "en": "Prepare Update",
        "de": "Update vorbereiten",
        "fr": "Préparer la mise à jour",
        "es": "Preparar actualización",
        "pt": "Preparar atualização",
        "zh-Hans": "准备更新",
    },
    "update.action_tooltip": {
        "en": "Download and prepare this update. It will not be installed yet.",
        "de": "Dieses Update herunterladen und vorbereiten. Es wird noch nicht installiert.",
        "fr": "Télécharger et préparer cette mise à jour. Elle ne sera pas encore installée.",
        "es": "Descargar y preparar esta actualización. Aún no se instalará.",
        "pt": "Baixar e preparar esta atualização. Ela ainda não será instalada.",
        "zh-Hans": "下载并准备此更新，但暂不安装。",
    },
    "update.view_release": {
        "en": "View Release",
        "de": "Version ansehen",
        "fr": "Voir la version",
        "es": "Ver versión",
        "pt": "Ver versão",
        "zh-Hans": "查看版本",
    },
    "update.view_release_tooltip": {
        "en": "See what’s new and download this version.",
        "de": "Neuigkeiten ansehen und diese Version herunterladen.",
        "fr": "Voir les nouveautés et télécharger cette version.",
        "es": "Ver las novedades y descargar esta versión.",
        "pt": "Ver as novidades e baixar esta versão.",
        "zh-Hans": "查看新内容并下载此版本。",
    },
    "update.retry": {
        "en": "Retry",
        "de": "Erneut versuchen",
        "fr": "Réessayer",
        "es": "Reintentar",
        "pt": "Tentar novamente",
        "zh-Hans": "重试",
    },
    "update.installer_required": {
        "en": "View the release to download and install it.",
        "de": "Öffnen Sie die Version, um sie herunterzuladen und zu installieren.",
        "fr": "Consultez la version pour la télécharger et l’installer.",
        "es": "Vea la versión para descargarla e instalarla.",
        "pt": "Veja a versão para baixá-la e instalá-la.",
        "zh-Hans": "查看此版本以下载并安装。",
    },
    "update.downloading": {
        "en": "Downloading…",
        "de": "Wird geladen…",
        "fr": "Téléchargement…",
        "es": "Descargando…",
        "pt": "Baixando…",
        "zh-Hans": "正在下载…",
    },
    "update.verifying": {
        "en": "Verifying…",
        "de": "Wird geprüft…",
        "fr": "Vérification…",
        "es": "Verificando…",
        "pt": "Verificando…",
        "zh-Hans": "正在验证…",
    },
    "update.preparing": {
        "en": "Preparing…",
        "de": "Wird vorbereitet…",
        "fr": "Préparation…",
        "es": "Preparando…",
        "pt": "Preparando…",
        "zh-Hans": "正在准备…",
    },
    "update.cancelling": {
        "en": "Cancelling…",
        "de": "Wird abgebrochen…",
        "fr": "Annulation…",
        "es": "Cancelando…",
        "pt": "Cancelando…",
        "zh-Hans": "正在取消…",
    },
    "update.verified_not_installed": {
        "en": "Glyphs MCP {version} is ready, but not installed.",
        "de": "Glyphs MCP {version} ist bereit, aber noch nicht installiert.",
        "fr": "Glyphs MCP {version} est prêt, mais pas encore installé.",
        "es": "Glyphs MCP {version} está listo, pero aún no está instalado.",
        "pt": "O Glyphs MCP {version} está pronto, mas ainda não foi instalado.",
        "zh-Hans": "Glyphs MCP {version} 已准备就绪，但尚未安装。",
    },
    "update.preparation_error": {
        "en": "Update preparation failed: {error}",
        "de": "Vorbereitung des Updates fehlgeschlagen: {error}",
        "fr": "Échec de la préparation de la mise à jour : {error}",
        "es": "Error al preparar la actualización: {error}",
        "pt": "Falha ao preparar a atualização: {error}",
        "zh-Hans": "更新准备失败：{error}",
    },
    "update.available": {
        "en": "A new version is available: {version}.",
        "de": "Eine neue Version ist verfügbar: {version}.",
        "fr": "Une nouvelle version est disponible : {version}.",
        "es": "Hay una nueva versión disponible: {version}.",
        "pt": "Uma nova versão está disponível: {version}.",
        "zh-Hans": "有新版本可用：{version}。",
    },
    "update.checking": {
        "en": "Checking for updates…",
        "de": "Suche nach Updates…",
        "fr": "Recherche de mises à jour…",
        "es": "Buscando actualizaciones…",
        "pt": "Verificando atualizações…",
        "zh-Hans": "正在检查更新…",
    },
    "update.up_to_date": {
        "en": "Glyphs MCP is up to date.",
        "de": "Glyphs MCP ist aktuell.",
        "fr": "Glyphs MCP est à jour.",
        "es": "Glyphs MCP está actualizado.",
        "pt": "O Glyphs MCP está atualizado.",
        "zh-Hans": "Glyphs MCP 已是最新版本。",
    },
    "update.disabled": {
        "en": "Automatic update checks are disabled.",
        "de": "Automatische Update-Prüfungen sind deaktiviert.",
        "fr": "La vérification automatique est désactivée.",
        "es": "La comprobación automática está desactivada.",
        "pt": "A verificação automática está desativada.",
        "zh-Hans": "自动更新检查已停用。",
    },
    "update.error": {
        "en": "Update check failed: {error}",
        "de": "Update-Prüfung fehlgeschlagen: {error}",
        "fr": "Échec de la vérification : {error}",
        "es": "Error al buscar actualizaciones: {error}",
        "pt": "Falha ao verificar atualizações: {error}",
        "zh-Hans": "更新检查失败：{error}",
    },
    "update.notification.title": {
        "en": "A new Glyphs MCP version is available",
        "de": "Eine neue Glyphs MCP-Version ist verfügbar",
        "fr": "Une nouvelle version de Glyphs MCP est disponible",
        "es": "Hay una nueva versión de Glyphs MCP disponible",
        "pt": "Uma nova versão do Glyphs MCP está disponível",
        "zh-Hans": "Glyphs MCP 有新版本可用",
    },
    "update.notification.message": {
        "en": "Version {version} is available. Open Glyphs MCP Server to learn more.",
        "de": "Version {version} ist verfügbar. Öffnen Sie Glyphs MCP Server, um mehr zu erfahren.",
        "fr": "La version {version} est disponible. Ouvrez Glyphs MCP Server pour en savoir plus.",
        "es": "La versión {version} está disponible. Abra Glyphs MCP Server para obtener más información.",
        "pt": "A versão {version} está disponível. Abra o Glyphs MCP Server para saber mais.",
        "zh-Hans": "版本 {version} 现已可用。打开 Glyphs MCP Server 了解详情。",
    },
    # Status values
    "status.running": {"en": "Running", "fr": "En cours", "zh-Hans": "运行中"},
    "status.stopped": {"en": "Stopped", "fr": "Arrêté", "zh-Hans": "已停止"},
    "status.error": {"en": "Error", "fr": "Erreur", "zh-Hans": "错误"},
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
    "error.open_update": {
        "en": "Unable to open update release:\n{url}\n\n{error}",
        "de": "Update-Version kann nicht geöffnet werden:\n{url}\n\n{error}",
        "fr": "Impossible d’ouvrir la mise à jour :\n{url}\n\n{error}",
        "es": "No se puede abrir la actualización:\n{url}\n\n{error}",
        "pt": "Não foi possível abrir a atualização:\n{url}\n\n{error}",
        "zh-Hans": "无法打开更新版本：\n{url}\n\n{error}",
    },
    "error.start_server": {
        "en": "Failed to start server: {error}",
        "fr": "Échec du démarrage du serveur : {error}",
        "zh-Hans": "启动服务器失败：{error}",
    },
    "error.startup_failed": {
        "en": "Failed to start on port {port}.\nCheck the Macro Panel, then click Start.",
        "fr": "Échec du démarrage sur le port {port}.\nConsultez le panneau Macro, puis cliquez sur Démarrer.",
        "zh-Hans": "无法在端口 {port} 上启动。\n请查看宏面板，然后点按“启动”。",
    },
    "error.unexpected_exit": {
        "en": "Server stopped unexpectedly on port {port}.\nCheck the Macro Panel, then click Start.",
        "fr": "Arrêt inattendu du serveur sur le port {port}.\nConsultez le panneau Macro, puis cliquez sur Démarrer.",
        "zh-Hans": "服务器在端口 {port} 上意外停止。\n请查看宏面板，然后点按“启动”。",
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
