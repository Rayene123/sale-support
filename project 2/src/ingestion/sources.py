"""Registry of legal sources for the Project 2 corpus.

The README's scope rules require a recorded source URL, title, language, date
and permission/status for every source, and forbid unverified legal text in the
repository. This module is that record.

A source is only ingested when the SHA-256 of the file matches the value stored
here. A truncated, replaced or re-exported PDF therefore fails the build loudly
instead of silently changing the corpus. To accept a new revision, obtain it,
verify it by hand, and update the hash here in a reviewed commit.

The v2 source of record (the 2024 edition) is a **supplied local file**: the
ministry's online ``CommerceFr.pdf`` still serves the 2014 edition, so the
pipeline cannot download these exact bytes. Such a source is marked
``downloadable=False`` and the build only verifies the file it finds on disk.
"""
from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Sources that are ingested into the corpus.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """One source file, with the provenance the scope rules demand."""

    source_id: str
    url: str
    title: str
    language: str
    publisher: str
    edition: str
    edition_date: str
    amendment_horizon: str
    permission: str
    permission_note: str
    sha256: str
    expected_bytes: int
    status: str = "active"  # "active" or "superseded"
    downloadable: bool = True  # False for a supplied file the pipeline cannot fetch
    provenance: str = ""


@dataclass(frozen=True)
class DocumentSpec:
    """A legal document carved out of a :class:`Source` file.

    One PDF can hold several documents: the Tunisian Code of Commerce PDF is
    prefixed by the promulgating law, whose articles 1-5 would otherwise
    collide with the code's articles 1-5.
    """

    document_id: str
    title: str
    language: str
    source_id: str
    region: str  # which region of the source file holds this document
    law_number: str | None
    law_date: str | None
    notes: str


JUSTICE_MINISTRY = "Ministère de la Justice, République Tunisienne"
IORT = "Imprimerie Officielle de la République Tunisienne (IORT)"

# Source of record for v2: the 2024 consolidated edition.
CODE_COMMERCE_FR = Source(
    source_id="code-commerce-fr-iort-2024",
    url="https://www.justice.gov.tn/index.php?id=289",
    title="Code de commerce (République Tunisienne), édition 2024",
    language="fr",
    publisher=f"{JUSTICE_MINISTRY} / {IORT}",
    edition=(
        "Edition revue et corrigée le 15 février 2024 (IORT); texte consolidé "
        "incluant les modifications jusqu'à la loi n° 2019-47 du 29 mai 2019"
    ),
    edition_date="2024-02-15",
    amendment_horizon="2019-05-29 (loi n° 2019-47 du 29 mai 2019)",
    permission="published-official-text",
    permission_note=(
        "Official publication of the IORT, reproduced verbatim for "
        "non-commercial educational research; the IORT notice reserves all "
        "rights. Redistribute only inside this course repository."
    ),
    sha256="353bca554ab5deaf229648485a271bc6fb65fa514b9785511d38f4e47393e7aa",
    expected_bytes=1527869,
    status="active",
    downloadable=False,
    provenance=(
        "Supplied as a local file (originally named "
        "4fbd3a90-401e-4bee-a872-82dc999a5af1.pdf), verified by SHA-256. The "
        "ministry's online CommerceFr.pdf still serves the 2014 edition "
        "(sha256 fd205f84…), so these 2024 bytes are not fetchable by the "
        "pipeline; the raw/ directory must contain them to rebuild."
    ),
)

SOURCES: tuple[Source, ...] = (CODE_COMMERCE_FR,)

DOCUMENTS: tuple[DocumentSpec, ...] = (
    DocumentSpec(
        document_id="code-commerce-tn",
        title="Code de commerce tunisien",
        language="fr",
        source_id=CODE_COMMERCE_FR.source_id,
        region="code",
        law_number="59-129",
        law_date="1959-10-05",
        notes=(
            "Articles 1 à 746 as consolidated in the 2024 IORT edition. "
            "Repealed articles are absent from the source text, not from this "
            "pipeline; the table of contents marks them '(abrogés)'."
        ),
    ),
    DocumentSpec(
        document_id="loi-59-129-1959",
        title="Loi n° 59-129 du 5 octobre 1959 portant promulgation du Code de commerce",
        language="fr",
        source_id=CODE_COMMERCE_FR.source_id,
        region="law",
        law_number="59-129",
        law_date="1959-10-05",
        notes=(
            "Promulgating law, articles 1 à 5, printed ahead of the code in the "
            "same file. Kept as its own document so its articles are not "
            "confused with the code's identically numbered articles."
        ),
    ),
)


