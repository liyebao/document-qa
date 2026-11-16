"""为已有片段补建 BM25 倒排词表（chunk_terms 与 token_count）。

用法（在 backend 目录执行，迁移 0005 之后运行）：
    .\\.venv\\Scripts\\python scripts\\rebuild_terms.py
"""
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.chunk import Chunk  # noqa: E402
from app.models.chunk_term import ChunkTerm  # noqa: E402
from app.services.retrieval.tokenizer import tokenize  # noqa: E402

_BATCH = 200


def main() -> None:
    db = SessionLocal()
    total = 0
    last_id = None
    try:
        while True:
            stmt = select(Chunk).order_by(Chunk.id).limit(_BATCH)
            if last_id is not None:
                stmt = stmt.where(Chunk.id > last_id)
            chunks = list(db.scalars(stmt).all())
            if not chunks:
                break

            for chunk in chunks:
                terms = Counter(tokenize(chunk.search_text or chunk.text))
                chunk.token_count = sum(terms.values())
                db.execute(delete(ChunkTerm).where(ChunkTerm.chunk_id == chunk.id))
                db.add_all(
                    [
                        ChunkTerm(chunk_id=chunk.id, term=term, tf=count)
                        for term, count in terms.items()
                    ]
                )

            db.commit()
            last_id = chunks[-1].id
            total += len(chunks)
            print(f"已重建 {total} 个片段的词表", flush=True)
    finally:
        db.close()

    print(f"完成：共处理 {total} 个片段")


if __name__ == "__main__":
    main()
