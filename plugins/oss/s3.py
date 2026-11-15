"""极简 S3 客户端：SigV4 签名 + path-style，只做对象存储插件需要的几件事。

不引入 boto3：项目只需要 PUT / HEAD / DELETE 三个动作，
外加一次「上传 → 匿名读取 → 删除」的连通性自检。

参考 fnos-oss 文档：
- S3 API 独立端口，path-style 寻址
- 支持 SigV4（Header 签名）
- 桶策略 private / public-read，public-read 时匿名可 GET/HEAD 对象
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import requests

# 网络超时：上传按 (连接, 读取) 分开，大文件读取给足时间
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 120
HEALTH_KEY = "_infowe_healthcheck.txt"


class S3Error(Exception):
    """带 HTTP 状态与响应片段的异常，方便后台直接展示。"""

    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body
        self.code = ""
        # 从 S3 的 XML 错误体里取出 Code，后台据此给中文提示
        import re

        match = re.search(r"<Code>([^<]+)</Code>", body or "")
        if match:
            self.code = match.group(1)

    def __str__(self) -> str:  # noqa: D105
        text = super().__str__()
        if self.status:
            text = f"{text}（HTTP {self.status}）"
        if self.body:
            text = f"{text}：{self.body[:200]}"
        return text


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date: str, region: str, service: str = "s3") -> bytes:
    key = _hmac(("AWS4" + secret).encode("utf-8"), date)
    key = _hmac(key, region)
    key = _hmac(key, service)
    return _hmac(key, "aws4_request")


def _encode_path(path: str) -> str:
    """按 S3 规范编码 URI：保留 '/' 与 '~'，中文与空格转义。"""
    return quote(path, safe="/~")


@dataclass
class S3Config:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    public_base: str = ""
    prefix: str = "uploads/"
    # 是否把 host 头纳入签名。标准 SigV4 要求签；
    # 但如果前面有反向代理改写了 Host，服务端算出的签名会和客户端不同，
    # 只能退化为「不签 host」的兼容模式（fnos-oss 接受）。
    sign_host: bool = True

    @property
    def base(self) -> str:
        """S3 API 根地址（path-style）：endpoint/bucket。"""
        return f"{self.endpoint.rstrip('/')}/{self.bucket.strip('/')}"

    @property
    def public_root(self) -> str:
        """对象公网前缀：配置了 public_base 就用它，否则回退到 endpoint/bucket。"""
        base = (self.public_base or "").strip().rstrip("/")
        return base or self.base

    def key_of(self, rel: str) -> str:
        """把站内相对路径 /uploads/... 换成对象 key（uploads/...）。"""
        rel = str(rel or "").lstrip("/")
        prefix = self.prefix.strip("/")
        if prefix and not rel.startswith(prefix + "/"):
            rel = f"{prefix}/{rel}"
        return rel

    def url_of(self, rel: str) -> str:
        """把站内相对路径换成公网 URL（与 key 一一对应，回写时可直接反解）。"""
        return f"{self.public_root}/{_encode_path(self.key_of(rel))}"

    def key_to_rel(self, key: str) -> str:
        """对象 key 换回站内相对路径（key 已包含配置前缀，直接补前导斜杠）。"""
        return "/" + str(key or "").lstrip("/")


def _auth_headers(cfg: S3Config, method: str, path: str, body: bytes,
                  content_type: str = "") -> dict[str, str]:
    """构造 SigV4 请求头；path 为已编码的完整路径（含 bucket/key）。"""
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = amz_date[:8]
    host = urlsplit(cfg.endpoint).netloc
    payload_hash = _sha256(body)

    signed = {
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if cfg.sign_host:
        signed["host"] = host
    if content_type:
        signed["content-type"] = content_type

    names = sorted(signed)
    signed_headers = ";".join(names)
    canonical_headers = "".join(f"{name}:{signed[name].strip()}\n" for name in names)
    canonical_request = "\n".join(
        [method, path, "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{date}/{cfg.region}/s3/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, _sha256(canonical_request.encode("utf-8"))]
    )
    signature = hmac.new(
        _signing_key(cfg.secret_key, date, cfg.region),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = dict(signed)
    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={cfg.access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return headers


def _request(cfg: S3Config, method: str, rel: str, body: bytes = b"",
             content_type: str = "", anonymous: bool = False) -> requests.Response:
    key = cfg.key_of(rel)
    path = _encode_path(f"/{cfg.bucket.strip('/')}/{key}")
    url = f"{cfg.endpoint.rstrip('/')}{path}"
    headers = {} if anonymous else _auth_headers(cfg, method, path, body, content_type)
    # 注意：content-type 已经由 _auth_headers 放进 headers（小写键，参与签名）。
    # 这里不能再加一个大写键，否则会发出两个 Content-Type，
    # 服务端把两个值拼起来算签名，必然 SignatureDoesNotMatch。
    try:
        return requests.request(
            method, url, data=body if method in {"PUT", "POST"} else None,
            headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    except requests.RequestException as exc:
        raise S3Error("无法连接对象存储", 0, str(exc)) from exc


def put(cfg: S3Config, rel: str, data: bytes, content_type: str = "") -> None:
    resp = _request(cfg, "PUT", rel, data, content_type)
    if resp.status_code not in (200, 201):
        raise S3Error("上传失败", resp.status_code, resp.text)


def delete(cfg: S3Config, rel: str) -> None:
    resp = _request(cfg, "DELETE", rel)
    if resp.status_code not in (200, 204, 404):
        raise S3Error("删除对象失败", resp.status_code, resp.text)


def head(cfg: S3Config, rel: str) -> bool:
    resp = _request(cfg, "HEAD", rel)
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    raise S3Error("读取对象信息失败", resp.status_code, resp.text)


def public_get(cfg: S3Config, rel: str) -> bool:
    """不带签名读取对象，用来验证桶是否为 public-read。"""
    resp = _request(cfg, "GET", rel, anonymous=True)
    return resp.status_code == 200


def healthcheck(cfg: S3Config) -> dict:
    """上传一个探针对象 → 匿名读取 → 删除，返回各步骤结果。

    匿名读取失败通常意味着桶策略还是 private；此时上传虽然成功，
    但文章里的图片会 403，所以必须把它当成配置错误提示出来。

    如果标准签名被拒绝，会自动用「不签 host」重试一次：这通常说明
    请求经过了反向代理、且代理改写了 Host 头。
    """
    from dataclasses import replace

    payload = f"infowe oss healthcheck {datetime.now().isoformat(timespec='seconds')}".encode()
    sign_host = cfg.sign_host
    try:
        put(cfg, HEALTH_KEY, payload, "text/plain; charset=utf-8")
    except S3Error as exc:
        if exc.code == "SignatureDoesNotMatch" and cfg.sign_host:
            cfg = replace(cfg, sign_host=False)
            put(cfg, HEALTH_KEY, payload, "text/plain; charset=utf-8")
            sign_host = False
        else:
            raise
    try:
        anonymous_ok = public_get(cfg, HEALTH_KEY)
    finally:
        try:
            delete(cfg, HEALTH_KEY)
        except S3Error:
            pass
    return {"upload": True, "public_read": anonymous_ok, "sign_host": sign_host}
