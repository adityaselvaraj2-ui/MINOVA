from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.config import settings
from app.db.session import get_session_factory
from app.services.export import export_report
from app.services.ingestion import _read_spreadsheet_rows
from app.services.topics import compute_topics


@pytest.fixture()
def session():
    settings.ensure_dirs()
    import app.db.models  # noqa: F401
    from app.db.session import Base, get_engine, init_db

    init_db()  # honour current MINETRACE_DATA_DIR (other modules may rebind)
    Base.metadata.create_all(get_engine())
    session = get_session_factory()()
    yield session
    session.close()


def _make_doc_with_chunks(session, filename: str, texts: list[str]):
    from app.db.models import Document, DocumentChunk, Role, User
    from app.security import hash_password

    if not session.query(Role).filter(Role.code == "FOREMAN").first():
        session.add(Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True))
        session.flush()
    user = session.query(User).filter(User.username == "doc_user").first()
    if not user:
        session.add(User(
            username="doc_user", full_name="Doc User",
            password_hash=hash_password("pass"), role_code="FOREMAN",
        ))
        session.flush()
        user = session.query(User).filter(User.username == "doc_user").first()

    doc = Document(
        filename=filename,
        file_path=str(Path(tempfile.gettempdir()) / filename),
        file_type="PDF", file_size=100, uploaded_by=user.id, status="READY",
    )
    session.add(doc)
    session.flush()
    for i, text in enumerate(texts):
        session.add(DocumentChunk(
            document_id=doc.id, chunk_index=i, text=text,
            page_number=1, char_start=0, char_end=len(text),
            token_count=len(text.split()),
        ))
    session.commit()
    return doc


def test_spreadsheet_csv_parsing(tmp_path):
    csv_path = tmp_path / "production.csv"
    csv_path.write_text(
        "Month,Mine,Production (t),OB (m3)\n"
        "Jan-2026,KHD,125000,340000\n"
        "Feb-2026,KHD,118500,331000\n",
        encoding="utf-8",
    )
    rows = _read_spreadsheet_rows(csv_path)
    assert len(rows) == 3
    assert rows[0][0] == "Month"
    assert rows[1][2] == "125000"


def test_spreadsheet_xlsx_parsing(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    xlsx_path = tmp_path / "geology.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Boreholes"
    ws.append(["Borehole", "Depth_m", "Seam"])
    ws.append(["BH-01", 142.5, "R-VI"])
    ws.append(["BH-02", 158.0, "R-V"])
    wb.save(xlsx_path)

    rows = _read_spreadsheet_rows(xlsx_path)
    assert rows[0][0] == "=== Sheet: Boreholes ==="
    assert any("BH-01" in cell for row in rows for cell in row)


def test_topics_with_corpus(session):
    _make_doc_with_chunks(session, "doc_geo.pdf", [
        "Coal seam correlation across the northern sector shows consistent thickness "
        "in borehole intersections and stable overburden ratios for open cast planning.",
        "Exploration drilling established proved reserves with good coal quality and "
        "low ash content supporting the mine plan for the proposed expansion block.",
    ])
    _make_doc_with_chunks(session, "doc_safety.pdf", [
        "Safety incidents were concentrated around haul road traffic management and "
        "equipment maintenance schedules during the monsoon season shutdown period.",
        "Accident prevention measures include worker training programmes, equipment "
        "inspection routines and emergency response drills at the opencast mine.",
    ])

    result = compute_topics(session, n_topics=2)
    assert result["document_count"] == 2
    assert len(result["wordcloud"]) > 0
    assert len(result["topics"]) >= 1
    for topic in result["topics"]:
        assert topic["label"]
        assert len(topic["keywords"]) > 0
        assert topic["document_count"] >= 1
    # Word cloud excludes stopwords
    cloud_terms = {w["text"] for w in result["wordcloud"]}
    assert "the" not in cloud_terms


def test_export_docx_and_pdf(session):
    from app.db.models import Bench, Mine, Report, Role, Sector, Subsidiary

    if not session.query(Role).filter(Role.code == "FOREMAN").first():
        session.add(Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True))
        session.flush()

    sub = session.query(Subsidiary).filter(Subsidiary.code == "TEST").first()
    if not sub:
        sub = Subsidiary(code="TEST", name="Test Subsidiary")
        session.add(sub)
        session.flush()
    sector = session.query(Sector).filter(Sector.code == "MINING").first()
    if not sector:
        sector = Sector(code="MINING")
        session.add(sector)
        session.flush()
    mine = session.query(Mine).filter(Mine.code == "TESTMINE").first()
    if not mine:
        mine = Mine(subsidiary_id=sub.id, sector_id=sector.id, code="TESTMINE", name="Test Mine")
        session.add(mine)
        session.flush()
    bench = Bench(mine_id=mine.id, code="B1", bench_type="SURFACE", name="Bench 1")
    session.add(bench)
    session.flush()

    report = Report(
        uuid="test-export-uuid", level="DAILY", mine_id=mine.id, bench_id=bench.id,
        period_start=__import__("datetime").date(2026, 9, 1),
        period_end=__import__("datetime").date(2026, 9, 1),
        status="APPROVED", expected_children=3, present_children=2,
    )
    session.add(report)
    session.flush()
    from app.db.models import ReportMetric
    session.add(ReportMetric(
        report_id=report.id, metric_code="production_milli_t",
        value_int=125_000, unit="milli_t", is_additive=True,
    ))
    session.add(ReportMetric(
        report_id=report.id, metric_code="ob_milli_m3",
        value_int=340_000, unit="milli_m3", is_additive=True,
    ))
    session.commit()

    docx_path = export_report(session, report, "docx")
    assert docx_path.exists() and docx_path.stat().st_size > 500
    assert docx_path.suffix == ".docx"

    pdf_path = export_report(session, report, "pdf")
    assert pdf_path.exists() and pdf_path.stat().st_size > 500
    assert pdf_path.suffix == ".pdf"

    # PDF magic bytes
    assert pdf_path.read_bytes()[:4] == b"%PDF"


def test_export_invalid_format(session):
    from app.db.models import Report

    report = session.query(Report).first()
    if report is None:
        pytest.skip("no report available")
    with pytest.raises(ValueError):
        export_report(session, report, "xlsx")