# --------------------------------------------------------------------------
# Sources that were used before and are now retired. Recorded so the next
# person does not re-ingest them or wonder where they went.
# --------------------------------------------------------------------------


SUPERSEDED_SOURCES: tuple[Source, ...] = (
    Source(
        source_id="code-commerce-fr-iort-2014",
        url=(
            "https://www.justice.gov.tn/fileadmin/medias/references_juridiques/"
            "codes_juridiques/CommerceFr.pdf"
        ),
        title="Code de commerce (République Tunisienne), édition 2014",
        language="fr",
        publisher=f"{JUSTICE_MINISTRY} / {IORT}",
        edition=(
            "Edition revue et corrigée le 15 février 2014 (IORT); conforme à la "
            "dernière révision prévue par la loi n° 2010-39"
        ),
        edition_date="2014-02-15",
        amendment_horizon="2010-07-26 (loi n° 2010-39 du 26 juillet 2010)",
        permission="published-official-text",
        permission_note=(
            "Superseded. Still served online, but the 2024 edition is now the "
            "source of record; the two would duplicate article numbers."
        ),
        sha256="fd205f84e7413e741f182c85dbff2fe4900e68658f92908a52c21245ab6f98a2",
        expected_bytes=700492,
        status="superseded",
        downloadable=True,
        provenance="Downloaded from the ministry URL until the 2024 edition replaced it.",
    ),
)


# --------------------------------------------------------------------------
# Sources that were examined and rejected. Recorded so the next person does not
# repeat the check.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RejectedSource:
    source_id: str
    url: str
    title: str
    language: str
    reason: str
    evidence: str


REJECTED_SOURCES: tuple[RejectedSource, ...] = (
    RejectedSource(
        source_id="code-commerce-ar-iort-2014",
        url=(
            "https://www.justice.gov.tn/fileadmin/medias/references_juridiques/"
            "codes_juridiques/CommerceArabe.pdf"
        ),
        title="مجلة التجارة (Code de commerce, version arabe)",
        language="ar",
        reason="no-extractable-text-layer",
        evidence=(
            "179 pages, but the PDF's ToUnicode CMap is broken: pypdf returns "
            "glyph names such as '/tehmarbutafinal/yehmedial/...' instead of "
            "Arabic characters. No Arabic article text can be extracted without "
            "OCR. SHA-256 "
            "30008bd2e709fc7b925916576322e34da7df01f63c518ac7d8c8aa741fa69d63."
        ),
    ),
)


@dataclass(frozen=True)
class PendingText:
    """Related legal texts seen on the ministry index but not instructor-approved."""

    title: str
    url: str
    language: str
    status: str = "pending-instructor-approval"


# The ministry's code index lives at
# https://www.justice.gov.tn/index.php?id=223 (page id 223, "Codes juridiques").
# The PDFs below were observed while confirming the Code de commerce source.
PENDING_TEXTS: tuple[PendingText, ...] = (
    PendingText(
        title="Code des droits réels",
        url=(
            "https://www.justice.gov.tn/fileadmin/medias/references_juridiques/"
            "codes_juridiques/dtreelArabe.pdf"
        ),
        language="ar",
    ),
    PendingText(
        title="Code des sociétés commerciales / texte relatif aux sociétés",
        url=(
            "https://www.justice.gov.tn/fileadmin/medias/references_juridiques/"
            "codes_juridiques/societeArabe.pdf"
        ),
        language="ar",
    ),
)


def source_by_id(source_id: str) -> Source:
    for source in SOURCES:
        if source.source_id == source_id:
            return source
    raise KeyError(f"unknown source_id: {source_id}")


def documents_for(source_id: str) -> tuple[DocumentSpec, ...]:
    return tuple(doc for doc in DOCUMENTS if doc.source_id == source_id)
