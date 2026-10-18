"""Download source files and verify them against the registry.

Raw PDFs are not committed (see the repository ``.gitignore``). They are
downloaded into ``data/raw/`` and checked against the SHA-256 in
:mod:`.sources` before use, so a build either runs on exactly the bytes that
were reviewed or fails.

The downloader never overwrites an existing file unless ``force=True``, and
never trusts a partial download: the hash is verified after the write.
"""
from __future__ import annotations

import hashlib
import socket
import urllib.error
import urllib.request
from pathlib import Path

from .sources import Source

USER_AGENT = "sale-support-corpus/1.0 (educational research; contact: repository owner)"


class SourceError(RuntimeError):
    """Raised when a source cannot be downloaded or does not match its registry entry."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(source: Source, path: Path) -> None:
    """Check size and digest of a local copy against the registry."""
    if not path.is_file():
        raise SourceError(f"missing source file: {path}")
    actual_bytes = path.stat().st_size
    if actual_bytes != source.expected_bytes:
        raise SourceError(
            f"{path.name}: expected {source.expected_bytes} bytes, found {actual_bytes}. "
            "Delete the file and rebuild, or review the new revision before updating sources.py."
        )
    actual_sha = sha256_of(path)
    if actual_sha != source.sha256:
        raise SourceError(
            f"{path.name}: SHA-256 mismatch.\n"
            f"  registry: {source.sha256}\n"
            f"  on disk : {actual_sha}\n"
            "The upstream file changed or the download was corrupted. For a new upstream "
            "revision, verify it by hand and update sources.py in a reviewed commit."
        )


def resolve_source(
    source: Source,
    raw_dir: Path,
    *,
    allow_download: bool = True,
    force: bool = False,
    timeout: int = 60,
) -> Path:
    """Return a verified local path for ``source``.

    A ``downloadable=False`` source (a supplied file the pipeline cannot fetch)
    is only ever verified on disk; the network is never touched for it.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{source.source_id}.pdf"

    if not source.downloadable:
        if force:
            raise SourceError(
                f"{source.source_id} is a supplied file and cannot be re-downloaded; "
                "remove --force."
            )
        if not target.is_file():
            raise SourceError(
                f"{source.source_id} is a supplied file and is not downloadable.\n"
                f"  expected at : {target}\n"
                f"  bytes       : {source.expected_bytes}\n"
                f"  sha256      : {source.sha256}\n"
                "The 2024 edition is not served by the publisher's public URL, so it must "
                "be placed in data/raw/ by hand before the build can run."
            )
        verify_source(source, target)
        return target

    if not allow_download:
        verify_source(source, target)
        return target
    return download_source(source, raw_dir, force=force, timeout=timeout)


def download_source(
    source: Source,
    raw_dir: Path,
    *,
    force: bool = False,
    timeout: int = 60,
) -> Path:
    """Return a verified local path for ``source``, downloading it if needed."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{source.source_id}.pdf"

    if target.exists() and not force:
        verify_source(source, target)
        return target

    request = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})
    socket.setdefaulttimeout(timeout)
    try:
        with urllib.request.urlopen(request) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise SourceError(f"{source.url} returned HTTP {status}")
            payload = response.read()
    except urllib.error.URLError as exc:
        raise SourceError(
            f"could not download {source.url}: {exc}. "
            f"If the file is already in {raw_dir}, verify it and re-run with --no-download."
        ) from exc

    if not payload.startswith(b"%PDF"):
        raise SourceError(
            f"{source.url} did not return a PDF (first bytes: {payload[:16]!r}). "
            "An error page or a login wall was served."
        )

    target.write_bytes(payload)
    try:
        verify_source(source, target)
    except SourceError:
        target.unlink(missing_ok=True)
        raise
    return target


def ensure_sources(
    sources: tuple[Source, ...],
    raw_dir: Path,
    *,
    allow_download: bool = True,
    force: bool = False,
    timeout: int = 60,
) -> dict[str, Path]:
    """Resolve every source to a verified local file."""
    resolved: dict[str, Path] = {}
    for source in sources:
        resolved[source.source_id] = resolve_source(
            source,
            raw_dir,
            allow_download=allow_download,
            force=force,
            timeout=timeout,
        )
    return resolved
