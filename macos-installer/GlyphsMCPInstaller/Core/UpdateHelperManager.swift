import Foundation

public struct UpdateHelperInstallationReceipt: Codable, Equatable {
	public let protocolVersion: Int
	public let helperVersion: String
	public let teamIdentifier: String
	public let executableSHA256: String
	public let installedAt: Date
}

public struct VerifiedUpdateHelper: Equatable {
	public let executableURL: URL
	public let probe: UpdateHelperProbe
	public let cdHash: String
	public let teamIdentifier: String
	public let authority: String
}

public struct UpdateOptInStore {
	public let isEnabled: @Sendable (GlyphsMajorVersion) -> Bool
	public let setEnabled: @Sendable (GlyphsMajorVersion, Bool) -> Void

	public init(
		isEnabled: @escaping @Sendable (GlyphsMajorVersion) -> Bool,
		setEnabled: @escaping @Sendable (GlyphsMajorVersion, Bool) -> Void
	) {
		self.isEnabled = isEnabled
		self.setEnabled = setEnabled
	}

	public static let live = UpdateOptInStore(
		isEnabled: { version in
			UserDefaults(suiteName: GlyphsPreferences.suiteName(glyphsVersion: version))?
				.bool(forKey: UpdateHelperProtocol.optInDefaultsKey) ?? false
		},
		setEnabled: { version, enabled in
			guard let defaults = UserDefaults(
				suiteName: GlyphsPreferences.suiteName(glyphsVersion: version)
			) else { return }
			defaults.set(enabled, forKey: UpdateHelperProtocol.optInDefaultsKey)
			defaults.synchronize()
		}
	)

	public func enabledVersions() -> Set<GlyphsMajorVersion> {
		Set(GlyphsMajorVersion.allCases.filter(isEnabled))
	}
}

public struct UpdateHelperVerifier {
	public let verify: @Sendable (URL) throws -> VerifiedUpdateHelper

	public init(verify: @escaping @Sendable (URL) throws -> VerifiedUpdateHelper) {
		self.verify = verify
	}

	public static func live(
		runner: UpdateCommandRunner = .live,
		allowDevelopmentSignature: Bool = false
	) -> UpdateHelperVerifier {
		UpdateHelperVerifier { executable in
			guard executable.standardizedFileURL.path == executable.path,
				  FileManager.default.fileExists(atPath: executable.path),
				  (try executable.resourceValues(forKeys: [.isRegularFileKey])).isRegularFile == true else {
				throw UpdateStagingError("helper_missing", "The updater helper is missing or invalid.")
			}

			_ = try runner.run(
				URL(fileURLWithPath: "/usr/bin/codesign"),
				["--verify", "--strict", "--verbose=2", executable.path]
			)
			let details = try runner.run(
				URL(fileURLWithPath: "/usr/bin/codesign"),
				["-d", "--verbose=4", executable.path]
			)
			func signatureField(_ name: String) -> String? {
				details
					.split(separator: "\n")
					.map(String.init)
					.first(where: { $0.hasPrefix("\(name)=") })?
					.dropFirst(name.count + 1)
					.description
			}

			let team = signatureField("TeamIdentifier") ?? ""
			let authority = signatureField("Authority") ?? ""
			guard team == UpdateHelperProtocol.expectedTeamIdentifier else {
				throw UpdateStagingError("helper_signature", "The updater helper is signed by an unexpected developer team.")
			}
			let productionAuthority = authority == UpdateHelperProtocol.expectedDeveloperIDAuthority
			let developmentAuthority = allowDevelopmentSignature && authority.hasPrefix("Apple Development:")
			guard productionAuthority || developmentAuthority else {
				throw UpdateStagingError("helper_signature", "The updater helper has an unexpected signing authority.")
			}
			guard details.range(of: #"flags=.*\(runtime\)"#, options: .regularExpression) != nil else {
				throw UpdateStagingError("helper_signature", "The updater helper is missing the hardened runtime.")
			}
			if !allowDevelopmentSignature {
				guard details.split(separator: "\n").contains(where: { $0.hasPrefix("Timestamp=") }) else {
					throw UpdateStagingError("helper_signature", "The updater helper is missing a secure timestamp.")
				}
			}
			guard let cdHash = signatureField("CDHash"), !cdHash.isEmpty else {
				throw UpdateStagingError("helper_signature", "The updater helper signature has no CDHash.")
			}

			let probeData = try runner.run(executable, ["probe", "--json"]).data(using: .utf8) ?? Data()
			let probe: UpdateHelperProbe
			do {
				probe = try JSONDecoder().decode(UpdateHelperProbe.self, from: probeData)
			} catch {
				throw UpdateStagingError("helper_protocol", "The updater helper returned an invalid probe response.")
			}
			guard probe.protocolVersion == UpdateHelperProtocol.currentVersion,
				  probe.teamIdentifier == UpdateHelperProtocol.expectedTeamIdentifier,
				  probe.capabilities.contains("prepare") else {
				throw UpdateStagingError("helper_protocol", "The updater helper is not compatible with this plug-in.")
			}
			return VerifiedUpdateHelper(
				executableURL: executable,
				probe: probe,
				cdHash: cdHash,
				teamIdentifier: team,
				authority: authority
			)
		}
	}
}

