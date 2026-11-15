"""对象存储插件后台路由：配置、连通性测试、存量迁移、地址回写。"""

from __future__ import annotations

from flask import jsonify, redirect, render_template, request, url_for

from services import auth
from services import plugins as plugins_service

from . import s3, storage

KEY = "oss"

# 把 S3 的英文错误码翻成可操作的中文提示
_FRIENDLY_CODE = {
    "SignatureDoesNotMatch": (
        "Access Key 与 Secret Key 不匹配。服务端认得这个 Access Key，但用保存的 Secret "
        "算出的签名对不上——通常是 Secret 复制不完整，或者重新生成密钥后只更新了其中一个。"
        "请到 fnos-oss 管理端「访问密钥」重新生成一对，两个值一起粘贴保存后再测试。"
    ),
    "InvalidAccessKeyId": "Access Key 不存在或已被停用，请到 fnos-oss 管理端确认密钥状态。",
    "NoSuchBucket": "桶不存在，请先在 fnos-oss 管理端创建同名桶。",
    "AccessDenied": "密钥没有该桶的权限，或桶策略不允许该操作。",
    "RequestTimeTooSkewed": "服务器时间偏差过大，请校准 NAS 时间后重试。",
    "InvalidBucketName": "桶名不合法，只能使用小写字母、数字和连字符。",
}


def _friendly(exc: "s3.S3Error") -> str:
    text = _FRIENDLY_CODE.get(exc.code)
    if text:
        return f"{text}（{exc.code}）"
    return str(exc)


