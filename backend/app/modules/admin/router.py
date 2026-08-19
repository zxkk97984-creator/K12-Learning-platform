import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin
from app.api.envelope import ok
from app.infrastructure.database.session import get_session
from app.modules.admin.schemas import (
    CreateBookRequest,
    CreateChapterRequest,
    CreateContentBlockRequest,
    CreateKnowledgePointRequest,
    PatchBookRequest,
    PatchChapterRequest,
    PatchContentBlockRequest,
    PatchKnowledgePointRequest,
    PatchKnowledgeResourceRequest,
)
from app.modules.admin.service import (
    AdminService,
    IdempotencyService,
    canonical_request_hash,
)

router = APIRouter(tags=["admin"])
service = AdminService()
idempotency = IdempotencyService()


async def require_idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not key:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Idempotency-Key header is required",
            },
        )
    return key


def actor_id(admin: AdminPrincipal) -> UUID:
    return admin.admin_id or admin.user_id


@router.get("/admin/stats")
async def get_stats(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return ok(await service.stats(session))


@router.get("/admin/books")
async def list_books(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    rows, next_cursor, has_more = await service.list_books(
        session,
        status=status,
        cursor=cursor,
        limit=limit,
    )
    return ok(rows, {"next_cursor": next_cursor, "has_more": has_more})


@router.post("/admin/books", status_code=201)
async def create_book(
    admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    body: CreateBookRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
    response: Response,
):
    result, replayed = await idempotency.execute(
        session,
        actor_id=actor_id(admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _create_book(session, admin, body),
    )
    if replayed:
        response.status_code = 200
    return result


async def _create_book(session, admin, body):
    return ok(jsonable_encoder(await service.create_book(session, admin, body)))


@router.get("/admin/books/{book_id}")
async def get_book(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    book_id: UUID,
):
    return ok(await service.get_book(session, book_id))


@router.patch("/admin/books/{book_id}")
async def patch_book(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    book_id: UUID,
    body: PatchBookRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
):
    result, _ = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _patch_book(session, book_id, body),
    )
    return result


async def _patch_book(session, book_id, body):
    return ok(jsonable_encoder(await service.patch_book(session, book_id, body)))


@router.post("/admin/books/{book_id}/chapters", status_code=201)
async def create_chapter(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    book_id: UUID,
    body: CreateChapterRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
    response: Response,
):
    result, replayed = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _create_chapter(session, book_id, body),
    )
    if replayed:
        response.status_code = 200
    return result


async def _create_chapter(session, book_id, body):
    return ok(await service.create_chapter(session, book_id, body))


@router.patch("/admin/chapters/{chapter_id}")
async def patch_chapter(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    chapter_id: UUID,
    body: PatchChapterRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
):
    result, _ = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _patch_chapter(session, chapter_id, body),
    )
    return result


async def _patch_chapter(session, chapter_id, body):
    return ok(await service.patch_chapter(session, chapter_id, body))


@router.post("/admin/chapters/{chapter_id}/content-blocks", status_code=201)
async def create_content_block(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    chapter_id: UUID,
    body: CreateContentBlockRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
    response: Response,
):
    result, replayed = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _create_content_block(session, chapter_id, body),
    )
    if replayed:
        response.status_code = 200
    return result


async def _create_content_block(session, chapter_id, body):
    return ok(await service.create_content_block(session, chapter_id, body))


@router.patch("/admin/content-blocks/{block_id}")
async def patch_content_block(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    block_id: UUID,
    body: PatchContentBlockRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
):
    result, _ = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _patch_content_block(session, block_id, body),
    )
    return result


async def _patch_content_block(session, block_id, body):
    return ok(await service.patch_content_block(session, block_id, body))


@router.post("/admin/knowledge-points", status_code=201)
async def create_knowledge_point(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    body: CreateKnowledgePointRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
    response: Response,
):
    result, replayed = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _create_knowledge_point(session, body),
    )
    if replayed:
        response.status_code = 200
    return result


async def _create_knowledge_point(session, body):
    return ok(await service.create_knowledge_point(session, body))


@router.patch("/admin/knowledge-points/{knowledge_point_id}")
async def patch_knowledge_point(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    knowledge_point_id: UUID,
    body: PatchKnowledgePointRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
):
    result, _ = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _patch_knowledge_point(session, knowledge_point_id, body),
    )
    return result


async def _patch_knowledge_point(session, knowledge_point_id, body):
    return ok(await service.patch_knowledge_point(session, knowledge_point_id, body))


@router.post("/admin/knowledge/resources", status_code=201)
async def upload_knowledge_resource(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
    source_name: Annotated[str, Form()],
    source_url: Annotated[str, Form()],
    license: Annotated[str, Form()],
    copyright_status: Annotated[str, Form()],
    key: Annotated[str, Depends(require_idempotency_key)],
    response: Response,
    author: Annotated[str | None, Form()] = None,
):
    file_bytes = await file.read()
    request_hash = canonical_request_hash(
        {
            "filename": file.filename,
            "source_name": source_name,
            "source_url": source_url,
            "author": author,
            "license": license,
            "copyright_status": copyright_status,
            "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        }
    )
    result, replayed = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=request_hash,
        handler=lambda: _upload_knowledge_resource(
            session,
            _admin,
            file_bytes=file_bytes,
            filename=file.filename or "resource.txt",
            source_name=source_name,
            source_url=source_url,
            author=author,
            license=license,
            copyright_status=copyright_status,
        ),
    )
    if replayed:
        response.status_code = 200
    return result


async def _upload_knowledge_resource(session, admin, **kwargs):
    return ok(
        jsonable_encoder(
            await service.upload_knowledge_resource(session, admin, **kwargs)
        )
    )


@router.patch("/admin/knowledge/resources/{resource_id}")
async def patch_knowledge_resource(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    resource_id: UUID,
    body: PatchKnowledgeResourceRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
):
    result, _ = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _patch_knowledge_resource(session, resource_id, body),
    )
    return result


async def _patch_knowledge_resource(session, resource_id, body):
    return ok(
        jsonable_encoder(
            await service.patch_knowledge_resource(session, resource_id, body)
        )
    )


@router.post("/admin/knowledge/resources/{resource_id}/reprocess")
async def reprocess_knowledge_resource(
    _admin: Annotated[AdminPrincipal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    resource_id: UUID,
    key: Annotated[str, Depends(require_idempotency_key)],
):
    result, _ = await idempotency.execute(
        session,
        actor_id=actor_id(_admin),
        actor_type="ADMIN",
        key=key,
        request_hash=canonical_request_hash({"resource_id": str(resource_id)}),
        handler=lambda: _reprocess_knowledge_resource(session, resource_id),
    )
    return result


async def _reprocess_knowledge_resource(session, resource_id):
    return ok(
        jsonable_encoder(
            await service.reprocess_knowledge_resource(session, resource_id)
        )
    )