public struct UpdateHelperManager {
	public let paths: UpdateStagingPaths
	public let store: UpdateOptInStore
	public let verifier: UpdateHelperVerifier
	public let fileManager: FileManager
	public let now: @Sendable () -> Date

	public init(
		paths: UpdateStagingPaths = UpdateStagingPaths(),
		store: UpdateOptInStore = .live,
		verifier: UpdateHelperVerifier? = nil,
		fileManager: FileManager = .default,
		now: @escaping @Sendable () -> Date = { Date() }
	) {
		self.paths = paths
		self.store = store
		self.fileManager = fileManager
		self.now = now
#if DEBUG
		self.verifier = verifier ?? .live(allowDevelopmentSignature: true)
#else
		self.verifier = verifier ?? .live()
#endif
	}

	public static func embeddedExecutable(in bundle: Bundle = .main) -> URL? {
		bundle.url(forResource: UpdateHelperProtocol.executableName, withExtension: nil)
	}

	public func configure(
		embeddedExecutable: URL?,
		selections: [GlyphsMajorVersion: Bool]
	) throws {
		var desired = Dictionary(
			uniqueKeysWithValues: GlyphsMajorVersion.allCases.map { ($0, store.isEnabled($0)) }
		)
		for (version, enabled) in selections {
			desired[version] = enabled
		}

		if desired.values.contains(true) {
			guard let embeddedExecutable else {
				throw UpdateStagingError("helper_missing", "The signed installer does not contain the updater helper.")
			}
			try installAtomically(from: embeddedExecutable)
		}

		for (version, enabled) in selections {
			store.setEnabled(version, enabled)
			if !enabled {
				try removeAuthorizations(for: version)
			}
		}

		if !desired.values.contains(true) {
			try removeManagedUpdaterIfPresent()
		}
	}

	@discardableResult
	public func installAtomically(from source: URL) throws -> UpdateHelperInstallationReceipt {
		let sourceVerification = try verifier.verify(source)
		let rootExistedBeforeInstall = GlyphsUninstallScanner.itemExists(
			at: paths.root,
			fileManager: fileManager
		)
		let temporary = paths.root.appendingPathComponent(".helper-\(UUID().uuidString.lowercased()).tmp")
		let backup = paths.root.appendingPathComponent(".helper-backup-\(UUID().uuidString.lowercased())")
		let receiptBackup = paths.root.appendingPathComponent(".helper-receipt-backup-\(UUID().uuidString.lowercased())")
		var installationSucceeded = false
		defer {
			try? removeIfPresent(temporary)
			try? removeIfPresent(backup)
			try? removeIfPresent(receiptBackup)
			if !installationSucceeded && !rootExistedBeforeInstall {
				try? fileManager.removeItem(at: paths.root)
			}
		}
		try ensureSafeRoot()
		try removeIfPresent(temporary)
		try removeIfPresent(backup)
		try removeIfPresent(receiptBackup)

		try fileManager.copyItem(at: source, to: temporary)
		try fileManager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: temporary.path)
		let temporaryVerification = try verifier.verify(temporary)
		guard temporaryVerification.cdHash == sourceVerification.cdHash,
			  temporaryVerification.teamIdentifier == sourceVerification.teamIdentifier else {
			throw UpdateStagingError("helper_signature", "The updater helper changed while it was copied.")
		}

