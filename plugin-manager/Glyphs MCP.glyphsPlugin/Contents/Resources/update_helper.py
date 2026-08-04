# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json
import os
import plistlib
import re
import signal
import subprocess
import uuid
from collections import namedtuple


PROTOCOL_VERSION = 1
EXPECTED_TEAM_ID = "N9U29A4T8J"
EXPECTED_AUTHORITY = "Developer ID Application: Thierry Charbonnel (N9U29A4T8J)"
OPT_IN_DEFAULTS_KEY = "com.ap.cx.glyphs-mcp.inAppUpdatesEnabled"
HELPER_NAME = "GlyphsMCPUpdater"
MANAGED_MARKER = "cx.ap.glyphs-mcp-updater-v1"
STRICT_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

HelperProbe = namedtuple(
    "HelperProbe",
    "path protocol_version helper_version team_identifier cdhash authority build",
)


class UpdateHelperError(RuntimeError):
    pass


def updater_root(home=None):
    home = os.path.expanduser("~") if home is None else os.path.abspath(home)
    return os.path.join(home, "Library", "Application Support", "Glyphs MCP", "Updater")


def helper_path(home=None):
    return os.path.join(updater_root(home), HELPER_NAME)


def request_status_path(request_id, home=None):
    normalized = normalize_request_id(request_id)
    return os.path.join(updater_root(home), "Requests", normalized + ".json")


def authorization_path(version, glyphs_major, home=None):
    version = validate_version(version)
    glyphs_major = validate_glyphs_major(glyphs_major)
    return os.path.join(
        updater_root(home),
        "Authorizations",
        "v" + version,
        "glyphs-{}.json".format(glyphs_major),
    )


def stage_receipt_path(version, home=None):
    version = validate_version(version)
    return os.path.join(updater_root(home), "Staged", "v" + version, "receipt.json")


def staged_plugin_path(version, home=None):
    version = validate_version(version)
    return os.path.join(
        updater_root(home),
        "Staged",
        "v" + version,
        "Glyphs MCP.glyphsPlugin",
    )


def validate_version(value):
    text = str(value or "")
    if not STRICT_VERSION_RE.match(text):
        raise UpdateHelperError("Invalid update version.")
    return text


def validate_glyphs_major(value):
    try:
        major = int(value)
    except Exception:
        raise UpdateHelperError("Invalid Glyphs major version.")
    if major not in (3, 4):
        raise UpdateHelperError("Invalid Glyphs major version.")
    return major


def normalize_request_id(value):
    text = str(value or "").lower()
    if not UUID_RE.match(text):
        raise UpdateHelperError("Invalid update request ID.")
    try:
        parsed = uuid.UUID(text)
    except Exception:
        raise UpdateHelperError("Invalid update request ID.")
    if str(parsed) != text:
        raise UpdateHelperError("Invalid update request ID.")
    return text


def glyphs_major_from_version(value):
    try:
        major = int(float(value))
    except Exception:
        major = 4
    return validate_glyphs_major(major)


def _signature_field(details, name):
    prefix = name + "="
    for line in str(details or "").splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def _run_checked(arguments, timeout, run):
    try:
        completed = run(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            universal_newlines=True,
        )
    except Exception as error:
        raise UpdateHelperError("Could not verify the updater helper: {}".format(error))
    if int(getattr(completed, "returncode", 1)) != 0:
        output = str(getattr(completed, "stdout", "") or "").strip()[:2000]
        raise UpdateHelperError(output or "The updater helper failed verification.")
    return str(getattr(completed, "stdout", "") or "")


