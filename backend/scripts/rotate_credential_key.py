"""把用户模型 Key 从旧主密钥迁移到新主密钥。

用法（在 backend 目录执行，先备份数据库）：
    .\\.venv\\Scripts\\python scripts\\rotate_credential_key.py --new-key "<base64-32-bytes>"

轮换完成后，把 `.env` 中的 CREDENTIAL_ENCRYPTION_KEY 改为新值，
并把 CREDENTIAL_ENCRYPTION_KEY_VERSION 改为脚本打印的新版本，然后重启后端。
"""
import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.secrets import encrypt_secret, reencrypt_secret  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.model_provider_config import ModelProviderConfig  # noqa: E402


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="轮换用户模型 API Key 的加密主密钥")
    parser.add_argument("--new-key", required=True, help="新的 base64 编码 32 字节密钥")
    parser.add_argument(
        "--new-version",
        type=int,
        default=settings.credential_key_version + 1,
        help="新密钥版本号，默认当前版本 + 1",
    )
    parser.add_argument(
        "--old-key",
        default=settings.credential_encryption_key,
        help="旧主密钥，默认取当前环境配置",
    )
    parser.add_argument(
        "--old-version",
        type=int,
        default=settings.credential_key_version,
        help="旧密钥版本号，默认取当前环境配置",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = parser.parse_args()

    if args.new_version == args.old_version:
        raise SystemExit("新版本号必须与旧版本号不同，否则无法区分密钥")

    # 即使没有任何配置，也先验证新密钥格式。
    encrypt_secret("key-rotation-probe", key=args.new_key, key_version=args.new_version)

    db = SessionLocal()
    try:
        configs = list(
            db.scalars(
                select(ModelProviderConfig).where(
                    ModelProviderConfig.key_version == args.old_version
                )
            ).all()
        )
        other_versions = db.scalar(
            select(func.count())
            .select_from(ModelProviderConfig)
            .where(ModelProviderConfig.key_version != args.old_version)
        )
        print(f"待轮换配置：{len(configs)} 条；其他版本配置：{other_versions or 0} 条")
        if args.dry_run:
            print("dry-run 模式，未写库")
            return
        for config in configs:
            ciphertext, version = reencrypt_secret(
                config.api_key_ciphertext,
                old_key=args.old_key,
                old_version=args.old_version,
                new_key=args.new_key,
                new_version=args.new_version,
            )
            config.api_key_ciphertext = ciphertext
            config.key_version = version
        db.commit()
        print(
            f"已轮换 {len(configs)} 条配置到版本 {args.new_version}；"
            "请更新 .env 后重启后端"
        )
        if other_versions:
            print("警告：仍有其他版本的配置，请确认是否需要继续轮换")
    finally:
        db.close()


if __name__ == "__main__":
    main()
