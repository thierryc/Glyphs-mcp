"""File-bound comparison contracts, independent of native export manifests."""
import re
from pathlib import PurePosixPath
from .models import ProtocolError

CAPABILITY = "font.compare.diffenator.v1"
EXTENSIONS = {".html", ".css", ".js", ".json", ".png", ".gif", ".svg", ".ttf", ".woff", ".woff2"}
MAX_BYTES = 512 * 1024 * 1024


def options(value):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {"styles", "filterStyles", "userWordlist"}:
        raise ProtocolError("invalid_request", "comparison options are styles, filterStyles and userWordlist")
    styles = value.get("styles", "instances")
    if styles not in ("instances", "masters", "cross_product"):
        raise ProtocolError("invalid_request", "styles must be instances, masters or cross_product")
    result = {"styles": styles}
    for name in ("filterStyles", "userWordlist"):
        item = value.get(name)
        if item is not None:
            if not isinstance(item, str) or not item or len(item) > (256 if name == "filterStyles" else 4096) or "\0" in item:
                raise ProtocolError("invalid_request", name + " must be a bounded nonempty string")
            if name == "filterStyles":
                try:
                    re.compile(item)
                except re.error as exc:
                    raise ProtocolError("invalid_request", "invalid style filter") from exc
            result[name] = item
    return result


def validate_manifest(value):
    if not isinstance(value, dict) or set(value) != {"files", "totalBytes", "entryPoint"}:
        raise ProtocolError("invalid_request", "invalid comparison report manifest")
    files = value["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= 4096:
        raise ProtocolError("invalid_request", "comparison report must contain 1-4096 files")
    paths, total = set(), 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256", "mediaType"}:
            raise ProtocolError("invalid_request", "invalid comparison report file")
        path = item["path"]
        if not isinstance(path, str) or not path or len(path) > 512 or "\\" in path or "\0" in path:
            raise ProtocolError("invalid_request", "invalid report path")
        relative = PurePosixPath(path)
        if relative.is_absolute() or any(p in (".", "..") for p in path.split("/")) or str(relative) != path or path in paths or relative.suffix not in EXTENSIONS:
            raise ProtocolError("invalid_request", "unsafe or unsupported report path")
        if type(item["size"]) is not int or not 0 <= item["size"] <= MAX_BYTES:
            raise ProtocolError("invalid_request", "invalid report file size")
        if not isinstance(item["sha256"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", item["sha256"]):
            raise ProtocolError("invalid_request", "invalid report checksum")
        if not isinstance(item["mediaType"], str) or not 1 <= len(item["mediaType"]) <= 120:
            raise ProtocolError("invalid_request", "invalid report media type")
        paths.add(path)
        total += item["size"]
    if type(value["totalBytes"]) is not int or total != value["totalBytes"] or total > MAX_BYTES:
        raise ProtocolError("invalid_request", "comparison report exceeds 512 MiB or its byte count differs")
    if not isinstance(value["entryPoint"], str) or value["entryPoint"] not in paths or not value["entryPoint"].endswith(".html"):
        raise ProtocolError("invalid_request", "comparison report requires an HTML entry point")
    return value
