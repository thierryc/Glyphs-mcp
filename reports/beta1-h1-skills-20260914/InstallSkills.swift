import Foundation
import GlyphsMCPInstallerCore

// Qualification driver only: all mutations go through the existing installer.
@main struct H1InstallSkills {
    static func main() throws {
        let args = CommandLine.arguments
        let root = URL(fileURLWithPath: args[1], isDirectory: true)
        let evidence = URL(fileURLWithPath: args[2], isDirectory: true)
        let destination = InstallerPaths.codexSkillsDir
        let payload = InstallerPayload(payloadDir: root,
            pluginBundle: root.appendingPathComponent("Lean/Glyphs MCP Bridge.glyphsPlugin"),
            requirementsTxt: root.appendingPathComponent("requirements.txt"),
            skillsDir: root.appendingPathComponent("skills"))
        let reviewed = try JSONDecoder().decode([String:String].self,
            from: Data(contentsOf: evidence.appendingPathComponent("reviewed-retirements.json")))
        let expectedNames = Set(["icon-font", "litsquare-metadata", "color-font", "variable-font",
            "production-audit", "unicode-semantics", "export-validation"].map { "glyphs-mcp-" + $0 })
        func require(_ ok: Bool, _ message: String) throws {
            guard ok else { throw NSError(domain: "H1", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
        }
        try require(Set(reviewed.keys) == expectedNames, "Review must contain exactly the seven H1 retirements")
        for (name, hash) in reviewed {
            try require(try InstallerPayloadManifestResolver.treeIdentity(destination.appendingPathComponent(name)) == hash,
                "Reviewed skill changed; preserve and review again: " + name)
        }
        let ledgerURL = destination.appendingPathComponent(".glyphs-mcp-skills.json")
        let ownership = try JSONDecoder().decode([String:String].self, from: Data(contentsOf: ledgerURL))
        var currentPreflight: [[String:String]] = []
        for source in payload.managedSkillDirectories() {
            let name = source.lastPathComponent
            let actual = try InstallerPayloadManifestResolver.treeIdentity(destination.appendingPathComponent(name))
            let expected = try InstallerPayloadManifestResolver.treeIdentity(source)
            try require(actual == expected || ownership[name] == actual, "Unreviewed managed-skill edit: " + name)
            currentPreflight.append(["name":name,"before":actual,"candidate":expected])
        }
        try require(currentPreflight.count == 11, "Expected eleven current managed skills")
        for name in InstallerPayload.legacyManagedSkillNames {
            try require(!FileManager.default.fileExists(atPath: destination.appendingPathComponent(name).path),
                "Preserve unrelated legacy skill: " + name)
        }
        if args.contains("--preflight-only") {
            print("Preflight passed: seven exact reviewed retirements; eleven current/owned skills; no unrelated replacement.")
            return
        }
        // H1 authorizes removal of these reviewed obsolete routes using backups.
        let installer = AgentSkillBundleInstaller(log: { print($0) })
        let result = try installer.installCodexSkills(payload: payload, overwriteExisting: true)
        try require(result.conflicts.isEmpty, result.summary)
        let retired = result.entries.filter { $0.outcome == .retired }
        try require(Set(retired.map(\.name)) == expectedNames, "Incomplete retirement")
        for entry in retired {
            try require(!FileManager.default.fileExists(atPath: entry.path), "Retired folder remains selectable")
            let backup = URL(fileURLWithPath: entry.backupPath!)
            try require(try InstallerPayloadManifestResolver.treeIdentity(backup) == reviewed[entry.name], "Backup mismatch")
        }
        let installed = try payload.managedSkillDirectories().map { source -> [String:String] in
            let expected = try InstallerPayloadManifestResolver.treeIdentity(source)
            let actual = try InstallerPayloadManifestResolver.treeIdentity(destination.appendingPathComponent(source.lastPathComponent))
            try require(expected == actual, "Installed skill differs: " + source.lastPathComponent)
            return ["name":source.lastPathComponent,"expected":expected,"installed":actual]
        }
        let backupRoot = destination.deletingLastPathComponent().appendingPathComponent("glyphs-mcp-skill-backups")
        let beforeRepeat = try InstallerPayloadManifestResolver.treeIdentity(backupRoot)
        let repeated = try installer.installCodexSkills(payload: payload, overwriteExisting: false)
        try require(repeated.entries.count == 11 && repeated.entries.allSatisfy { $0.outcome == .current }, "Repeat is not current")
        try require(try InstallerPayloadManifestResolver.treeIdentity(backupRoot) == beforeRepeat, "Repeat added/changed backups")
        let record: [String:Any] = [
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "explicitReviewedReplacement":true, "preflight":currentPreflight,
            "reviewedRetirements":reviewed, "verified":installed,
            "entries":result.entries.map { ["name":$0.name,"path":$0.path,"outcome":$0.outcome.rawValue,"backup":$0.backupPath ?? ""] },
            "repeatOutcomes":repeated.entries.map { $0.outcome.rawValue }, "repeatBackupUnchanged":true]
        try JSONSerialization.data(withJSONObject: record, options:[.prettyPrinted,.sortedKeys])
            .write(to: evidence.appendingPathComponent("installation.json"))
    }
}