def _mask(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    return "****" + value[-4:] if len(value) > 4 else "****"


def _form_config() -> dict:
    """从表单收集配置；保存与测试共用，避免两套字段名。"""
    return {
        "endpoint": (request.form.get("endpoint") or "").strip().rstrip("/"),
        "bucket": (request.form.get("bucket") or "").strip().strip("/"),
        "access_key": (request.form.get("access_key") or "").strip(),
        "secret_key": (request.form.get("secret_key") or "").strip(),
        "region": (request.form.get("region") or "us-east-1").strip() or "us-east-1",
        "public_base": (request.form.get("public_base") or "").strip().rstrip("/"),
        "prefix": (request.form.get("prefix") or "uploads").strip().strip("/") or "uploads",
    }


def register(app) -> None:
    prefix = app.config.get("ADMIN_PREFIX", "/admin")

    @auth.admin_required
    def oss_config():
        cfg = storage.raw_config()
        current = storage.get_cfg()
        return render_template(
            "oss/config.html",
            cfg=cfg,
            enabled=plugins_service.enabled(KEY),
            configured=current is not None,
            secret_mask=_mask(cfg.get("secret_key")),
            public_root=current.public_root if current else "",
            local_files=len(storage.list_local_files()),
            local_refs=storage.count_local_refs(),
            remote_refs=storage.count_remote_refs(),
            migrated_at=str(cfg.get("migrated_at") or ""),
        )

    @auth.admin_required
    def oss_save():
        old = storage.raw_config()
        data = _form_config()
        # 密钥留空表示「不修改」，避免后台回显掩码时把真密钥覆盖成 ****
        if not data["secret_key"]:
            if old.get("access_key") and old["access_key"] != data["access_key"]:
                # Access Key 换了但 Secret 留空，几乎必然配成「新 AK + 旧 SK」，
                # 服务端只会回 SignatureDoesNotMatch，很难排查，这里直接拦住。
                flash("Access Key 已变更，必须同时重新填写 Secret Key", "error")
                return redirect(url_for("admin_plugin_oss_config"))
            data["secret_key"] = str(old.get("secret_key") or "")
        if not data["access_key"]:
            data["access_key"] = str(old.get("access_key") or "")
        # 公网基址改过之后，停用回写要能认得出旧地址
        if old.get("public_base") and old["public_base"] != data["public_base"]:
            data["public_base_prev"] = old["public_base"]
        elif old.get("public_base_prev"):
            data["public_base_prev"] = old["public_base_prev"]
        # 继承自动探测出的签名模式，避免保存配置时把它丢掉
        if old.get("sign_host") is not None:
            data["sign_host"] = old["sign_host"]
        data["migrated_at"] = str(old.get("migrated_at") or "")
        plugins_service.save_config(KEY, data)
        return redirect(url_for("admin_plugin_oss_config"))

    @auth.admin_required
    def oss_test():
        data = _form_config()
        if not data["secret_key"]:
            data["secret_key"] = str(storage.raw_config().get("secret_key") or "")
        if not data["access_key"]:
            data["access_key"] = str(storage.raw_config().get("access_key") or "")
        if not (data["endpoint"] and data["bucket"] and data["access_key"] and data["secret_key"]):
            return jsonify({"ok": False, "error": "Endpoint / 桶 / 密钥填写不完整"}), 400
        cfg = s3.S3Config(
            endpoint=data["endpoint"],
            bucket=data["bucket"],
            access_key=data["access_key"],
            secret_key=data["secret_key"],
            region=data["region"],
            public_base=data["public_base"],
            prefix=data["prefix"],
        )
        try:
            result = s3.healthcheck(cfg)
        except s3.S3Error as exc:
            return jsonify({"ok": False, "error": _friendly(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"测试失败：{exc}"}), 400
        if not result["public_read"]:
            return jsonify({
                "ok": False,
                "error": "上传成功，但匿名读取被拒绝：请把桶策略设为 public-read，否则文章里的图片会 403",
            }), 400
        message = "上传、匿名读取、删除三步均通过"
        if not result["sign_host"]:
            # 记住探测结果：之后的上传直接走兼容模式，不再先失败一次
            old = storage.raw_config()
            if old.get("sign_host") is not False:
                old["sign_host"] = False
                plugins_service.save_config(KEY, old)
            message += "；检测到反向代理改写了 Host，已自动切换为兼容签名模式"
        public_base = data["public_base"].rstrip("/")
        if public_base and not public_base.endswith("/" + data["bucket"]):
            message += f"；注意：公网基址似乎缺少桶名，正常应为 {public_base}/{data['bucket']}"
        return jsonify({"ok": True, "message": message})

    @auth.admin_required
    def oss_migrate():
        if not plugins_service.enabled(KEY):
            return jsonify({"error": "请先启用对象存储插件"}), 400
        if storage.get_cfg() is None:
            return jsonify({"error": "配置不完整：请先填写 Endpoint、桶与密钥"}), 400
        try:
            offset = max(0, int(request.form.get("offset") or 0))
            limit = max(1, min(50, int(request.form.get("limit") or 10)))
        except (TypeError, ValueError):
            offset, limit = 0, 10
        return jsonify(storage.migrate_batch(offset, limit))

    @auth.admin_required
    def oss_rewrite():
        direction = (request.form.get("direction") or "remote").strip().lower()
        if direction not in {"remote", "local"}:
            return jsonify({"error": "direction 只能是 remote 或 local"}), 400
        if direction == "remote" and not plugins_service.enabled(KEY):
            return jsonify({"error": "请先启用对象存储插件"}), 400
        stats = storage.rewrite_db(direction)
        if direction == "remote":
            storage.mark_migrated()
        return jsonify({"ok": True, **stats})

    @auth.admin_required
    def oss_status():
        cfg = storage.raw_config()
        return jsonify({
            "enabled": plugins_service.enabled(KEY),
            "configured": storage.get_cfg() is not None,
            "local_files": len(storage.list_local_files()),
            "local_refs": storage.count_local_refs(),
            "remote_refs": storage.count_remote_refs(),
            "migrated_at": str(cfg.get("migrated_at") or ""),
        })

    app.add_url_rule(prefix + "/plugins/oss", "admin_plugin_oss_config", oss_config, methods=["GET"])
    app.add_url_rule(prefix + "/plugins/oss/save", "admin_plugin_oss_save", oss_save, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/oss/test", "admin_plugin_oss_test", oss_test, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/oss/migrate", "admin_plugin_oss_migrate", oss_migrate, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/oss/rewrite", "admin_plugin_oss_rewrite", oss_rewrite, methods=["POST"])
    app.add_url_rule(prefix + "/plugins/oss/status", "admin_plugin_oss_status", oss_status, methods=["GET"])