def verify_installed_helper(
    path=None,
    run=subprocess.run,
    allow_development_signature=False,
    home=None,
):
    path = helper_path(home) if path is None else os.path.abspath(path)
    if path != helper_path(home):
        raise UpdateHelperError("The updater helper is not at its managed path.")
    if os.path.islink(path) or not os.path.isfile(path):
        raise UpdateHelperError("The signed updater helper is not installed.")
    stat_result = os.stat(path)
    if stat_result.st_uid != os.getuid() or (stat_result.st_mode & 0o022):
        raise UpdateHelperError("The updater helper has unsafe ownership or permissions.")

    _run_checked(
        ["/usr/bin/codesign", "--verify", "--strict", "--verbose=2", path],
        timeout=5,
        run=run,
    )
    details = _run_checked(
        ["/usr/bin/codesign", "-d", "--verbose=4", path],
        timeout=5,
        run=run,
    )
    team = _signature_field(details, "TeamIdentifier")
    authority = _signature_field(details, "Authority")
    cdhash = _signature_field(details, "CDHash")
    if team != EXPECTED_TEAM_ID:
        raise UpdateHelperError("The updater helper has an unexpected developer team.")
    production = authority == EXPECTED_AUTHORITY
    development = bool(allow_development_signature) and str(authority or "").startswith(
        "Apple Development:"
    )
    if not (production or development):
        raise UpdateHelperError("The updater helper has an unexpected signing authority.")
    if "(runtime)" not in details:
        raise UpdateHelperError("The updater helper is missing the hardened runtime.")
    if not development and not _signature_field(details, "Timestamp"):
        raise UpdateHelperError("The updater helper is missing a secure timestamp.")
    if not cdhash:
        raise UpdateHelperError("The updater helper signature has no CDHash.")

    probe_text = _run_checked([path, "probe", "--json"], timeout=5, run=run)
    try:
        probe = json.loads(probe_text)
    except Exception:
        raise UpdateHelperError("The updater helper returned an invalid probe response.")
    if (
        not isinstance(probe, dict)
        or int(probe.get("protocolVersion", -1)) != PROTOCOL_VERSION
        or probe.get("teamIdentifier") != EXPECTED_TEAM_ID
        or "prepare" not in (probe.get("capabilities") or [])
        or not STRICT_VERSION_RE.match(str(probe.get("helperVersion") or ""))
    ):
        raise UpdateHelperError("The updater helper is incompatible with this plug-in.")

    return HelperProbe(
        path=path,
        protocol_version=PROTOCOL_VERSION,
        helper_version=str(probe["helperVersion"]),
        team_identifier=team,
        cdhash=cdhash,
        authority=authority,
        build=str(probe.get("build") or ""),
    )


def prepare_arguments(version, glyphs_major, request_id, path=None, home=None):
    version = validate_version(version)
    glyphs_major = validate_glyphs_major(glyphs_major)
    request_id = normalize_request_id(request_id)
    path = helper_path(home) if path is None else os.path.abspath(path)
    if path != helper_path(home):
        raise UpdateHelperError("The updater helper is not at its managed path.")
    return [
        path,
        "prepare",
        "--protocol",
        str(PROTOCOL_VERSION),
        "--version",
        version,
        "--glyphs-major",
        str(glyphs_major),
        "--request-id",
        request_id,
    ]


def start_prepare(
    version,
    glyphs_major,
    request_id,
    path=None,
    popen=subprocess.Popen,
    home=None,
):
    arguments = prepare_arguments(
        version,
        glyphs_major,
        request_id,
        path=path,
        home=home,
    )
    try:
        return popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=False,
            universal_newlines=True,
        )
    except Exception as error:
        raise UpdateHelperError("Could not start verified update preparation: {}".format(error))


def cancel_prepare(process):
    if process is None or process.poll() is not None:
        return False
    try:
        process.send_signal(signal.SIGTERM)
        return True
    except Exception as error:
        raise UpdateHelperError("Could not cancel update preparation: {}".format(error))


def _read_bounded_json(path, maximum_bytes=65536):
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    if os.path.getsize(path) > maximum_bytes:
        raise UpdateHelperError("The updater status file is too large.")
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except Exception as error:
        raise UpdateHelperError("Could not read updater status: {}".format(error))
    if not isinstance(value, dict):
        raise UpdateHelperError("The updater status is invalid.")
    return value


