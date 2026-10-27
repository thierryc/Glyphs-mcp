import AppKit
import Combine
import ServiceManagement
import SwiftUI
import GlyphsMCPInstallerCore

@MainActor
final class DesktopAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSMenuDelegate {
    private let initializationStartedAt = Date()
    private var firstPresentationRecorded = false
    let desktop = DesktopModel()
    let installer = InstallerViewModel()
    lazy var updates = DesktopUpdates(installationBusy: { [weak self] in self?.installer.operationsBusy == true })
    private var dashboard: NSWindow?
    private var welcome: NSWindow?
    private var settingsWindow: NSWindow?
    private var initialWelcome = false
    private var troubleshootingLogs: NSWindow?
    private var statusItem: NSStatusItem?
    private lazy var statusMenu = makeStatusMenu()
    private enum StatusMenuRow: Int {
        case summary = 1, mcp, glyphs, tasks, notice, recovery, server, quit
    }
    private var taskObservation: AnyCancellable?
    private var taskMenuTracking: NSObjectProtocol?
    private var preferences: NSObjectProtocol?
    private var activityObservation: AnyCancellable?
    private var componentUpdateObservation: AnyCancellable?
    private var componentDialogObservers: [NSObjectProtocol] = []
    private var menuImages: [Bool: NSImage] = [:]
    private weak var activityDot: DesktopActivityDot?

