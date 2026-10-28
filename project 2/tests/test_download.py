"""Source replacement must preserve the reviewed PDF on failed downloads."""
from dataclasses import replace
from hashlib import sha256
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

import _paths
from ingestion.download import SourceError, download_source
from ingestion.sources import CODE_COMMERCE_FR


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.original = b"%PDF-existing-reviewed-copy"
        self.replacement = b"%PDF-new-reviewed-replacement"
        self.source = replace(CODE_COMMERCE_FR, source_id="fixture", url="https://example.invalid/source.pdf",
                              expected_bytes=len(self.replacement), sha256=sha256(self.replacement).hexdigest())
        self.target = self.folder / "fixture.pdf"
        self.target.write_bytes(self.original)

    def test_failed_verification_preserves_previous_file_and_removes_temporary_copy(self):
        bad_digest = b"%PDF-" + b"x" * (len(self.replacement) - 5)
        for body in (b"%PDF-short", bad_digest, b"not a PDF"):
            with self.subTest(body=body), patch("ingestion.download.urllib.request.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(SourceError):
                    download_source(self.source, self.folder, force=True)
            self.assertEqual(self.target.read_bytes(), self.original)
            self.assertEqual(list(self.folder.iterdir()), [self.target])

    def test_network_failure_preserves_previous_file(self):
        with patch("ingestion.download.urllib.request.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(SourceError):
                download_source(self.source, self.folder, force=True)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_successful_download_replaces_file_only_after_verification(self):
        with patch("ingestion.download.urllib.request.urlopen", return_value=io.BytesIO(self.replacement)) as request:
            self.assertEqual(download_source(self.source, self.folder, force=True, timeout=3), self.target)
        self.assertEqual(self.target.read_bytes(), self.replacement)
        self.assertEqual(list(self.folder.iterdir()), [self.target])
        self.assertEqual(request.call_args.kwargs, {"timeout": 3})

    def test_failed_first_download_leaves_no_partial_source(self):
        self.target.unlink()
        with patch("ingestion.download.urllib.request.urlopen", return_value=io.BytesIO(b"%PDF-invalid")):
            with self.assertRaises(SourceError):
                download_source(self.source, self.folder)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_failed_atomic_replacement_preserves_original_and_cleans_temporary_copy(self):
        with patch("ingestion.download.urllib.request.urlopen", return_value=io.BytesIO(self.replacement)), patch(
                "ingestion.download.Path.replace", side_effect=PermissionError("file is open")):
            with self.assertRaises(PermissionError):
                download_source(self.source, self.folder, force=True)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(list(self.folder.iterdir()), [self.target])
