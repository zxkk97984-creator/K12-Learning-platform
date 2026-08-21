"""Rule-based ingestion: Parser -> Chunker -> Embedding Provider -> DB."""

from io import BytesIO
import hashlib
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding import get_embedding
from app.infrastructure.database.models import (
    KnowledgeChunk,
    KnowledgeResource,
)

MAX_CHUNK_CHARS = 500
STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "knowledge"


def parse_markdown(text: str) -> list[dict[str, str]]:
    """Split Markdown/TXT into heading-scoped blocks."""
    blocks: list[dict[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if content:
            blocks.append(
                {
                    "content_type": current_heading or "plain",
                    "content": content,
                }
            )

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            current_lines = []
            current_heading = stripped.lstrip("#").strip()
        else:
            current_lines.append(line)
    flush()
    return blocks


def chunk_blocks(
    blocks: list[dict[str, str]],
    *,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for block in blocks:
        content = block["content"]
        if len(content) <= max_chars:
            chunks.append(block)
            continue
        for index in range(0, len(content), max_chars):
            chunks.append(
                {
                    "content_type": block["content_type"],
                    "content": content[index : index + max_chars],
                }
            )
    return chunks


def storage_path_for(storage_key: str) -> Path:
    """Resolve a stored resource key without allowing path traversal."""
    path = STORAGE_ROOT / storage_key
    root = STORAGE_ROOT.resolve()
    if root not in path.resolve().parents:
        raise ValueError("invalid storage key")
    return path


def _pdf_literal_strings(data: bytes) -> list[str]:
    """Extract PDF literal strings from a content stream.

    This is deliberately small and dependency-free.  It covers the plain and
    Flate-compressed text streams used by the local seed/tests; if pypdf is
    installed, ``parse_pdf`` tries it first for broader PDF compatibility.
    """
    strings: list[str] = []
    index = 0
    while index < len(data):
        if data[index] != ord("("):
            index += 1
            continue
        index += 1
        depth = 1
        value = bytearray()
        while index < len(data) and depth:
            byte = data[index]
            index += 1
            if byte == ord("\\") and index < len(data):
                escaped = data[index]
                index += 1
                value.extend(
                    {
                        ord("n"): b"\n",
                        ord("r"): b"\r",
                        ord("t"): b"\t",
                        ord("b"): b"\b",
                        ord("f"): b"\f",
                    }.get(escaped, bytes([escaped]))
                )
            elif byte == ord("("):
                depth += 1
                value.append(byte)
            elif byte == ord(")"):
                depth -= 1
                if depth:
                    value.append(byte)
            else:
                value.append(byte)
        if depth == 0 and value.strip():
            strings.append(value.decode("utf-8", errors="replace").strip())
    return strings


def _pdf_content_streams(data: bytes) -> list[bytes]:
    streams: list[bytes] = []
    for marker in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", marker.end())
        if end < 0:
            continue
        stream = data[marker.end() : end].rstrip(b"\r\n")
        header = data[max(0, marker.start() - 512) : marker.start()]
        if b"/FlateDecode" in header:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        streams.append(stream)
    return streams


def parse_pdf(data: bytes) -> str:
    """Extract text from a PDF without adding a mandatory runtime dependency."""
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        PdfReader = None

    if PdfReader is not None:
        try:
            reader = PdfReader(BytesIO(data))
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
            if extracted.strip():
                return extracted.strip()
        except Exception:
            # Fall through to the small stdlib parser for simple documents.
            pass

    streams = _pdf_content_streams(data)
    if not streams:
        streams = [data]
    parts = [part for stream in streams for part in _pdf_literal_strings(stream)]
    extracted = "\n".join(part for part in parts if part.strip()).strip()
    if not extracted:
        raise ValueError(
            "PDF contains no extractable text; install pypdf for scanned/complex PDFs"
        )
    return extracted


def _embedding_value(text: str) -> str:
    vector = get_embedding(text)
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def storage_key_for(source_url: str, source_name: str) -> str:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]
    name = Path(source_name).stem.replace(" ", "-")
    return f"knowledge/{digest}/{name}.md"


async def ingest_text(
    session: AsyncSession,
    *,
    text: str,
    source_name: str,
    source_url: str,
    license: str,
    copyright_status: str,
    author: str | None = None,
    storage_key: str | None = None,
    knowledge_point_ids: list[str] | None = None,
    force_reprocess: bool = False,
    file_type: str = "MARKDOWN",
    parsed_blocks: list[dict[str, str]] | None = None,
    preserve_status: bool = False,
) -> tuple[UUID, int]:
    storage_key = storage_key or storage_key_for(source_url, source_name)
    existing = (
        await session.execute(
            select(KnowledgeResource).where(
                KnowledgeResource.source_url == source_url,
                KnowledgeResource.storage_key == storage_key,
            )
        )
    ).scalar_one_or_none()
    if (
        existing is not None
        and existing.status == "READY"
        and not force_reprocess
    ):
        return existing.resource_id, 0

    now = datetime.now(timezone.utc)
    if existing is None:
        resource = KnowledgeResource(
            resource_id=uuid4(),
            source_name=source_name,
            source_url=source_url,
            author=author,
            license=license,
            copyright_status=copyright_status,
            storage_key=storage_key,
            file_type=file_type,
            status="UPLOADED",
            uploaded_at=now,
        )
        session.add(resource)
    else:
        resource = existing
        if not preserve_status:
            resource.status = "UPLOADED"
            resource.error = None
            resource.updated_at = now
        await session.execute(
            KnowledgeChunk.__table__.delete().where(
                KnowledgeChunk.resource_id == existing.resource_id
            )
        )
    await session.flush()

    try:
        if not preserve_status:
            resource.status = "PARSING"
        blocks = parsed_blocks if parsed_blocks is not None else parse_markdown(text)
        resource.status = "CHUNKING"
        chunks = chunk_blocks(blocks)
        resource.status = "INDEXING"
        kp_ids = knowledge_point_ids or []
        for index, chunk in enumerate(chunks):
            embedding = _embedding_value(chunk["content"])
            session.add(
                KnowledgeChunk(
                    chunk_id=uuid4(),
                    resource_id=resource.resource_id,
                    chunk_index=index,
                    content=chunk["content"],
                    content_type=chunk["content_type"],
                    metadata_={
                        "source_url": source_url,
                        "license": license,
                        "copyright_status": copyright_status,
                        "source_ids": [str(resource.resource_id)],
                        "heading": chunk["content_type"],
                    },
                    knowledge_point_ids=kp_ids,
                    embedding=embedding,
                    token_count=len(chunk["content"]),
                    status="READY",
                )
            )
        resource.status = "READY"
        resource.error = None
        resource.updated_at = now
        await session.commit()
        return resource.resource_id, len(chunks)
    except Exception as exc:
        resource.status = "FAILED"
        resource.error = str(exc)
        resource.updated_at = datetime.now(timezone.utc)
        await session.commit()
        raise


async def ingest_stored_resource(
    session: AsyncSession,
    resource_id: UUID,
    *,
    force_reprocess: bool = False,
) -> tuple[UUID, int]:
    """Parse and index an uploaded resource from storage in Worker context."""
    resource = await session.get(KnowledgeResource, resource_id)
    if resource is None:
        raise ValueError(f"knowledge resource not found: {resource_id}")
    try:
        resource.status = "PARSING"
        resource.error = None
        resource.updated_at = datetime.now(timezone.utc)
        await session.commit()

        path = storage_path_for(str(resource.storage_key))
        if not path.is_file():
            raise FileNotFoundError("stored source file is missing")
        raw = path.read_bytes()
        if resource.file_type == "PDF":
            text = parse_pdf(raw)
        else:
            text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            raise ValueError("source file contains no extractable text")
        parsed_blocks = parse_markdown(text)
        if not parsed_blocks:
            raise ValueError("source file contains no indexable text")

        resource = await session.get(KnowledgeResource, resource_id)
        if resource is None:  # pragma: no cover - protected by the first lookup
            raise ValueError(f"knowledge resource not found: {resource_id}")
        resource.status = "CHUNKING"
        resource.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return await ingest_text(
            session,
            text=text,
            source_name=resource.source_name,
            source_url=resource.source_url,
            license=resource.license,
            copyright_status=resource.copyright_status,
            author=resource.author,
            storage_key=str(resource.storage_key),
            knowledge_point_ids=None,
            force_reprocess=force_reprocess or resource.status != "READY",
            file_type=resource.file_type,
            parsed_blocks=parsed_blocks,
            preserve_status=True,
        )
    except Exception as exc:
        await session.rollback()
        resource = await session.get(KnowledgeResource, resource_id)
        if resource is not None:
            resource.status = "FAILED"
            resource.error = str(exc)[:4000]
            resource.updated_at = datetime.now(timezone.utc)
            await session.commit()
        raise
