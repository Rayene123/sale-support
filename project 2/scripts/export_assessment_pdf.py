"""Export the Project 2 requirements assessment to PDF."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "requirements_assessment.pdf"


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def build_pdf(output: Path = OUTPUT) -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TitleCenter",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["BodyText"],
        fontSize=8.5,
        leading=11,
    ))
    styles.add(ParagraphStyle(
        name="Body",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=13,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="Section",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        spaceBefore=8,
        spaceAfter=5,
        textColor=colors.HexColor("#163a5f"),
    ))

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="Project 2 - The Librarian Requirements Assessment",
        author="Project team",
    )
    story = [
        paragraph("Project 2 - The Librarian", styles["TitleCenter"]),
        paragraph("Requirements assessment and completion report", styles["Heading2"]),
        paragraph(
            "Assessment of the Tunisian Commerce RAG implementation against the "
            "CS496 AI Engineering project brief. Generated 21 October 2026.",
            styles["Body"],
        ),
        paragraph(
            "<b>Executive verdict.</b> The project is a credible, tested RAG "
            "implementation with strong corpus, retrieval, citation, and evaluation "
            "work. It is not yet fully complete against the brief because public "
            "deployment, real-user feedback, and a qualifying 50% Week 8 optimization "
            "are still outstanding.",
            styles["Body"],
        ),
        paragraph("What is done well", styles["Section"]),
    ]

    good = [
        ["Requirement area", "Evidence and assessment"],
        ["Real corpus", "193-page 2024 IORT Tunisian Code de commerce; source provenance and SHA-256 verification are documented."],
        ["Corpus scale and QA set", "109 approved questions: 89 answerable, 20 unanswerable, including multi-article questions with source evidence."],
        ["Indexing", "Article-aware records preserve article numbers, legal hierarchy, page metadata, and stable IDs. BM25 and multilingual vector indexing are implemented."],
        ["Retrieval", "BM25, vector, hybrid reciprocal-rank fusion, and deterministic reranking are implemented and compared."],
        ["Citations", "Claims cite returned chunks; quotes are checked against supplied text; article, page, and source metadata are attached server-side."],
        ["Evaluation", "Recall@k, any-gold hits, strict multi-evidence success, latency, citation metrics, abstention metrics, token usage, and cost formulas are present."],
        ["Engineering quality", "The full suite passes: 204 tests passed, 26 skipped, 0 failures."],
        ["Documentation", "README, design, optimization report, postmortem, deployment files, and contribution roles are documented."],
    ]
    story.append(make_table(good, styles))

    story.append(paragraph("Measured retrieval results", styles["Section"]))
    results = [
        ["Method", "Recall@10", "p50 search", "p95 search"],
        ["BM25", "83.15%", "1.82 ms", "2.82 ms"],
        ["Vector", "68.54%", "20.56 ms", "27.48 ms"],
        ["Hybrid", "87.08%", "21.69 ms", "27.63 ms"],
        ["Hybrid + reranker", "87.08%", "24.17 ms", "32.55 ms"],
    ]
    story.append(make_table(results, styles))
    story.append(paragraph(
        "Hybrid improves recall over BM25 at k=10, but costs more latency. "
        "The reranker did not improve k=10 coverage in the fixed evaluation.",
        styles["Body"],
    ))

    story.append(paragraph("What remains incomplete or weak", styles["Section"]))
    gaps = [
        ["Gap", "Current status and impact"],
        ["Week 8 optimization target", "Not demonstrated. No before/after experiment proves a 50% cost or p95 reduction with no more than two percentage points of accuracy loss."],
        ["Public deployment", "The FastAPI service and Dockerfile exist, but there is no public URL. Docker image build was not completed because Docker Desktop's Linux engine was unavailable."],
        ["Real-user feedback", "No target-user sessions or anonymous task outcomes were collected."],
        ["Abstention quality", "Generation evaluation found 13/20 correct unanswerable abstentions, 7 unsupported answers, and 31/89 false abstentions."],
        ["Faithfulness measurement", "Quote occurrence and citation-ID matching are structural proxies, not semantic entailment or legal correctness."],
        ["Cost model", "Token-cost formulas exist, but local electricity, hardware amortization, and operating costs were not measured."],
  ]
    story.append(make_table(gaps, styles))

    story.append(paragraph("Recommended final actions", styles["Section"]))
    actions = [
        "Deploy the Dockerized service and record a public URL, model configuration, and health check.",
        "Collect anonymous feedback from real target users using the documented five-point task questionnaire.",
        "Choose one optimization, rerun the unchanged 109-question set before and after, and report latency, cost, answer quality, citations, and abstention.",
        "Calibrate MIN_RETRIEVAL_SCORE on a development split, not on the final test set, and rerun generation evaluation.",
        "Add structured human faithfulness labels or a documented judge protocol.",
    ]
    for index, action in enumerate(actions, 1):
        story.append(paragraph(f"{index}. {action}", styles["Body"]))

    story.append(Spacer(1, 6))
    story.append(paragraph(
        "Referenced repository files: README.md, design.md, optimisation.md, "
        "postmortem.md, docs/PERSON_4_EVALUATION.md, eval/retrieval.py, "
        "eval/generation.py, src/api/app.py, and src/generation/service.py.",
        styles["Small"],
    ))
    doc.build(story)


def make_table(rows: list[list[str]], styles) -> Table:
    formatted = [
        [paragraph(cell, styles["Small"]) for cell in row]
        for row in rows
    ]
    widths = [42 * mm, 124 * mm] if len(rows[0]) == 2 else [58 * mm, 31 * mm, 31 * mm, 31 * mm]
    table = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aab7c4")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f7")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


if __name__ == "__main__":
    build_pdf()
    print(OUTPUT)
