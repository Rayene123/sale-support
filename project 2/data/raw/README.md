# Raw source files

This directory holds the downloaded source PDFs. **They are not committed**
(`project 2/data/raw/*.pdf` is git-ignored): the files are large, and the
scope rules require that the repository stay free of restricted third-party
reproductions.

The build downloads each file here and verifies its SHA-256 against the source
registry (`project 2/src/ingestion/sources.py`) before reading it. A file whose
hash does not match is rejected, so a stale or tampered copy can never silently
change the corpus.

## Reproduce the raw files

```sh
python "project 2/scripts/build_corpus.py" build
```

This downloads any missing source into this directory, verifies it, and writes
the processed corpus to `project 2/data/processed/`. If the raw PDF is already
present and valid, the download is skipped:

```sh
python "project 2/scripts/build_corpus.py" build --no-download
```

## Files

| File | Source | SHA-256 | Bytes |
|---|---|---|---|
| `code-commerce-fr-iort-2014.pdf` | `https://www.justice.gov.tn/fileadmin/medias/references_juridiques/codes_juridiques/CommerceFr.pdf` | `fd205f84e7413e741f182c85dbff2fe4900e68658f92908a52c21245ab6f98a2` | 700492 |

The Arabic twin (`CommerceArabe.pdf`) is deliberately **not** downloaded: its
PDF has a broken `ToUnicode` map and yields glyph names instead of Arabic text.
See `REJECTED_SOURCES` in `sources.py` and `excluded_sources` in
`project 2/data/processed/manifest.json`.

The `.gitkeep` file keeps this empty directory in git.
