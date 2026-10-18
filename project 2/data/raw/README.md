# Raw source files

This directory holds the downloaded source PDFs. **They are not committed**
(`project 2/data/raw/*.pdf` is git-ignored): the files are large, and the
scope rules require that the repository stay free of restricted third-party
reproductions.

The build verifies each file's SHA-256 against the source registry
(`project 2/src/ingestion/sources.py`) before reading it. A file whose hash does
not match is rejected, so a stale or tampered copy can never silently change the
corpus.

## Provide the raw source

The current source of record is **not downloadable**: the publisher's public URL
still serves the 2014 edition, so no URL returns these 2024 bytes. Supply the
file by hand, named exactly as below, then build:

```sh
python "project 2/scripts/build_corpus.py" build --no-download
```

The build verifies the file against the recorded SHA-256 and writes the
processed corpus to `project 2/data/processed/`. Plain `build` (without
`--no-download`) refuses a non-downloadable source with a clear message rather
than guessing a URL.

## Files

| File | Provenance | SHA-256 | Bytes |
|---|---|---|---|
| `code-commerce-fr-iort-2024.pdf` | 2024 IORT edition, supplied by hand (see `manifest.json → sources[0].provenance`) | `353bca554ab5deaf229648485a271bc6fb65fa514b9785511d38f4e47393e7aa` | 1527869 |

The earlier **2014** edition (`code-commerce-fr-iort-2014`, sha256
`fd205f84…b6f98a2`) is the same legal text with an older horizon and is retired
as `superseded`; it is recorded in `manifest.json → superseded_sources` and is
not built.

The Arabic twin (`CommerceArabe.pdf`) is deliberately **not** downloaded: its
PDF has a broken `ToUnicode` map and yields glyph names instead of Arabic text.
See `REJECTED_SOURCES` in `sources.py` and `excluded_sources` in
`project 2/data/processed/manifest.json`.

The `.gitkeep` file keeps this otherwise-empty directory in git.
