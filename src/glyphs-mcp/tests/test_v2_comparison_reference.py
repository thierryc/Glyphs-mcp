"""Git-backed comparison reference domain and transaction contracts."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from dulwich import porcelain  # noqa: E402
from dulwich.client import LocalGitClient  # noqa: E402

from glyphs_mcp_v2.background_work import BackgroundWorkCoordinator  # noqa: E402
from glyphs_mcp_v2.comparison_reference import (  # noqa: E402
    ComparisonReferenceError,
    ComparisonReferencePreferences,
    ComparisonReferenceService,
    ComparisonReferenceSpec,
    DulwichGitReferenceResolver,
    GitReferenceCache,
    ReferenceSnapshot,
    ReferenceStatus,
    canonical_github_url,
)
from glyphs_mcp_v2.saved_source import SavedSourceService  # noqa: E402


FLAT_FIXTURE = REPO / "GlyphsSDK/GlyphsFileFormat/GlyphsFileFormatv3.glyphs"


def _repository(root: Path) -> tuple[Path, str]:
    source = root / "Family.glyphs"
    shutil.copy2(FLAT_FIXTURE, source)
    repo = porcelain.init(root)
    porcelain.add(repo, paths=["Family.glyphs"])
    commit = porcelain.commit(
        repo,
        message=b"baseline",
        author=b"Glyphs MCP Tests <tests@example.com>",
        committer=b"Glyphs MCP Tests <tests@example.com>",
    )
    repo.close()
    return source, commit.decode("ascii")


class ComparisonReferenceDomainTests(unittest.TestCase):
    def test_github_urls_are_canonical_and_credential_free(self) -> None:
        self.assertEqual(
            canonical_github_url("owner/repository"),
            "https://github.com/owner/repository.git",
        )
        self.assertEqual(
            canonical_github_url("https://github.com/owner/repository.git"),
            "https://github.com/owner/repository.git",
        )
        for value in (
            "ssh://git@github.com/owner/repository",
            "https://token@github.com/owner/repository",
            "https://gitlab.com/owner/repository",
            "file:///tmp/repository",
            "https://github.com/owner/repository#main",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ComparisonReferenceError):
                    canonical_github_url(value)

    def test_font_paths_are_repository_relative_supported_sources(self) -> None:
        for value in ("../Family.glyphs", "/Family.glyphs", "Family.ufo"):
            with self.subTest(value=value):
                with self.assertRaises(ComparisonReferenceError):
                    ComparisonReferenceSpec.from_mapping(
                        {
                            "kind": "local_git",
                            "revision": "main",
                            "fontPath": value,
                        }
                    )

    def test_local_revision_reads_committed_objects_and_ignores_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, commit = _repository(root)
            original_bytes = source.read_bytes()
            source.write_text("dirty working tree", encoding="utf-8")
            resolver = DulwichGitReferenceResolver()

            result = resolver.resolve(
                ComparisonReferenceSpec(
                    kind="local_git",
                    revision=commit[:12],
                    repository_path=str(root),
                ),
                live_source_path=str(source),
            )

            self.assertEqual(result.resolved.resolved_commit, commit)
            self.assertEqual(result.resolved.font_path, "Family.glyphs")
            self.assertEqual(result.resolved.cache_state, "local")
            self.assertIsNotNone(result.snapshot.model)
            self.assertEqual(source.read_text(encoding="utf-8"), "dirty working tree")
            self.assertNotEqual(source.read_bytes(), original_bytes)

    def test_local_full_sha_reuses_the_decoded_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, commit = _repository(root)
            resolver = DulwichGitReferenceResolver()
            spec = ComparisonReferenceSpec(
                kind="local_git",
                revision=commit,
                repository_path=str(root),
            )

            first = resolver.resolve(spec, live_source_path=str(source))
            second = resolver.resolve(spec, live_source_path=str(source))

            self.assertIs(first.snapshot, second.snapshot)
            self.assertLessEqual(len(resolver._decoded), 128)

    def test_public_github_transport_populates_and_reuses_bare_cache_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            source, commit = _repository(source_root)

            class LocalTransport:
                def __init__(self, *_args, **_kwargs) -> None:
                    self.client = LocalGitClient(include_tags=True, quiet=True)

                def get_refs(self, _path):
                    return self.client.get_refs(str(source_root))

                def fetch(self, _path, target, **kwargs):
                    return self.client.fetch(str(source_root), target, **kwargs)

                def close(self):
                    return None

            cache = GitReferenceCache(root=root / "cache")
            resolver = DulwichGitReferenceResolver(
                cache=cache,
                http_client_factory=LocalTransport,
            )
            spec = ComparisonReferenceSpec(
                kind="github",
                repository_url="https://github.com/example/family.git",
                revision="master",
            )
            cold = resolver.resolve(spec, live_source_path=str(source))

            def offline(*_args, **_kwargs):
                raise AssertionError("warm pinned resolution attempted network access")

            warm = DulwichGitReferenceResolver(
                cache=cache,
                http_client_factory=offline,
            ).resolve(
                spec,
                live_source_path=str(source),
                cached_only=True,
                resolved_hint=commit,
            )

            self.assertEqual(cold.resolved.resolved_commit, commit)
            self.assertEqual(cold.resolved.cache_state, "cold")
            self.assertEqual(warm.resolved.resolved_commit, commit)
            self.assertEqual(warm.resolved.cache_state, "warm")
            status = ReferenceStatus(
                state="ready",
                spec=spec,
                resolved=warm.resolved,
                source_fingerprint=warm.snapshot.source_fingerprint,
            )
            self.assertEqual(status.to_dict()["offlineStatus"], "cache_ready")
            self.assertEqual(
                cold.snapshot.source_fingerprint, warm.snapshot.source_fingerprint
            )

    def test_lfs_pointer_and_symlink_sources_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lfs_root = Path(temporary) / "lfs"
            lfs_root.mkdir()
            source, _commit = _repository(lfs_root)
            source.write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:" + b"0" * 64 + b"\nsize 123\n"
            )
            repo = porcelain.open_repo(lfs_root)
            porcelain.add(repo, paths=["Family.glyphs"])
            lfs_commit = porcelain.commit(
                repo,
                message=b"lfs pointer",
                author=b"Tests <tests@example.com>",
                committer=b"Tests <tests@example.com>",
            )
            repo.close()
            with self.assertRaisesRegex(ComparisonReferenceError, "Git LFS"):
                DulwichGitReferenceResolver().resolve(
                    ComparisonReferenceSpec(
                        kind="local_git",
                        revision=lfs_commit.decode("ascii"),
                        repository_path=str(lfs_root),
                    ),
                    live_source_path=str(source),
                )

            link_root = Path(temporary) / "link"
            link_root.mkdir()
            real_source = link_root / "Real.glyphs"
            shutil.copy2(FLAT_FIXTURE, real_source)
            link = link_root / "Family.glyphs"
            link.symlink_to(real_source.name)
            link_repo = porcelain.init(link_root)
            porcelain.add(link_repo, paths=["Family.glyphs"])
            link_commit = porcelain.commit(
                link_repo,
                message=b"symlink",
                author=b"Tests <tests@example.com>",
                committer=b"Tests <tests@example.com>",
            )
            link_repo.close()
            with self.assertRaisesRegex(
                ComparisonReferenceError, "Symlinks and submodules"
            ):
                DulwichGitReferenceResolver().resolve(
                    ComparisonReferenceSpec(
                        kind="local_git",
                        revision=link_commit.decode("ascii"),
                        repository_path=str(link_root),
                        font_path="Family.glyphs",
                    ),
                    live_source_path=str(real_source),
                )


class _ResolverStub:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    def resolve(self, *_args, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.result


class ComparisonReferenceServiceTests(unittest.TestCase):
    def _service(self, resolver) -> ComparisonReferenceService:
        return ComparisonReferenceService(
            saved_sources=SavedSourceService(
                coordinator=BackgroundWorkCoordinator(thread_name="saved-reference-test")
            ),
            resolver=resolver,
            preferences=ComparisonReferencePreferences({}),
            coordinator=BackgroundWorkCoordinator(thread_name="git-reference-test"),
        )

    def test_failed_new_reference_restores_the_previous_reference(self) -> None:
        service = self._service(
            _ResolverStub(error=ComparisonReferenceError("missing", "not found"))
        )
        try:
            service.bind_document("doc-1", source_path="/fonts/Family.glyphs")
            with self.assertRaises(ComparisonReferenceError):
                service.configure_wait(
                    "doc-1",
                    ComparisonReferenceSpec(
                        kind="local_git", revision="missing", repository_path="/repo"
                    ),
                    timeout_seconds=5,
                )
            status = service.status_for_document("doc-1")
            self.assertEqual(status.spec.kind, "last_saved")
            self.assertEqual(status.error_code, "missing")
        finally:
            service.saved_sources.coordinator.close(wait=True)
            service.close()

    def test_failed_refresh_retains_overlay_and_marks_it_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, commit = _repository(Path(temporary))
            real_resolver = DulwichGitReferenceResolver()
            resolved = real_resolver.resolve(
                ComparisonReferenceSpec(
                    kind="local_git",
                    revision=commit,
                    repository_path=temporary,
                ),
                live_source_path=str(source),
            )
            service = self._service(_ResolverStub(result=resolved))
            try:
                service.bind_document("doc-1", source_path=str(source))
                service.configure_wait(
                    "doc-1",
                    ComparisonReferenceSpec(
                        kind="local_git",
                        revision=commit,
                        repository_path=temporary,
                    ),
                    timeout_seconds=5,
                )
                before = service.snapshot_for_source(str(source))
                self.assertIsInstance(before, ReferenceSnapshot)
                service.resolver = _ResolverStub(
                    error=ComparisonReferenceError("offline", "network unavailable")
                )

                with self.assertRaises(ComparisonReferenceError):
                    service.refresh_wait("doc-1", timeout_seconds=5)

                after = service.snapshot_for_source(str(source))
                status = service.status_for_document("doc-1")
                self.assertIs(after, before)
                self.assertEqual(status.state, "stale_cached")
                self.assertTrue(status.stale)
                self.assertEqual(status.error_code, "offline")
            finally:
                service.saved_sources.coordinator.close(wait=True)
                service.close()


if __name__ == "__main__":
    unittest.main()
