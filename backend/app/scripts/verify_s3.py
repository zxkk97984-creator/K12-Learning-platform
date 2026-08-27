"""S3 兼容对象存储连通性校验（CLI，真实网络请求）。

用本地 MinIO（docker-compose 的 shuangling-minio，默认 shuangling /
shuangling123，端口 9000）端到端跑通 S3 SigV4 的 put → get → exists 链路，
验证「统一存储抽象」在 s3 backend 下可用。

无需外部云凭据。默认从 .env 读取 S3_* 配置，也可用 --endpoint/--bucket/
--access-key/--secret-key 覆盖。

Usage:
    # 使用 .env 中的 S3_* 配置（若未设置则用下述 MinIO 默认覆盖）
    uv run python -m app.scripts.verify_s3

    # 显式指定（本地 MinIO）
    uv run python -m app.scripts.verify_s3 \
        --endpoint http://localhost:9000 --bucket shuangling \
        --access-key shuangling --secret-key shuangling123
"""

import argparse
import asyncio
from uuid import uuid4

from app.config import settings
from app.infrastructure.storage.s3 import S3ObjectStorage


def _build(args: argparse.Namespace) -> S3ObjectStorage:
    return S3ObjectStorage(
        endpoint=args.endpoint or settings.s3_endpoint,
        bucket=args.bucket or settings.s3_bucket,
        region=args.region or settings.s3_region,
        access_key=args.access_key or settings.s3_access_key,
        secret_key=args.secret_key or settings.s3_secret_key,
    )


async def ensure_bucket(storage: S3ObjectStorage) -> None:
    """幂等创建 bucket（MinIO 已存在返回 409，视为成功）。"""
    import httpx

    from datetime import datetime, timezone

    from app.infrastructure.storage.s3 import _sha256_hex, sign_request

    url = f"{storage.endpoint}/{storage.bucket}"
    headers = sign_request(
        method="PUT",
        url=url,
        region=storage.region,
        access_key=storage.access_key,
        secret_key=storage.secret_key,
        payload_hash=_sha256_hex(b""),
        now=datetime.now(timezone.utc),
    )
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        resp = await client.put(url, headers=headers)
    if resp.status_code not in (200, 409):  # 409 = already exists, fine
        raise RuntimeError(f"create bucket failed [{resp.status_code}]: {resp.text[:200]}")


async def verify(storage: S3ObjectStorage) -> None:
    key = f"verify-s3/{uuid4().hex}.txt"
    marker = f"shuangling s3 verifier {uuid4().hex}"
    print(f"[verify-s3] endpoint={storage.endpoint} bucket={storage.bucket}")
    await ensure_bucket(storage)
    print("[verify-s3] bucket ready")
    try:
        print("[verify-s3] put ...")
        await storage.put(key, marker.encode("utf-8"), content_type="text/plain")
        print("[verify-s3] get ...")
        obj = await storage.get(key)
        assert obj.data.decode("utf-8") == marker, "content mismatch after round-trip"
        print(f"[verify-s3] exists ... ({await storage.exists(key)})")
        assert await storage.exists(key) is True
        print("[verify-s3] delete ...")
        # S3ObjectStorage 目前无 delete 方法：直接丢给 httpx DELETE（同 SigV4）。
        import httpx

        from app.infrastructure.storage.s3 import _sha256_hex, sign_request

        from datetime import datetime, timezone

        url = storage._url(key)  # noqa: SLF001 - 连接校验脚本内自用
        headers = sign_request(
            method="DELETE",
            url=url,
            region=storage.region,
            access_key=storage.access_key,
            secret_key=storage.secret_key,
            payload_hash=_sha256_hex(b""),
            now=datetime.now(timezone.utc),
        )
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            resp = await client.delete(url, headers=headers)
        assert resp.status_code < 300, f"delete failed [{resp.status_code}]"
        print("[verify-s3] exists after delete ...")
        assert await storage.exists(key) is False
        print("[verify-s3] PASS: S3 SigV4 put/get/exists/delete 全链路通过")
    finally:
        # 兜底清理，避免残留测试对象。
        try:
            import httpx

            from datetime import datetime, timezone

            from app.infrastructure.storage.s3 import _sha256_hex, sign_request

            if await storage.exists(key):
                url = storage._url(key)  # noqa: SLF001
                headers = sign_request(
                    method="DELETE",
                    url=url,
                    region=storage.region,
                    access_key=storage.access_key,
                    secret_key=storage.secret_key,
                    payload_hash=_sha256_hex(b""),
                    now=datetime.now(timezone.utc),
                )
                async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
                    await client.delete(url, headers=headers)
        except Exception:  # noqa: BLE001 - 清理失败不影响主结果
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="S3 兼容对象存储连通性校验")
    parser.add_argument("--endpoint", help="S3/MinIO endpoint（默认 http://localhost:9000）")
    parser.add_argument("--bucket", help="bucket（默认 shuangling）")
    parser.add_argument("--region", help="region（默认 us-east-1）")
    parser.add_argument("--access-key", help="access key（默认 shuangling）")
    parser.add_argument("--secret-key", help="secret key（默认 shuangling123）")
    args = parser.parse_args()
    asyncio.run(verify(_build(args)))


if __name__ == "__main__":
    main()
