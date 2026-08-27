"""S3 兼容对象存储实现（AWS Signature V4，httpx 异步，无额外依赖）。

支持 MinIO / AWS S3 / 其他兼容端点。签名实现遵循 SigV4 规范，
单元测试使用固定输入校验签名的确定性（不访问网络）。
"""

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.infrastructure.storage.base import (
    StoredObject,
    StorageConfigError,
    StorageError,
    validate_key,
)

_ALGORITHM = "AWS4-HMAC-SHA256"


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign_request(
    *,
    method: str,
    url: str,
    region: str,
    access_key: str,
    secret_key: str,
    payload_hash: str,
    now: datetime,
) -> dict[str, str]:
    """计算 SigV4 Authorization 头（纯函数，便于确定性测试）。"""
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    date_stamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = (
        f"{method}\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [_ALGORITHM, amz_date, scope, _sha256_hex(canonical_request.encode("utf-8"))]
    )
    k_date = _hmac_sha256(f"AWS4{secret_key}".encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, "s3")
    k_signing = _hmac_sha256(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"{_ALGORITHM} Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        endpoint = endpoint or settings.s3_endpoint
        bucket = bucket or settings.s3_bucket
        access_key = access_key or settings.s3_access_key
        secret_key = secret_key or settings.s3_secret_key
        self.region = region or settings.s3_region or "us-east-1"
        missing = [
            name
            for name, value in (
                ("S3_ENDPOINT", endpoint),
                ("S3_BUCKET", bucket),
                ("S3_ACCESS_KEY", access_key),
                ("S3_SECRET_KEY", secret_key),
            )
            if not value
        ]
        if missing:
            raise StorageConfigError(
                "storage_backend=s3 但缺少必需配置："
                + ", ".join(missing)
                + "；请在 .env 中补全或将 STORAGE_BACKEND 改回 local"
            )
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket  # type: ignore[assignment]
        self.access_key = access_key  # type: ignore[assignment]
        self.secret_key = secret_key  # type: ignore[assignment]

    def _url(self, key: str) -> str:
        cleaned = validate_key(key)
        return f"{self.endpoint}/{self.bucket}/{cleaned}"

    def _headers(self, method: str, key: str, data: bytes) -> dict[str, str]:
        payload_hash = _sha256_hex(data)
        headers = sign_request(
            method=method,
            url=self._url(key),
            region=self.region,
            access_key=self.access_key,
            secret_key=self.secret_key,
            payload_hash=payload_hash,
            now=datetime.now(timezone.utc),
        )
        return headers

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        headers = self._headers("PUT", key, data)
        if content_type:
            headers["Content-Type"] = content_type
        # trust_env=False：对象存储指向显式配置的 endpoint，不应被系统 HTTP(S)/SOCKS
        # 代理拦截（尤其 localhost 的 MinIO）。否则用户环境的 socks:// 代理会让
        # httpx 抛 "Unknown scheme for proxy URL"。
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            resp = await client.put(self._url(key), content=data, headers=headers)
        if resp.status_code >= 300:
            raise StorageError(f"S3 put failed [{resp.status_code}]: {resp.text[:200]}")
        return key

    async def get(self, key: str) -> StoredObject:
        headers = self._headers("GET", key, b"")
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            resp = await client.get(self._url(key), headers=headers)
        if resp.status_code == 404:
            raise StorageError(f"object not found: {key}")
        if resp.status_code >= 300:
            raise StorageError(f"S3 get failed [{resp.status_code}]")
        return StoredObject(
            key=key, data=resp.content, content_type=resp.headers.get("content-type")
        )

    async def exists(self, key: str) -> bool:
        headers = self._headers("HEAD", key, b"")
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            resp = await client.head(self._url(key), headers=headers)
        return resp.status_code < 300
