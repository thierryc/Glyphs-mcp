import Foundation

/// Validate both ZIP directory and local records before native extraction.
public enum TemplateArchive {
    public static func validate(_ data: Data) throws -> String {
        let bytes = [UInt8](data)
        func u16(_ i: Int) -> Int { i >= 0 && i + 2 <= bytes.count ? Int(bytes[i]) | Int(bytes[i+1]) << 8 : -1 }
        func u32(_ i: Int) -> Int { i >= 0 && i + 4 <= bytes.count ? u16(i) | u16(i+2) << 16 : -1 }
        func fail() -> ProjectError { ProjectError("The template ZIP is unsafe, unsupported or incomplete.") }
        func extraFields(_ start: Int, _ length: Int) throws {
            var offset = start
            guard start >= 0, start + length <= bytes.count else { throw fail() }
            while offset < start + length {
                guard offset + 4 <= start + length else { throw fail() }
                let tag = u16(offset), size = u16(offset + 2)
                // Timestamp and Unix identity metadata cannot substitute paths
                // or sizes. Reject ZIP64 and alternate Unicode path records.
                guard [0x5455, 0x7875, 0x5855, 0x000a].contains(tag), offset + 4 + size <= start + length else { throw fail() }
                offset += 4 + size
            }
        }
        guard bytes.count >= 22, bytes.count <= 20 * 1024 * 1024 else { throw fail() }
        guard let end = stride(from: bytes.count - 22, through: max(0, bytes.count - 65_557), by: -1).first(where: { u32($0) == 0x06054b50 }) else { throw fail() }
        let count = u16(end + 10), central = u32(end + 16)
        guard u16(end + 4) == 0, u16(end + 6) == 0, count > 0, count <= 10_000,
              u16(end + 8) == count, central >= 0, central + u32(end + 12) == end,
              end + 22 + u16(end + 20) == bytes.count else { throw fail() }
        var cursor = central, expanded = 0
        var names = Set<String>(), roots = Set<String>()
        var localRanges: [Range<Int>] = []
        for _ in 0..<count {
            guard cursor + 46 <= end, u32(cursor) == 0x02014b50 else { throw fail() }
            let flags = u16(cursor + 8), method = u16(cursor + 10)
            let compressed = u32(cursor + 20), size = u32(cursor + 24)
            let length = u16(cursor + 28), extra = u16(cursor + 30), comment = u16(cursor + 32)
            let local = u32(cursor + 42), next = cursor + 46 + length + extra + comment
            guard flags & 1 == 0, [0, 8].contains(method), length > 0, next <= end,
                  local >= 0, local + 30 <= central, u32(local) == 0x04034b50,
                  u16(local + 6) == flags, u16(local + 8) == method,
                  u16(local + 26) == length else { throw fail() }
            let localNameStart = local + 30, payload = localNameStart + length + u16(local + 28)
            guard payload >= localNameStart + length, payload + compressed <= central,
                  Array(bytes[localNameStart..<(localNameStart + length)]) == Array(bytes[(cursor+46)..<(cursor+46+length)]) else { throw fail() }
            try extraFields(cursor + 46 + length, extra)
            try extraFields(localNameStart + length, u16(local + 28))
            guard let raw = String(bytes: bytes[(cursor+46)..<(cursor+46+length)], encoding: .utf8) else { throw fail() }
            let name = raw.hasSuffix("/") ? String(raw.dropLast()) : raw
            try ProjectFiles.validateRelativePath(name)
            guard names.insert(name.precomposedStringWithCanonicalMapping.lowercased()).inserted else { throw fail() }
            roots.insert(String(name.split(separator: "/")[0]))
            let mode = (u32(cursor + 38) >> 16) & 0xf000
            guard [0, 0x4000, 0x8000].contains(mode), !raw.hasSuffix("/") || size == 0 else { throw fail() }
            expanded += size
            guard expanded <= 64 * 1024 * 1024 else { throw fail() }
            let range = local..<(payload + compressed)
            guard !localRanges.contains(where: { $0.overlaps(range) }) else { throw fail() }
            localRanges.append(range); cursor = next
        }
        guard cursor == end, roots.count == 1, let root = roots.first else { throw fail() }
        return root
    }
}
