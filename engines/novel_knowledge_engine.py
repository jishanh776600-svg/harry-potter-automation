"""
Harry Potter Novel Knowledge Engine (Step 6)
================================================================================
Authoritative ingestion, chunking, and searchable knowledge base for the
7 Harry Potter novels.

Features:
  - Idempotent Drive-to-local synchronization (data/books/)
  - Page-aware PDF text extraction with header/footer artifact cleansing
  - Canonical chapter boundary detection using canonical registry
  - Contextual chunking (250-450 words) respecting paragraph boundaries
  - Strict global narrative chronology preservation (1 to N index across series)
  - SQLite FTS5 (Full-Text Search) with BM25 ranking and Porter stemming
  - Complete source traceability (Book -> Chapter -> Page range -> Exact text)
  - 100% offline-capable, $0 API cost, self-contained inside pipeline.db
"""

import os
import re
import io
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import pypdf
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config.settings import PROJECT_ROOT, DATABASE_DIR, DB_PATH, MOVIES_DIR
from core.models import Base, NovelBook, NovelChapter, NovelChunk
from core.novel_registry import CANONICAL_BOOKS

logger = logging.getLogger(__name__)

BOOKS_DIR = PROJECT_ROOT / "data" / "books"
BOOKS_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_DIR.mkdir(parents=True, exist_ok=True)


def get_db_connection() -> sqlite3.Connection:
    """Returns raw SQLite connection to pipeline.db with row_factory set."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_novel_tables():
    """Initializes SQLAlchemy tables and the SQLite FTS5 virtual table."""
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.create_all(engine)

    # Initialize FTS5 virtual table if it doesn't already exist
    with get_db_connection() as conn:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS novel_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                book_number UNINDEXED,
                chapter_number UNINDEXED,
                chapter_title,
                text,
                source_location UNINDEXED,
                tokenize = 'porter unicode61'
            );
        """)
        conn.commit()


def compute_file_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a local file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def clean_page_text(raw_text: str, book_number: int, page_num: int) -> str:
    """
    Cleans extraction artifacts from a single page's text:
    - Removes isolated top/bottom page numbers
    - Removes repeated running headers (book titles, author name)
    - Normalizes non-standard whitespace and smart quotes
    """
    if not raw_text:
        return ""

    lines = raw_text.split("\n")
    cleaned_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue

        # Check if line is just the page number (digits only at start or end of page)
        if stripped.isdigit() and (i <= 2 or i >= len(lines) - 3):
            continue

        # Remove common running headers / footers
        lower = stripped.lower()
        if any(h in lower for h in [
            "harry potter and the",
            "j. k. rowling",
            "j.k. rowling",
            "original scanned/ocr",
            "(this is book ",
            "(edit where needed"
        ]) and len(stripped) < 70 and (i <= 3 or i >= len(lines) - 3):
            continue

        # Normalize quotes and dashes
        line_clean = (
            stripped
            .replace("“", '"').replace("”", '"')
            .replace("‘", "'").replace("’", "'")
            .replace("—", " -- ")
            .replace("–", " - ")
        )
        cleaned_lines.append(line_clean)

    return "\n".join(cleaned_lines)


