import Foundation
import GlyphsMCPInstallerCore

@main struct H2InstallSkills {
 static func main() throws {
  let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
  let destination = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
  let replace = false
  let payload = InstallerPayload(payloadDir: root, pluginBundle: root.appendingPathComponent("Lean/Glyphs MCP Bridge.glyphsPlugin"), requirementsTxt: root.appendingPathComponent("requirements.txt"), skillsDir: root.appendingPathComponent("skills"))
  // H2 updates only unchanged installer-owned skills. Any conflict stops
  // this qualification driver; it does not authorize explicit replacement.
  let ownershipURL = destination.appendingPathComponent(".glyphs-mcp-skills.json")
  let previous = (try? Data(contentsOf: ownershipURL)).flatMap { try? JSONDecoder().decode([String:String].self, from: $0) } ?? [:]
  var conflicts: [String] = []
  for source in payload.managedSkillDirectories() {
   let name=source.lastPathComponent, target=destination.appendingPathComponent(name)
   if FileManager.default.fileExists(atPath: target.path) {
    let actual=try InstallerPayloadManifestResolver.treeIdentity(target)
    let expected=try InstallerPayloadManifestResolver.treeIdentity(source)
    if actual != expected && previous[name] != actual { conflicts.append(name) }
   }
  }
  guard conflicts.isEmpty else {
   throw NSError(domain:"H2",code:1,userInfo:[NSLocalizedDescriptionKey:"Unreviewed skill conflicts: \(conflicts)"])
  }
  for legacy in InstallerPayload.legacyManagedSkillNames {
   guard !FileManager.default.fileExists(atPath: destination.appendingPathComponent(legacy).path) else {
    throw NSError(domain:"H2",code:5,userInfo:[NSLocalizedDescriptionKey:"Unrelated legacy skill must be preserved: \(legacy)"])
   }
  }
  // Public installer entry point, existing transaction/backup behavior only.
  guard destination.path == FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".codex/skills").path else {
   throw NSError(domain:"H2",code:2,userInfo:[NSLocalizedDescriptionKey:"Use the existing installer tests for temporary destinations"])
  }
  let result=try AgentSkillBundleInstaller(log: { print($0) }).installCodexSkills(payload:payload,overwriteExisting:replace)
  guard result.conflicts.isEmpty else { throw NSError(domain:"H2",code:3,userInfo:[NSLocalizedDescriptionKey:result.summary]) }
  let rows = try payload.managedSkillDirectories().map { source -> [String:String] in
   let target=destination.appendingPathComponent(source.lastPathComponent)
   let expected=try InstallerPayloadManifestResolver.treeIdentity(source), actual=try InstallerPayloadManifestResolver.treeIdentity(target)
   guard expected == actual else { throw NSError(domain:"H2",code:4) }
   return ["name":source.lastPathComponent,"expected":expected,"installed":actual]
  }
  let data: [String:Any] = ["entries":result.entries.map{["name":$0.name,"path":$0.path,"outcome":$0.outcome.rawValue]},"verified":rows,"preflightConflicts":conflicts,"explicitReplacement":replace]
  try JSONSerialization.data(withJSONObject:data,options:[.prettyPrinted,.sortedKeys]).write(to: URL(fileURLWithPath:CommandLine.arguments[3]))
 }
}