		let hadExisting = GlyphsUninstallScanner.itemExists(at: paths.helperExecutable, fileManager: fileManager)
		let hadReceipt = GlyphsUninstallScanner.itemExists(at: paths.installReceipt, fileManager: fileManager)
		do {
			if hadExisting {
				try fileManager.moveItem(at: paths.helperExecutable, to: backup)
			}
			if hadReceipt {
				try fileManager.moveItem(at: paths.installReceipt, to: receiptBackup)
			}
			try fileManager.moveItem(at: temporary, to: paths.helperExecutable)
			let installed = try verifier.verify(paths.helperExecutable)
			guard installed.cdHash == sourceVerification.cdHash,
				  installed.teamIdentifier == sourceVerification.teamIdentifier else {
				throw UpdateStagingError("helper_signature", "The installed updater helper failed verification.")
			}
			let executableData = try Data(contentsOf: paths.helperExecutable, options: .mappedIfSafe)
			let receipt = UpdateHelperInstallationReceipt(
				protocolVersion: UpdateHelperProtocol.currentVersion,
				helperVersion: sourceVerification.probe.helperVersion,
				teamIdentifier: installed.teamIdentifier,
				executableSHA256: UpdateChecksumManifest.sha256(executableData),
				installedAt: now()
			)
			try writeJSON(receipt, to: paths.installReceipt)
			try Data(UpdateHelperProtocol.managedMarker.utf8).write(to: paths.managedMarker, options: .atomic)
			try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: paths.installReceipt.path)
			try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: paths.managedMarker.path)
			installationSucceeded = true
			return receipt
		} catch {
			try? removeIfPresent(paths.helperExecutable)
			try? removeIfPresent(paths.installReceipt)
			if hadExisting, GlyphsUninstallScanner.itemExists(at: backup, fileManager: fileManager) {
				try? fileManager.moveItem(at: backup, to: paths.helperExecutable)
			}
			if hadReceipt, GlyphsUninstallScanner.itemExists(at: receiptBackup, fileManager: fileManager) {
				try? fileManager.moveItem(at: receiptBackup, to: paths.installReceipt)
			}
			throw error
		}
	}

	public func removeManagedUpdaterIfPresent() throws {
		guard GlyphsUninstallScanner.itemExists(at: paths.root, fileManager: fileManager) else { return }
		guard !isSymbolicLink(paths.root),
			  let marker = try? String(contentsOf: paths.managedMarker, encoding: .utf8),
			  marker == UpdateHelperProtocol.managedMarker else {
			throw UpdateStagingError("unsafe_path", "The updater directory is not marked as managed and was preserved.")
		}
		try fileManager.removeItem(at: paths.root)
	}

	private func removeAuthorizations(for version: GlyphsMajorVersion) throws {
		guard GlyphsUninstallScanner.itemExists(at: paths.authorizations, fileManager: fileManager) else {
			return
		}
		guard !isSymbolicLink(paths.authorizations) else {
			throw UpdateStagingError("unsafe_path", "The updater authorization directory is unsafe and was preserved.")
		}
		let versions = try fileManager.contentsOfDirectory(
			at: paths.authorizations,
			includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
			options: []
		)
		for releaseDirectory in versions {
			let values = try releaseDirectory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
			guard values.isDirectory == true, values.isSymbolicLink != true,
				  releaseDirectory.lastPathComponent.hasPrefix("v") else { continue }
			let receipt = releaseDirectory.appendingPathComponent("glyphs-\(version.rawValue).json")
			if GlyphsUninstallScanner.itemExists(at: receipt, fileManager: fileManager) {
				guard !isSymbolicLink(receipt) else {
					throw UpdateStagingError("unsafe_path", "An updater authorization receipt is unsafe and was preserved.")
				}
				try fileManager.removeItem(at: receipt)
			}
		}
	}

	private func ensureSafeRoot() throws {
		let applicationSupport = paths.root.deletingLastPathComponent().deletingLastPathComponent()
		let productRoot = paths.root.deletingLastPathComponent()
		let rootExisted = GlyphsUninstallScanner.itemExists(at: paths.root, fileManager: fileManager)
		if rootExisted {
			guard !isSymbolicLink(paths.root),
				  let marker = try? String(contentsOf: paths.managedMarker, encoding: .utf8),
				  marker == UpdateHelperProtocol.managedMarker,
				  !isSymbolicLink(paths.managedMarker) else {
				throw UpdateStagingError("unsafe_path", "The existing updater directory is not marked as managed and was preserved.")
			}
		}
		try fileManager.createDirectory(
			at: applicationSupport,
			withIntermediateDirectories: true,
			attributes: [.posixPermissions: 0o700]
		)
		for directory in [productRoot, paths.root] {
			if GlyphsUninstallScanner.itemExists(at: directory, fileManager: fileManager) {
				guard !isSymbolicLink(directory) else {
					throw UpdateStagingError("unsafe_path", "The updater destination contains a symbolic link.")
				}
			} else {
				try fileManager.createDirectory(
					at: directory,
					withIntermediateDirectories: false,
					attributes: [.posixPermissions: 0o700]
				)
			}
			try fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
		}
	}

	private func writeJSON<T: Encodable>(_ value: T, to destination: URL) throws {
		let encoder = JSONEncoder()
		encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
		encoder.dateEncodingStrategy = .iso8601
		var data = try encoder.encode(value)
		data.append(Data("\n".utf8))
		try data.write(to: destination, options: .atomic)
	}

	private func isSymbolicLink(_ url: URL) -> Bool {
		(try? url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true
	}

	private func removeIfPresent(_ url: URL) throws {
		if GlyphsUninstallScanner.itemExists(at: url, fileManager: fileManager) {
			try fileManager.removeItem(at: url)
		}
	}
}
