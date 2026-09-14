import AppKit
import Combine
import Sparkle
import GlyphsMCPInstallerCore

@MainActor
final class DesktopUpdates: NSObject, ObservableObject, SPUUpdaterDelegate {
    @Published private(set) var canCheck = false
    @Published private(set) var message = ""
    private var controller: SPUStandardUpdaterController!
    private var observation: AnyCancellable?
    private let installationBusy: () -> Bool

    init(installationBusy: @escaping () -> Bool) {
        self.installationBusy = installationBusy
        super.init()
        controller = SPUStandardUpdaterController(startingUpdater: false, updaterDelegate: self, userDriverDelegate: nil)
        controller.updater.automaticallyDownloadsUpdates = false
        observation = controller.updater.publisher(for: \.canCheckForUpdates)
            .receive(on: RunLoop.main).sink { [weak self] in self?.canCheck = $0 }
        do { try controller.updater.start() } catch { message = error.localizedDescription }
    }
    var automaticChecks: Bool {
        get { controller.updater.automaticallyChecksForUpdates }
        set { controller.updater.automaticallyChecksForUpdates = newValue; objectWillChange.send() }
    }
    func check() { controller.checkForUpdates(nil) }

    func updater(_ updater: SPUUpdater, mayPerform updateCheck: SPUUpdateCheck) throws {
        if installationBusy() { throw ProjectError("Finish the component installation before checking for an application update.") }
    }
    func updater(_ updater: SPUUpdater, shouldProceedWithUpdate updateItem: SUAppcastItem, updateCheck: SPUUpdateCheck) throws {
        if installationBusy() { throw ProjectError("Finish the component installation before updating Glyphs MCP.") }
    }
    func updater(_ updater: SPUUpdater, didAbortWithError error: Error) { message = error.localizedDescription }
    func updater(_ updater: SPUUpdater, didFinishUpdateCycleFor updateCheck: SPUUpdateCheck, error: Error?) {
        if let error { message = error.localizedDescription }
        else { message = "" }
    }
}