def read_request_status(request_id, version, glyphs_major, home=None):
    request_id = normalize_request_id(request_id)
    version = validate_version(version)
    glyphs_major = validate_glyphs_major(glyphs_major)
    value = _read_bounded_json(request_status_path(request_id, home=home))
    if value is None:
        return None
    if (
        int(value.get("protocolVersion", -1)) != PROTOCOL_VERSION
        or str(value.get("requestID") or "").lower() != request_id
        or value.get("version") != version
        or int(value.get("glyphsMajor", -1)) != glyphs_major
        or value.get("phase")
        not in (
            "resolving",
            "downloading",
            "verifying",
            "preparing",
            "ready",
            "failed",
            "cancelled",
        )
    ):
        raise UpdateHelperError("The updater status does not match this request.")
    return value


def verified_stage_is_ready(
    version,
    glyphs_major,
    home=None,
    run=subprocess.run,
    allow_development_signature=False,
):
    version = validate_version(version)
    glyphs_major = validate_glyphs_major(glyphs_major)
    authorization = _read_bounded_json(
        authorization_path(version, glyphs_major, home=home)
    )
    receipt = _read_bounded_json(stage_receipt_path(version, home=home))
    plugin = staged_plugin_path(version, home=home)
    if authorization is None or receipt is None or os.path.islink(plugin):
        return False
    request_id = str(authorization.get("requestID") or "").lower()
    asset_sha256 = str(receipt.get("assetSHA256") or "").lower()
    plugin_cdhash = str(receipt.get("pluginCDHash") or "")
    helper_version = str(receipt.get("helperVersion") or "")
    metadata_valid = bool(
        os.path.isdir(plugin)
        and int(authorization.get("protocolVersion", -1)) == PROTOCOL_VERSION
        and UUID_RE.match(request_id)
        and authorization.get("version") == version
        and int(authorization.get("glyphsMajor", -1)) == glyphs_major
        and int(receipt.get("protocolVersion", -1)) == PROTOCOL_VERSION
        and receipt.get("version") == version
        and receipt.get("tag") == "v" + version
        and receipt.get("assetName") == "GlyphsMCPInstaller.zip"
        and re.match(r"^[0-9a-f]{64}$", asset_sha256)
        and receipt.get("teamIdentifier") == EXPECTED_TEAM_ID
        and bool(plugin_cdhash)
        and STRICT_VERSION_RE.match(helper_version)
    )
    if not metadata_valid:
        return False

    executable = os.path.join(plugin, "Contents", "MacOS", "plugin")
    info_path = os.path.join(plugin, "Contents", "Info.plist")
    if (
        os.path.islink(executable)
        or not os.path.isfile(executable)
        or os.path.islink(info_path)
        or not os.path.isfile(info_path)
        or os.path.getsize(info_path) > 1024 * 1024
    ):
        return False
    try:
        with open(info_path, "rb") as stream:
            info = plistlib.load(stream)
    except Exception:
        return False
    if (
        not isinstance(info, dict)
        or info.get("CFBundleShortVersionString") != version
    ):
        return False

    try:
        _run_checked(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", plugin],
            timeout=10,
            run=run,
        )
        details = _run_checked(
            ["/usr/bin/codesign", "-d", "--verbose=4", executable],
            timeout=5,
            run=run,
        )
    except UpdateHelperError:
        return False
    team = _signature_field(details, "TeamIdentifier")
    authority = _signature_field(details, "Authority")
    cdhash = _signature_field(details, "CDHash")
    production = authority == EXPECTED_AUTHORITY
    development = bool(allow_development_signature) and str(authority or "").startswith(
        "Apple Development:"
    )
    return bool(
        team == EXPECTED_TEAM_ID
        and (production or development)
        and "(runtime)" in details
        and (development or bool(_signature_field(details, "Timestamp")))
        and cdhash == plugin_cdhash
    )
