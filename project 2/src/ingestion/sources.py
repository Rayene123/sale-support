"""Registry of legal sources for the Project 2 corpus.

The README's scope rules require a recorded source URL, title, language, date
and permission/status for every source, and forbid unverified legal text in the
repository. This module is that record.

A source is only ingested when the SHA-256 of the downloaded file matches the
value stored here. A truncated, replaced or re-exported PDF therefore fails the
build loudly instead of silently changing the corpus. To accept a new revision,
download it, verify it by hand, and update the hash here in a reviewed commit.
"""
from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Sources that are ingested into v1 of the corpus.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """One downloadable file, with the provenance the scope rules demand."""

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

CODE_COMMERCE_FR = Source(
    source_id="code-commerce-fr-iort-2014",
    url=(
        "https://www.justice.gov.tn/fileadmin/medias/references_juridiques/"
        "codes_juridiques/CommerceFr.pdf"
    ),
    title="Code de commerce (République Tunisienne)",
    language="fr",
    publisher=f"{JUSTICE_MINISTRY} / Imprimerie Officielle de la République Tunisienne (IORT)",
    edition=(
        "Edition revue et corrigée le 15 février 2014 (IORT); conforme à la "
        "dernière révision prévue par la loi n° 2010-39"
    ),
    edition_date="2014-02-15",
    amendment_horizon="2010-07-26 (loi n° 2010-39 du 26 juillet 2010)",
    permission="published-official-text",
    permission_note=(
        "Official publication of the Tunisian Ministry of Justice. Reproduced "
        "verbatim for non-commercial educational research; the IORT notice "
        "reserves all rights. Redistribute only inside this course repository."
    ),
    sha256="fd205f84e7413e741f182c85dbff2fe4900e68658f92908a52c21245ab6f98a2",
    expected_bytes=700492,
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
            "Articles 1 à 746 as consolidated in the 2014 IORT edition. "
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
# Sources that were examined and rejected for v1. Recorded so the next person
# does not repeat the check.
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


# The ministry's French code index lives at
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
