"""按当前解析器重新入库已有文档。

解析规则升级后（例如修复了标题误判导致正文丢失），已有片段仍是旧结果，
重建索引只会重算向量、不会重新解析原文件。这个脚本对指定资料集或单份文档
重新执行「解析 → 切片 → 向量化 → 入库」，文档 ID 与引用快照保持不变。

用法（在 backend 目录执行）：
    .\\.venv\\Scripts\\python scripts\\reingest_documents.py --collection <资料集 UUID>
    .\\.venv\\Scripts\\python scripts\\reingest_documents.py --document <文档 UUID>

脚本会删除并重建每份文档的片段；历史消息里的引用快照仍在，但片段级链接
（citations.chunk_id）会因外键置空而断开，需要在意的资料集请先备份数据库。
"""
import argparse
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.document import DOCUMENT_STATUS_READY, Document  # noqa: E402
from app.services import ingestion  # noqa: E402


def _ready_documents(collection_id: uuid.UUID) -> list[Document]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Document)
                .where(
                    Document.collection_id == collection_id,
                    Document.status == DOCUMENT_STATUS_READY,
                    Document.deleted_at.is_(None),
                    Document.is_current.is_(True),
                )
                .order_by(Document.created_at)
            ).all()
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="按当前解析器重新入库已有文档")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--collection", help="资料集 UUID，重新处理其下全部可用文档")
    target.add_argument("--document", help="单份文档 UUID")
    args = parser.parse_args()

    if args.document:
        documents = []
        with SessionLocal() as db:
            document = db.get(Document, uuid.UUID(args.document))
            if document is None:
                raise SystemExit("文档不存在")
            documents = [document]
    else:
        documents = _ready_documents(uuid.UUID(args.collection))
    if not documents:
        raise SystemExit("没有可重新处理的文档")

    failed = 0
    for document in documents:
        try:
            ingestion.run_ingestion(document.id)
        except Exception as exc:  # noqa: BLE001  单份失败不阻断其余文档
            failed += 1
            print(f"失败 {document.filename}：{exc}")
            continue
        print(f"完成 {document.filename}")
    print(f"共 {len(documents)} 份，失败 {failed} 份")


if __name__ == "__main__":
    main()
