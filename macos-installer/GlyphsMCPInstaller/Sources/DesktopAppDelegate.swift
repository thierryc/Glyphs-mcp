import AppKit
import Combine
import ServiceManagement
import SwiftUI
import GlyphsMCPInstallerCore

@MainActor
final class DesktopAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSPopoverDelegate {
    let desktop = DesktopModel()
    let installer = InstallerViewModel()
    lazy var updates = DesktopUpdates(installationBusy: { [weak self] in self?.installer.busy == true })
    private var dashboard: NSWindow?
    private var welcome: NSWindow?
    private var troubleshootingLogs: NSWindow?
    private var statusItem: NSStatusItem?
    private let popover = NSPopover()
    private var preferences: NSObjectProtocol?
    private var activityObservation: AnyCancellable?
    private var menuImages: [Bool: NSImage] = [:]
    private weak var activityDot: DesktopActivityDot?

    func applicationDidFinishLaunching(_ notification: Notification) {
        _ = updates
        installer.stopServiceBeforeQuit = { [weak self] in try await self?.desktop.stopForInstallation() }
        installer.showTroubleshootingLogs = { [weak self] in self?.showTroubleshootingLogs() }
        popover.behavior = .transient
        popover.animates = false
        popover.delegate = self
        popover.contentViewController = NSHostingController(rootView: DesktopPopover(
            open: { [weak self] in self?.showDashboard() },
            settings: { [weak self] in self?.showSettings() },
            support: { [weak self] in self?.showWelcome() }).environmentObject(desktop))
        updateMenuBar()
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
        if DesktopLaunchPolicy.showsDashboard(loginLaunch: login) { showDashboard() }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showDashboard(); return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        installer.busy ? .terminateCancel : .terminateNow
    }
    func applicationWillTerminate(_ notification: Notification) {
        desktop.setVisible("popover", false); desktop.setDashboardVisible(false)
        desktop.setMenuBarVisible(false)
        if let item = statusItem { NSStatusBar.system.removeStatusItem(item) }
        // Sidecar startup is a separate preference; quitting this interface does
        // not send a service stop request.
    }

    func showDashboard() {
        popover.performClose(nil)
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
            window.contentViewController = NSHostingController(rootView: ContentView().environmentObject(installer).environmentObject(desktop))
            // Use one window-wide separator instead of automatic per-column styles.
            window.titlebarSeparatorStyle = .line
            window.center(); dashboard = window
        }
        NSApp.setActivationPolicy(.regular)
        dashboard?.deminiaturize(nil); dashboard?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        desktop.setDashboardVisible(true)
    }

    func showSettings() {
        popover.performClose(nil)
        NSApp.activate(ignoringOtherApps: true)
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
    }

    func showWelcome() {
        popover.performClose(nil)
        if welcome == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 440, height: 610),
                styleMask: [.titled, .closable], backing: .buffered, defer: false)
            window.title = "Welcome & Support"
            window.titleVisibility = .hidden
            window.titlebarAppearsTransparent = true
            window.isReleasedWhenClosed = false
            window.contentViewController = NSHostingController(rootView: DesktopWelcomeView(close: { [weak self] in self?.welcome?.close() }))
            window.center(); welcome = window
        }
        welcome?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        // Desktop presentation is manual and never changes the bridge's
        // first-successful-display preference.
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
                TroubleshootingLogView().environmentObject(installer).environmentObject(desktop))
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
            item.button?.setAccessibilityLabel("Glyphs MCP — server status")
            item.button?.target = self; item.button?.action = #selector(togglePopover)
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
            popover.performClose(nil)
            NSStatusBar.system.removeStatusItem(item); statusItem = nil
            NSApp.setActivationPolicy(.regular)
        }
        desktop.setMenuBarVisible(visible)
    }

    private func updateMenuActivity(_ active: Bool) {
        statusItem?.button?.image = menuImages[active]
        activityDot?.isHidden = !active
        statusItem?.button?.toolTip = active ? "Glyphs MCP — task in progress" : "Glyphs MCP — open server status"
        statusItem?.button?.setAccessibilityValue(active ? "Task in progress" : "No activity indicated")
    }

    @objc private func togglePopover() {
        guard let button = statusItem?.button else { return }
        if popover.isShown { popover.performClose(nil) }
        else { popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY) }
    }
    func popoverDidShow(_ notification: Notification) { desktop.setVisible("popover", true) }
    func popoverDidClose(_ notification: Notification) { desktop.setVisible("popover", false) }
    func windowWillClose(_ notification: Notification) {
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

struct DesktopPopover: View {
    @EnvironmentObject private var desktop: DesktopModel
    let open: () -> Void
    let settings: () -> Void
    let support: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("Glyphs MCP").font(.headline)
                    if let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String {
                        Text(version)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .help(DesktopIdentity.versionLabel)
                    }
                }
                Spacer()
                Text(desktop.title).foregroundStyle(.secondary)
            }
            DesktopActivityView()
            if !desktop.notice.isEmpty { Text(desktop.notice).font(.caption).foregroundStyle(.secondary) }
            Divider()
            HStack { DesktopServerButton(); Spacer(); Button("Open Glyphs MCP", action: open) }
            HStack {
                Button("Settings…", action: settings)
                Spacer()
                Button(action: support) { Image(systemName: "heart.circle") }.help("Welcome & Support").accessibilityLabel("Welcome & Support")
                Button("Quit Glyphs MCP") { NSApp.terminate(nil) }
                    .help(desktop.serviceRunning == true ? "Quit the desktop app. The MCP server keeps running." : "Quit the desktop app.")
            }.font(.callout)
        }.padding(18).frame(width: 340)
    }
}

struct DesktopSettings: View {
    @EnvironmentObject private var desktop: DesktopModel
    @ObservedObject var updates: DesktopUpdates
    @AppStorage(DesktopIdentity.showMenuBarKey) private var showMenuBar = true
    @State private var loginEnabled = SMAppService.mainApp.status == .enabled
    @State private var loginError = ""
    @State private var port = ""
    var body: some View {
        Form {
            Section("Desktop") {
                Toggle("Show Glyphs MCP in the menu bar", isOn: $showMenuBar)
                Toggle("Open Glyphs MCP at login", isOn: Binding(get: { loginEnabled }, set: setLogin))
                if showMenuBar { Text("At login, open in the menu bar without showing the main window.").font(.caption).foregroundStyle(.secondary) }
                if !loginError.isEmpty { Text(loginError).foregroundStyle(.secondary) }
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
        }.formStyle(.grouped).frame(width: 500).padding()
        .onAppear { port = String(desktop.installation.port) }
        .task { await desktop.refresh() }
    }
    private func setLogin(_ enabled: Bool) {
        do {
            if enabled { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
            loginEnabled = SMAppService.mainApp.status == .enabled
            loginError = SMAppService.mainApp.status == .requiresApproval ? "Allow Glyphs MCP in System Settings → Login Items." : ""
        } catch { loginError = error.localizedDescription }
    }
}
