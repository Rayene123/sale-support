"""A synthetic, article-shaped document used by the parser tests.

It is deliberately small and hand-written: it contains no published legal text,
only the *shapes* the parser must handle, copied from the layout of the real
source (running header removed, hard wrapping, footnote markers, sentence-case
chapter titles, wrapped amendment notes, a repealed article, a ``bis`` article,
a parenthetical repeal notice between articles, and a table of contents).
"""
from __future__ import annotations

import _paths  # noqa: F401  (adds project 2/src to sys.path)

from ingestion.structure import Line

# Layout facts copied from the real publication, for the tests to assert on.
CODE_START = 5       # index of the "CODE DE COMMERCE(1)" title line
LAW_START = 0        # index of the promulgating law headline
FIRST_LIVRE = 6      # index of "LIVRE PREMIER"
TOC_START = 38       # index of "TABLE DES MATIERES"


def sample_stream() -> list[Line]:
    """Return the fixture as the parser sees it: (page, text) lines."""
    return [
        # --- promulgating law -------------------------------------------------
        Line(3, "Loi n° 59-129 du 5 octobre 1959, portant promulgation"),
        Line(3, "du Code de Commerce (1)."),
        Line(3, "Au nom du Peuple,"),
        Line(4, "Article premier"),
        Line(
            4,
            "Les textes publiés ci-après et relatifs au droit commercial sont "
            "réunis en un seul corps sous le titre de Code de Commerce.",
        ),
        # --- code -------------------------------------------------------------
        Line(7, "CODE DE COMMERCE(1)"),
        Line(7, "LIVRE PREMIER"),
        Line(7, "DU COMMERCE EN GENERAL"),
        Line(7, "TITRE PREMIER"),
        Line(7, "DES COMMERÇANTS"),
        Line(7, "Article premier"),
        Line(7, "Le présent code s'applique aux commerçants et aux"),
        Line(7, "actes de commerce."),
        Line(7, "Article 2"),
        Line(7, "Est commerçant, quiconque, à titre professionnel, procède :"),
        Line(7, "- à l'achat et à la vente des biens;"),
        Line(7, "Article 6 (Abrogé par la loi n° 95-35 du 17 avril 1995)."),
        Line(9, "TITRE II"),
        Line(9, "DES LIVRES DE COMMERCE"),
        Line(9, "Article 7"),
        Line(9, "Toute personne physique ou morale ayant la qualité de"),
        Line(9, "commerçant est assujettie à la tenue d'une comptabilité."),
        Line(9, "Article 231 (Le deuxième paragraphe a été modifié par la"),
        Line(9, "loi n° 2000 - 61 du 20 juin 2000)."),
        Line(9, "Le premier paragraphe reste inchangé."),
        Line(11, "TITRE III"),
        Line(11, "DES SOCIETES"),
        Line(11, "(Les Articles 14 à 188 sont abrogés par la loi n° 95-35 du"),
        Line(11, "17 avril 1995)."),
        Line(11, "LIVRE II"),
        Line(11, "DU FONDS DE COMMERCE"),
        Line(11, "CHAPITRE II"),
        Line(11, "Des contrats relatifs au fonds de commerce"),
        Line(11, "Section I. - De la vente et de la promesse de vente"),
        Line(11, "Sous-section I.- De la publicité de la vente du fonds de"),
        Line(11, "commerce"),
        Line(11, "Article 189 bis (Ajouté par la loi n° 2003-31 du 28 avril 2003)"),
        Line(11, "La vente du fonds de commerce est soumise aux formalités suivantes."),
        # --- table of contents ------------------------------------------------
        Line(215, "TABLE DES MATIERES"),
        Line(215, "Sujet Articles Page"),
        Line(215, "CODE DE COMMERCE 1 à 746 7"),
        Line(215, "Titre III : Des sociétés 14 à 188 (abrogés) 11"),
        Line(215, "LIVRE IV : DU CONCORDAT 413 à 444 (abrogés) 119"),
    ]


def page_sample() -> str:
    """One raw page of extracted text, header, page number and footnote included."""
    return "\n".join(
        [
            "Imprimerie Officielle de la République Tuinsienne",
            "51",
            "L'endossement doit être pur et simple.",
            "Toute condition à laquelle il est subordonné est réputée non",
            "écrite.",
            "__________",
            "(1) Rectificatif paru au JORT n° 3 du 15 janvier 1960.",
        ]
    )