    func applicationDidFinishLaunching(_ notification: Notification) {
        _ = updates
        componentUpdateObservation = installer.objectWillChange.sink { [weak self] _ in
            DispatchQueue.main.async { self?.presentComponentUpdateReminder() }
        }
        for name in [NSWindow.didBecomeKeyNotification, NSWindow.didEndSheetNotification,
                     NSApplication.didBecomeActiveNotification] {
            componentDialogObservers.append(NotificationCenter.default.addObserver(forName: name,
                object: nil, queue: .main) { [weak self] _ in
                    Task { @MainActor in self?.presentComponentUpdateReminder() }
                })
        }
        installer.stopServiceBeforeQuit = { [weak self] in try await self?.desktop.stopForInstallation() }
        installer.showTroubleshootingLogs = { [weak self] in self?.showTroubleshootingLogs() }
        updateMenuBar()
        taskObservation = desktop.objectWillChange.sink { [weak self] _ in
            DispatchQueue.main.async {
                self?.updateTaskMenuBadge()
                self?.updateStatusMenu()
            }
        }
        taskMenuTracking = NotificationCenter.default.addObserver(forName: NSMenu.didBeginTrackingNotification,
            object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.updateTaskMenuBadge() }
            }
        activityObservation = Publishers.CombineLatest3(desktop.$status, desktop.$stale, desktop.$serviceRunning)
            .map { status, stale, running in status?.showsActivityDot(stale: stale, running: running) == true }
            .removeDuplicates()
            .sink { [weak self] active in self?.updateMenuActivity(active) }
        preferences = NotificationCenter.default.addObserver(forName: UserDefaults.didChangeNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.updateMenuBar() }
        }
        desktop.onWelcome = { [weak self] in self?.showWelcome() }
        let event = NSAppleEventManager.shared().currentAppleEvent
        let login = event?.paramDescriptor(forKeyword: AEKeyword(keyAEPropData))?.enumCodeValue == OSType(keyAELaunchedAsLogInItem)
        if DesktopLaunchPolicy.showsWelcome(loginLaunch: login, defaults: .standard) {
            initialWelcome = true
            showWelcome()
        } else if DesktopLaunchPolicy.showsDashboard(loginLaunch: login) { showDashboard() }
        // Discovery begins after presentation, never in the delegate's initializer.
        Task { @MainActor [weak self] in self?.installer.refresh(resetFailures: true) }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if initialWelcome { showWelcome() } else { showDashboard() }
        return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        installer.operationsBusy ? .terminateCancel : .terminateNow
    }
    func applicationWillTerminate(_ notification: Notification) {
        desktop.setVisible("statusMenu", false); desktop.setDashboardVisible(false)
        desktop.setMenuBarVisible(false)
        if let item = statusItem { NSStatusBar.system.removeStatusItem(item) }
        // Sidecar startup is a separate preference; quitting this interface does
        // not send a service stop request.
    }

    @objc func showTasks() {
        desktop.requestTasks()
        showDashboard()
    }

    private func taskMenuItem() -> NSMenuItem {
        let item = NSMenuItem(title: NSLocalizedString("Show Tasks", comment: "Task navigation"), action: #selector(showTasks), keyEquivalent: "")
        item.target = self
        if desktop.unreadTaskCount > 0 { item.badge = .newItems(count: desktop.unreadTaskCount) }
        return item
    }
    private func updateTaskMenuBadge() {
        // SwiftUI owns and can rebuild its commands. Find the current menu item
        // rather than retaining an item from an earlier menu generation.
        guard let menu = NSApp.mainMenu?.items.first?.submenu,
              let item = menu.items.first(where: { $0.title == NSLocalizedString("Show Tasks", comment: "Task navigation") }) else { return }
        item.badge = desktop.unreadTaskCount > 0 ? .newItems(count: desktop.unreadTaskCount) : nil
    }
    func applicationDockMenu(_ sender: NSApplication) -> NSMenu? {
        let menu = NSMenu()
        menu.addItem(taskMenuItem())
        let open = NSMenuItem(title: NSLocalizedString("Show Window", comment: "Dock navigation"), action: #selector(openDashboardFromMenu), keyEquivalent: "")
        open.target = self; menu.addItem(open)
        return menu
    }
    @objc private func openDashboardFromMenu() { showDashboard() }

    func showDashboard() {
        statusMenu.cancelTracking()
        if dashboard == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0,
                width: DesktopDashboardLayout.initialWidth, height: DesktopDashboardLayout.initialHeight),
                styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            window.title = DesktopIdentity.applicationTitle
            window.identifier = NSUserInterfaceItemIdentifier("glyphs-mcp-dashboard")
            window.setFrameAutosaveName("Glyphs MCP Dashboard")
            window.contentMinSize = NSSize(width: DesktopDashboardLayout.minimumWidth,
                                           height: DesktopDashboardLayout.minimumHeight)
            window.isReleasedWhenClosed = false; window.delegate = self
            window.contentViewController = NSHostingController(rootView: ContentView().environmentObject(installer).environmentObject(desktop).desktopDesign())
            // Use one window-wide separator instead of automatic per-column styles.
            window.titlebarSeparatorStyle = .line
            window.center(); dashboard = window
        }
        NSApp.setActivationPolicy(.regular)
        dashboard?.deminiaturize(nil); dashboard?.makeKeyAndOrderFront(nil)
        recordFirstPresentation("Dashboard presentation")
        NSApp.activate(ignoringOtherApps: true)
        desktop.setDashboardVisible(true)
        presentComponentUpdateReminder()
    }

    private func presentComponentUpdateReminder() {
        let interactive = !initialWelcome && NSApp.isActive && dashboard?.isVisible == true
            && dashboard?.isMiniaturized == false && welcome?.isVisible != true
        let otherDialog = NSApp.modalWindow != nil || NSApp.windows.contains { $0.attachedSheet != nil }
        let key = installer.componentUpdateReminderKey
        guard ComponentUpdateReminder.shouldPresent(statuses: installer.componentUpdates,
            alreadyShown: UserDefaults.standard.bool(forKey: key), interactive: interactive,
            busy: installer.operationsBusy, otherDialog: otherDialog), let dashboard else { return }
        let alert = NSAlert()
        let needsServerUpdate = installer.componentUpdates["mcp"] == .updateAvailable
        alert.alertStyle = .informational
        alert.messageText = NSLocalizedString(ComponentUpdateReminder.title(needsServerUpdate: needsServerUpdate), comment: "Component update reminder headline")
        alert.informativeText = NSLocalizedString(ComponentUpdateReminder.message(needsServerUpdate: needsServerUpdate), comment: "Component update reminder guidance")
        // Give the headline and two short paragraphs room while retaining native alert behavior.
        alert.accessoryView = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 0))
        alert.addButton(withTitle: NSLocalizedString("Open Setup", comment: "Component update reminder action"))
        alert.addButton(withTitle: NSLocalizedString("Later", comment: "Component update reminder action"))
        alert.beginSheetModal(for: dashboard) { [weak self] response in
            if response == .alertFirstButtonReturn {
                self?.desktop.requestSetup()
                self?.showDashboard()
            }
        }
        UserDefaults.standard.set(true, forKey: key)
    }

    private func recordFirstPresentation(_ name: String) {
        guard !firstPresentationRecorded else { return }
        firstPresentationRecorded = true
        installer.recordPresentation(name, since: initializationStartedAt)
    }

    @objc func showSettings() {
        statusMenu.cancelTracking()
        if settingsWindow == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 532, height: 740),
                styleMask: [.titled, .closable], backing: .buffered, defer: false)
            window.title = NSLocalizedString("Settings…", comment: "Settings window title")
            window.identifier = NSUserInterfaceItemIdentifier("glyphs-mcp-settings")
            window.isReleasedWhenClosed = false
            window.contentViewController = NSHostingController(rootView:
                DesktopSettings(updates: updates).environmentObject(desktop)
                    .desktopDesign().frame(height: 740))
            window.center()
            settingsWindow = window
        }
        NSApp.setActivationPolicy(.regular)
        settingsWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func showWelcome() {
        statusMenu.cancelTracking()
        if welcome == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 640),
                styleMask: [.titled, .closable], backing: .buffered, defer: false)
            window.title = NSLocalizedString("Welcome & Support", comment: "Welcome window title")
            window.titleVisibility = .hidden
            window.titlebarAppearsTransparent = true
            window.isReleasedWhenClosed = false
            window.delegate = self
            window.center(); welcome = window
        }
        // A new root resets slide navigation on manual replay.
        welcome?.contentViewController = NSHostingController(rootView: DesktopWelcomeView(
            startSetup: { [weak self] in self?.finishWelcome() })
            .safeAreaInset(edge: .top) { DesktopInitializationStatus().environmentObject(installer) }
            .desktopDesign())
        NSApp.setActivationPolicy(.regular)
        welcome?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        recordFirstPresentation("Welcome presentation")
        // Desktop presentation is manual and never changes the bridge's
        // first-successful-display preference.
    }

    private func finishWelcome() {
        DesktopLaunchPolicy.completeWelcome(defaults: .standard)
        initialWelcome = false
        welcome?.close()
        desktop.requestSetup()
        showDashboard()
    }

    func showTroubleshootingLogs() {
        if troubleshootingLogs == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 980, height: 620),
                styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            window.title = NSLocalizedString("Glyphs MCP Logs", comment: "Troubleshooting log window title")
            window.identifier = NSUserInterfaceItemIdentifier("glyphs-mcp-logs")
            window.setFrameAutosaveName("Glyphs MCP Logs")
            window.contentMinSize = NSSize(width: 760, height: 480)
            window.isReleasedWhenClosed = false
            window.contentViewController = NSHostingController(rootView:
                TroubleshootingLogView().environmentObject(installer).environmentObject(desktop).desktopDesign())
            window.center()
            troubleshootingLogs = window
        }
        troubleshootingLogs?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func updateMenuBar() {
        let visible = DesktopLaunchPolicy.showsMenuBar(defaults: .standard)
        if visible && statusItem == nil {
            let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
            if let logo = NSImage(named: "GlyphsMCPMenu") {
                menuImages = [false: DesktopMenuImage.make(logo: logo, active: false),
                              true: DesktopMenuImage.make(logo: logo, active: true)]
            }
            item.button?.setAccessibilityLabel(NSLocalizedString("Glyphs MCP — server status", comment: "Menu bar accessibility label"))
            item.menu = statusMenu
            if let button = item.button {
                let dot = DesktopActivityDot(frame: .zero)
                dot.translatesAutoresizingMaskIntoConstraints = false
                dot.setAccessibilityElement(false)
                button.addSubview(dot)
                NSLayoutConstraint.activate([
                    dot.widthAnchor.constraint(equalToConstant: 4),
                    dot.heightAnchor.constraint(equalToConstant: 4),
                    dot.centerXAnchor.constraint(equalTo: button.centerXAnchor, constant: 10),
                    dot.centerYAnchor.constraint(equalTo: button.centerYAnchor),
                ])
                activityDot = dot
            }
            statusItem = item
            updateMenuActivity(desktop.showsActivityDot)
        } else if !visible, let item = statusItem {
            statusMenu.cancelTracking()
            NSStatusBar.system.removeStatusItem(item); statusItem = nil
            NSApp.setActivationPolicy(.regular)
        }
        desktop.setMenuBarVisible(visible)
    }

    private func updateMenuActivity(_ active: Bool) {
        statusItem?.button?.image = menuImages[active]
        activityDot?.isHidden = !active
        statusItem?.button?.toolTip = NSLocalizedString(active ? "Glyphs MCP — task in progress" : "Glyphs MCP — open server status", comment: "Menu bar tooltip")
        statusItem?.button?.setAccessibilityValue(NSLocalizedString(active ? "Task in progress" : "No activity indicated", comment: "Menu bar activity"))
    }

    private func makeStatusMenu() -> NSMenu {
        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.delegate = self
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        menu.addItem(.sectionHeader(title: "Glyphs MCP \(version)".trimmingCharacters(in: .whitespaces)))
        for row in [StatusMenuRow.summary, .mcp, .glyphs] {
            let item = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            item.tag = row.rawValue
            item.isEnabled = false
            menu.addItem(item)
        }
        menu.addItem(.separator())
        let tasks = taskMenuItem()
        tasks.tag = StatusMenuRow.tasks.rawValue
        tasks.image = NSImage(systemSymbolName: "list.bullet", accessibilityDescription: nil)
        menu.addItem(tasks)
        let notice = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        notice.tag = StatusMenuRow.notice.rawValue
        notice.isEnabled = false
        menu.addItem(notice)
        func action(_ title: String, _ selector: Selector, symbol: String,
                    row: StatusMenuRow? = nil, key: String = "") {
            let item = NSMenuItem(title: NSLocalizedString(title, comment: "Status menu action"),
                                  action: selector, keyEquivalent: key)
            item.target = self
            item.image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)
            if let row { item.tag = row.rawValue }
            menu.addItem(item)
        }
        action("Check Glyphs in Setup", #selector(openSetupFromMenu), symbol: "exclamationmark.triangle", row: .recovery)
        menu.addItem(.separator())
        action("Stop Server", #selector(toggleServerFromMenu), symbol: "stop.circle", row: .server)
        action("Open Glyphs MCP", #selector(openDashboardFromMenu), symbol: "macwindow")
        menu.addItem(.separator())
        action("Settings…", #selector(showSettings), symbol: "gearshape", key: ",")
        action("Welcome & Support", #selector(showWelcome), symbol: "heart.circle")
        action("Quit Glyphs MCP", #selector(quitFromMenu), symbol: "power", row: .quit, key: "q")
        return menu
    }

    private func updateStatusMenu() {
        func item(_ row: StatusMenuRow) -> NSMenuItem? { statusMenu.item(withTag: row.rawValue) }
        func localized(_ text: String) -> String { NSLocalizedString(text, comment: "Server status") }
        item(.summary)?.title = localized(desktop.title)
        item(.summary)?.image = NSImage(systemSymbolName: desktop.statusSymbol, accessibilityDescription: nil)
        let connected = desktop.serviceRunning == true && !desktop.stale
        item(.mcp)?.title = "MCP: " + localized(connected ? "Connected" : desktop.serviceRunning == false ? "Stopped" : "Unavailable")
        item(.glyphs)?.title = "Glyphs 4: " + localized(desktop.glyphsRunning ? "Running" : "Not running")
        for (row, available) in [(StatusMenuRow.mcp, connected), (.glyphs, desktop.glyphsRunning)] {
            let configuration = NSImage.SymbolConfiguration(paletteColors: [available ? .systemGreen : .secondaryLabelColor])
            let image = NSImage(systemSymbolName: "circle.fill", accessibilityDescription: nil)?
                .withSymbolConfiguration(configuration)
            image?.isTemplate = false
            item(row)?.image = image
        }
        item(.tasks)?.badge = desktop.unreadTaskCount > 0 ? .newItems(count: desktop.unreadTaskCount) : nil
        item(.notice)?.title = desktop.notice
        item(.notice)?.isHidden = desktop.notice.isEmpty
        item(.recovery)?.isHidden = !desktop.needsGlyphsRecovery
        let starts = desktop.serviceRunning == false
        item(.server)?.title = localized(desktop.controlProgress ?? (starts ? "Start Server" : "Stop Server"))
        item(.server)?.image = NSImage(systemSymbolName: starts ? "play.circle" : "stop.circle", accessibilityDescription: nil)
        item(.server)?.isEnabled = desktop.canChangeSettings
        item(.server)?.toolTip = localized(desktop.status?.isBusy == true
            ? "Wait for the current operation to finish." : "Start or stop the MCP server.")
        item(.quit)?.toolTip = localized(desktop.serviceRunning == true
            ? "Quit the desktop app. The MCP server keeps running." : "Quit the desktop app.")
    }

    func menuWillOpen(_ menu: NSMenu) {
        guard menu === statusMenu else { return }
        updateStatusMenu()
        desktop.setVisible("statusMenu", true)
    }
    func menuDidClose(_ menu: NSMenu) {
        guard menu === statusMenu else { return }
        desktop.setVisible("statusMenu", false)
    }
    @objc private func openSetupFromMenu() { desktop.requestSetup(); showDashboard() }
    @objc private func toggleServerFromMenu() {
        guard desktop.canChangeSettings else { return }
        desktop.control(desktop.serviceRunning == false ? "start" : "stop")
    }
    @objc private func quitFromMenu() { NSApp.terminate(nil) }
    func windowWillClose(_ notification: Notification) {
        if notification.object as? NSWindow === welcome {
            DesktopLaunchPolicy.completeWelcome(defaults: .standard)
            if initialWelcome {
                initialWelcome = false
                showDashboard()
            }
            return
        }
        guard notification.object as? NSWindow === dashboard else { return }
        desktop.setDashboardVisible(false)
        if statusItem != nil { NSApp.setActivationPolicy(.accessory) }
    }
    func windowDidMiniaturize(_ notification: Notification) { desktop.setDashboardVisible(false) }
    func windowDidDeminiaturize(_ notification: Notification) { desktop.setDashboardVisible(true) }
    func windowDidChangeOcclusionState(_ notification: Notification) {
        desktop.setDashboardVisible(dashboard?.isVisible == true && dashboard?.occlusionState.contains(.visible) == true)
    }
}

struct DesktopSettings: View {
    @EnvironmentObject private var desktop: DesktopModel
    @ObservedObject var updates: DesktopUpdates
    @AppStorage(DesktopIdentity.showMenuBarKey) private var showMenuBar = true
    @State private var loginEnabled = SMAppService.mainApp.status == .enabled
    @State private var loginError = ""
    @State private var port = ""
    @State private var taskExpiryDays = 1
    @State private var taskExpiryError = ""
    var body: some View {
        Form {
            Section("Desktop") {
                Toggle("Show Glyphs MCP in the menu bar", isOn: $showMenuBar)
                Toggle("Open Glyphs MCP at login", isOn: Binding(get: { loginEnabled }, set: setLogin))
                if showMenuBar { Text("At login, open in the menu bar without showing the main window.").font(.caption).foregroundStyle(.secondary) }
                if !loginError.isEmpty { Text(LocalizedStringKey(loginError)).foregroundStyle(.secondary) }
            }
            Section("MCP Server") {
                Toggle("Start the MCP server at login", isOn: Binding(get: { desktop.installation.autoStart }, set: { desktop.control($0 ? "auto-on" : "auto-off") }))
                    .disabled(desktop.controlling || !desktop.installation.hasServer)
                HStack {
                    TextField("MCP port", text: $port).frame(width: 160)
                    Button("Apply Port") { desktop.control("port", value: port) }.disabled(!desktop.canChangeSettings)
                }
                Text("Finish the current font task before changing the MCP port. Update your AI connections to use the new port.").font(.caption).foregroundStyle(.secondary)
                if !desktop.notice.isEmpty { Text(desktop.notice).font(.callout).foregroundStyle(.secondary) }
            }
            Section("Application updates") {
                Toggle("Automatically check for updates", isOn: Binding(get: { updates.automaticChecks }, set: { updates.automaticChecks = $0 }))
                Text("Choose when to install app updates. Manage Glyphs components and agent connections in Setup.").font(.caption).foregroundStyle(.secondary)
                Button("Check for Updates…", action: updates.check).disabled(!updates.canCheck)
                if !updates.message.isEmpty { Text(updates.message).font(.caption).foregroundStyle(.secondary) }
            }
            Section("Tasks") {
                Picker("Expire inactive tasks after", selection: Binding(get: { taskExpiryDays }, set: setTaskExpiry)) {
                    Text("1 day").tag(1)
                    Text("7 days").tag(7)
                    Text("30 days").tag(30)
                    Text("90 days").tag(90)
                    if ![1, 7, 30, 90].contains(taskExpiryDays) { Text("\(taskExpiryDays) days").tag(taskExpiryDays) }
                }
                Text("Inactive tasks move to Finished as Expired. Work in progress and available recovery are kept. History and diagnostics remain available.")
                    .font(.caption).foregroundStyle(.secondary)
                if !taskExpiryError.isEmpty { Text(taskExpiryError).font(.caption).foregroundStyle(.secondary) }
            }
        }.formStyle(.grouped).frame(width: 500).padding()
        .onAppear {
            port = String(desktop.installation.port)
            do { taskExpiryDays = try DesktopTaskExpiryPolicy.read(under: desktop.installation.root).inactivityDays }
            catch { taskExpiryError = error.localizedDescription }
        }
        .task { await desktop.refresh() }
    }
    private func setLogin(_ enabled: Bool) {
        do {
            if enabled { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
            loginEnabled = SMAppService.mainApp.status == .enabled
            loginError = SMAppService.mainApp.status == .requiresApproval ? "Allow Glyphs MCP in System Settings → Login Items." : ""
        } catch { loginError = error.localizedDescription }
    }
    private func setTaskExpiry(_ days: Int) {
        do {
            try DesktopTaskExpiryPolicy(inactivityDays: days).write(under: desktop.installation.root)
            taskExpiryDays = days
            taskExpiryError = ""
        } catch { taskExpiryError = error.localizedDescription }
    }
}
