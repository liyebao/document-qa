from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401  确保模型注册到 Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 表达式索引无法由 SQLAlchemy 元数据完整描述，迁移中手工创建；
# 关闭 autogenerate 对比，避免 alembic check 误报需要删除。
_IGNORED_INDEX_PREFIXES = (
    "ix_chunks_embedding_",
    "ix_chunks_search_text_trgm",
)


def include_object(object_, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    if type_ == "index" and name and name.startswith(_IGNORED_INDEX_PREFIXES):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