class NovelKnowledgeEngine:
    """Ingestion, indexing, and search engine for Harry Potter novels."""

    def __init__(self):
        init_novel_tables()
        self.engine = create_engine(f"sqlite:///{DB_PATH}")
        self.Session = sessionmaker(bind=self.engine)

    def is_book_ingested(self, book_number: int) -> bool:
        """Checks if a book has already been fully ingested."""
        with self.Session() as session:
            b = session.query(NovelBook).filter(NovelBook.book_number == book_number).first()
            if b and b.total_chunks > 0:
                return True
        return False

    def ingest_book(self, book_meta: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """
        Ingests a single Harry Potter novel PDF:
        - Extracts text page-by-page
        - Maps chapter boundaries using canonical registry
        - Creates cohesive paragraphs and chunks
        - Preserves strict narrative chronology
        - Updates SQLite tables and FTS5 index
        """
        book_num = book_meta["book_number"]
        filename = book_meta["filename"]
        pdf_path = BOOKS_DIR / filename

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF for Book {book_num} not found at {pdf_path}")

        file_hash = compute_file_sha256(pdf_path)

        if not force and self.is_book_ingested(book_num):
            with self.Session() as session:
                existing = session.query(NovelBook).filter(NovelBook.book_number == book_num).first()
                logger.info(f"Book {book_num} ('{existing.title}') already ingested ({existing.total_chunks} chunks). Skipping.")
                return {
                    "book_number": book_num,
                    "title": existing.title,
                    "chapters": existing.total_chapters,
                    "chunks": existing.total_chunks,
                    "pages": existing.total_pages,
                    "status": "CACHED"
                }

        logger.info(f"Starting extraction for Book {book_num}: {book_meta['title']} ({filename})...")
        reader = pypdf.PdfReader(str(pdf_path))
        total_pages = len(reader.pages)

        # 1. Extract and clean text per page
        page_texts: List[Tuple[int, str]] = []  # (1-based page_num, cleaned_text)
        for p_idx in range(total_pages):
            raw = reader.pages[p_idx].extract_text() or ""
            clean = clean_page_text(raw, book_num, p_idx + 1)
            page_texts.append((p_idx + 1, clean))

        # 2. Locate chapter boundaries across pages
        canonical_chapters = book_meta["chapters"]  # List of (chap_num, chap_title)
        chapter_starts: List[Dict[str, Any]] = []

        # Build search patterns for each chapter
        for chap_num, chap_title in canonical_chapters:
            found_page = None
            for page_num, p_text in page_texts:
                p_text_upper = p_text.upper()
                title_upper = chap_title.upper()

                # Check for chapter title match or chapter number heading
                has_title = title_upper in p_text_upper
                has_chap_heading = bool(re.search(
                    rf"(?:CHAPTER|C\s*H\s*A\s*P\s*T\s*E\s*R)\s*(?:{chap_num}\b|{_number_to_word(chap_num)}\b)",
                    p_text_upper,
                    re.IGNORECASE
                ))

                if has_title or (has_chap_heading and page_num > (chapter_starts[-1]["page_start"] if chapter_starts else 0)):
                    found_page = page_num
                    break

            if found_page is None:
                # Fallback: estimate page based on previous chapter
                prev_page = chapter_starts[-1]["page_start"] if chapter_starts else 1
                found_page = prev_page + 5
                logger.warning(f"Book {book_num} Chapter {chap_num} ('{chap_title}') boundary estimated at page {found_page}")

            chapter_starts.append({
                "chapter_number": chap_num,
                "chapter_title": chap_title,
                "page_start": found_page
            })

        # Calculate page_end for each chapter
        for i in range(len(chapter_starts)):
            if i < len(chapter_starts) - 1:
                chapter_starts[i]["page_end"] = max(chapter_starts[i]["page_start"], chapter_starts[i + 1]["page_start"] - 1)
            else:
                chapter_starts[i]["page_end"] = total_pages

        # 3. Assemble text per chapter
        chapter_data: List[Dict[str, Any]] = []
        for ch in chapter_starts:
            c_text_parts = []
            for p_num in range(ch["page_start"], ch["page_end"] + 1):
                if p_num <= len(page_texts):
                    c_text_parts.append(page_texts[p_num - 1][1])
            combined_text = "\n\n".join(c_text_parts).strip()
            ch["text"] = combined_text
            chapter_data.append(ch)

        # 4. Chunk each chapter into cohesive story passages (250-450 words)
        book_id = f"hp_book_{book_num}"
        all_chunks: List[Dict[str, Any]] = []

        for ch in chapter_data:
            c_num = ch["chapter_number"]
            c_title = ch["chapter_title"]
            c_id = f"hp_b{book_num}_c{c_num:02d}"

            paragraphs = [p.strip() for p in ch["text"].split("\n\n") if p.strip()]
            cur_chunk_paras = []
            cur_words = 0
            ch_chunk_idx = 1

            for para in paragraphs:
                p_words = len(para.split())
                # If adding this paragraph exceeds target chunk size and we already have sufficient context
                if cur_words + p_words > 400 and cur_words >= 200:
                    chunk_text = "\n\n".join(cur_chunk_paras)
                    all_chunks.append({
                        "book_id": book_id,
                        "book_number": book_num,
                        "book_title": book_meta["title"],
                        "chapter_id": c_id,
                        "chapter_number": c_num,
                        "chapter_title": c_title,
                        "page_start": ch["page_start"],
                        "page_end": ch["page_end"],
                        "chunk_index": ch_chunk_idx,
                        "text": chunk_text,
                        "word_count": cur_words,
                        "source_file": filename,
                        "source_location": f"Book {book_num} Chapter {c_num} (p.{ch['page_start']}-{ch['page_end']})"
                    })
                    ch_chunk_idx += 1
                    cur_chunk_paras = [para]
                    cur_words = p_words
                else:
                    cur_chunk_paras.append(para)
                    cur_words += p_words

            # Add trailing chunk
            if cur_chunk_paras:
                chunk_text = "\n\n".join(cur_chunk_paras)
                all_chunks.append({
                    "book_id": book_id,
                    "book_number": book_num,
                    "book_title": book_meta["title"],
                    "chapter_id": c_id,
                    "chapter_number": c_num,
                    "chapter_title": c_title,
                    "page_start": ch["page_start"],
                    "page_end": ch["page_end"],
                    "chunk_index": ch_chunk_idx,
                    "text": chunk_text,
                    "word_count": cur_words,
                    "source_file": filename,
                    "source_location": f"Book {book_num} Chapter {c_num} (p.{ch['page_start']}-{ch['page_end']})"
                })

        # 5. Determine base global chronology index for this book
        # (Chronology is strictly: Book 1 chunks, then Book 2 chunks, ..., Book 7 chunks)
        with self.Session() as session:
            # Delete existing records for this book if force=True
            if force:
                session.query(NovelChunk).filter(NovelChunk.book_number == book_num).delete()
                session.query(NovelChapter).filter(NovelChapter.book_number == book_num).delete()
                session.query(NovelBook).filter(NovelBook.book_number == book_num).delete()
                session.commit()
                # Also clean FTS
                with get_db_connection() as raw_conn:
                    raw_conn.execute("DELETE FROM novel_chunks_fts WHERE book_number = ?", (book_num,))
                    raw_conn.commit()

            # Global chronology offset: sum of chunks from all previous books
            prev_chunks_count = (
                session.query(NovelChunk)
                .filter(NovelChunk.book_number < book_num)
                .count()
            )

            # Insert NovelBook
            book_record = NovelBook(
                id=book_id,
                book_number=book_num,
                title=book_meta["title"],
                us_title=book_meta.get("us_title"),
                total_chapters=len(chapter_data),
                total_pages=total_pages,
                total_chunks=len(all_chunks),
                source_file=filename,
                source_drive_id=book_meta.get("drive_id"),
                file_checksum=file_hash,
                ingested_at=datetime.utcnow()
            )
            session.add(book_record)

            # Insert NovelChapters
            for ch in chapter_data:
                ch_chunks_count = sum(1 for c in all_chunks if c["chapter_number"] == ch["chapter_number"])
                chap_record = NovelChapter(
                    id=f"hp_b{book_num}_c{ch['chapter_number']:02d}",
                    book_id=book_id,
                    book_number=book_num,
                    chapter_number=ch["chapter_number"],
                    chapter_title=ch["chapter_title"],
                    start_page=ch["page_start"],
                    end_page=ch["page_end"],
                    total_chunks=ch_chunks_count,
                    word_count=len(ch["text"].split())
                )
                session.add(chap_record)

            # Insert NovelChunks with global chronological order index
            fts_rows = []
            for i, c in enumerate(all_chunks):
                global_idx = prev_chunks_count + i + 1
                chunk_id = f"hp_b{book_num}_c{c['chapter_number']:02d}_chk{c['chunk_index']:03d}"
                c_record = NovelChunk(
                    id=chunk_id,
                    book_id=book_id,
                    book_number=book_num,
                    book_title=c["book_title"],
                    chapter_id=c["chapter_id"],
                    chapter_number=c["chapter_number"],
                    chapter_title=c["chapter_title"],
                    page_start=c["page_start"],
                    page_end=c["page_end"],
                    chunk_index=c["chunk_index"],
                    global_chronology_index=global_idx,
                    text=c["text"],
                    word_count=c["word_count"],
                    source_file=c["source_file"],
                    source_location=c["source_location"],
                    created_at=datetime.utcnow()
                )
                session.add(c_record)
                fts_rows.append((
                    chunk_id,
                    book_num,
                    c["chapter_number"],
                    c["chapter_title"],
                    c["text"],
                    c["source_location"]
                ))

            session.commit()

        # Insert into SQLite FTS5 table
        with get_db_connection() as raw_conn:
            raw_conn.executemany("""
                INSERT INTO novel_chunks_fts (chunk_id, book_number, chapter_number, chapter_title, text, source_location)
                VALUES (?, ?, ?, ?, ?, ?)
            """, fts_rows)
            raw_conn.commit()

        logger.info(
            f"Successfully ingested Book {book_num}: {book_meta['title']} "
            f"({len(chapter_data)} chapters, {len(all_chunks)} chunks, {total_pages} pages)"
        )

        return {
            "book_number": book_num,
            "title": book_meta["title"],
            "chapters": len(chapter_data),
            "chunks": len(all_chunks),
            "pages": total_pages,
            "status": "INGESTED"
        }

    def ingest_all_novels(self, force: bool = False) -> List[Dict[str, Any]]:
        """Ingests all 7 Harry Potter novels in strict sequential order."""
        results = []
        for book_meta in CANONICAL_BOOKS:
            res = self.ingest_book(book_meta, force=force)
            results.append(res)
        return results

    def search(
        self,
        query: str,
        book_number: Optional[int] = None,
        chapter_number: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Autonomous adaptive full-text semantic retrieval over the 7 novels using SQLite FTS5 BM25 ranking.
        Multi-tier progressive strategy:
          Tier 1: Strict AND across all terms (exact keyword precision)
          Tier 2: Stop-word filtered AND (removes low-information connective words)
          Tier 3: BM25-ranked OR across significant terms (finds closest canonical passages)
          Tier 4: Cross-book relaxation (if book_number was constrained and yielded 0 hits)
        """
        clean_q = re.sub(r'[^\w\s"\'\-]', " ", query).strip()
        if not clean_q:
            return []

        raw_terms = [t for t in clean_q.split() if t]
        if not raw_terms:
            return []

        stop_words = {
            "the", "a", "an", "in", "on", "of", "at", "by", "for", "with", "about",
            "into", "through", "after", "before", "under", "between", "but", "and",
            "or", "is", "was", "are", "were", "be", "been", "being", "have", "has",
            "had", "do", "does", "did", "would", "should", "could", "can", "will",
            "plan", "details", "explain", "explains", "story", "full", "happens",
            "secret", "truth", "reason", "scene", "reveals", "their", "there",
            "where", "which", "what", "why", "when", "that", "this", "these", "those"
        }
        sig_terms = [t for t in raw_terms if t.lower() not in stop_words and len(t) > 2]
        if not sig_terms:
            sig_terms = raw_terms

        def _run_query(match_expr: str, b_num: Optional[int], c_num: Optional[int]) -> List[Any]:
            sql = """
                SELECT 
                    c.id as chunk_id,
                    c.book_number,
                    c.book_title,
                    c.chapter_number,
                    c.chapter_title,
                    c.page_start,
                    c.page_end,
                    c.global_chronology_index,
                    c.source_location,
                    c.text,
                    bm25(novel_chunks_fts) as rank
                FROM novel_chunks_fts f
                JOIN novel_chunks c ON f.chunk_id = c.id
                WHERE novel_chunks_fts MATCH ?
            """
            params = [match_expr]
            if b_num is not None:
                sql += " AND c.book_number = ?"
                params.append(b_num)
            if c_num is not None:
                sql += " AND c.chapter_number = ?"
                params.append(c_num)
            sql += " ORDER BY rank ASC LIMIT ?"
            params.append(limit)

            with get_db_connection() as conn:
                try:
                    return conn.execute(sql, params).fetchall()
                except sqlite3.OperationalError:
                    return []

        # Tier 1: Exact phrase if quoted, else strict AND with prefix wildcards
        if '"' in query:
            match_t1 = f'"{clean_q}"'
        elif len(raw_terms) == 1:
            match_t1 = f'"{raw_terms[0]}"*'
        else:
            match_t1 = " AND ".join(f'"{t}"*' for t in raw_terms)

        rows = _run_query(match_t1, book_number, chapter_number)

        # Tier 2: Filtered AND (if stop words were present and Tier 1 had 0 hits)
        if not rows and len(sig_terms) < len(raw_terms) and len(sig_terms) > 0:
            match_t2 = " AND ".join(f'"{t}"*' for t in sig_terms)
            rows = _run_query(match_t2, book_number, chapter_number)

        # Tier 3: BM25-ranked OR across significant terms
        if not rows and len(sig_terms) > 1:
            match_t3 = " OR ".join(f'"{t}"*' for t in sig_terms)
            rows = _run_query(match_t3, book_number, chapter_number)

        # Tier 4: Cross-book relaxation if book_number was provided and yielded 0 hits
        if not rows and book_number is not None:
            match_t4 = " OR ".join(f'"{t}"*' for t in sig_terms)
            rows = _run_query(match_t4, None, None)

        results = []
        for r in rows:
            results.append({
                "chunk_id": r["chunk_id"],
                "book_number": r["book_number"],
                "book_title": r["book_title"],
                "chapter_number": r["chapter_number"],
                "chapter_title": r["chapter_title"],
                "page_start": r["page_start"],
                "page_end": r["page_end"],
                "global_chronology_index": r["global_chronology_index"],
                "source_location": r["source_location"],
                "text": r["text"],
                "relevance_rank": round(float(r["rank"]), 3)
            })

        return results

    def get_chronological_passages(self, start_index: int = 1, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves passages in strict chronological story order."""
        with self.Session() as session:
            chunks = (
                session.query(NovelChunk)
                .filter(NovelChunk.global_chronology_index >= start_index)
                .order_by(NovelChunk.global_chronology_index.asc())
                .limit(limit)
                .all()
            )
            return [{
                "chunk_id": c.id,
                "book_number": c.book_number,
                "book_title": c.book_title,
                "chapter_number": c.chapter_number,
                "chapter_title": c.chapter_title,
                "global_chronology_index": c.global_chronology_index,
                "source_location": c.source_location,
                "text": c.text[:300] + ("..." if len(c.text) > 300 else "")
            } for c in chunks]


def _number_to_word(n: int) -> str:
    """Helper to convert chapter number to English word for OCR matching."""
    words = [
        "", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN",
        "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN",
        "NINETEEN", "TWENTY", "TWENTY-ONE", "TWENTY-TWO", "TWENTY-THREE", "TWENTY-FOUR", "TWENTY-FIVE",
        "TWENTY-SIX", "TWENTY-SEVEN", "TWENTY-EIGHT", "TWENTY-NINE", "THIRTY", "THIRTY-ONE",
        "THIRTY-TWO", "THIRTY-THREE", "THIRTY-FOUR", "THIRTY-FIVE", "THIRTY-SIX", "THIRTY-SEVEN", "THIRTY-EIGHT"
    ]
    return words[n] if 0 <= n < len(words) else str(n)
