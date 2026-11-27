import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createConversation,
  getCollection,
  listConversations,
  reindexCollection,
  renameCollection,
} from "../api/collections";
import { errorMessage } from "../api/client";
import { deleteConversation } from "../api/conversations";
import {
  createTextDocument,
  deleteDocument,
  importUrlDocument,
  listDocuments,
  replaceDocument,
  retryDocument,
  setDocumentEnabled,
  uploadDocument,
} from "../api/documents";
import type { CollectionOut, ConversationSummary, DocumentItem } from "../api/types";
import { notifyConversationsChanged } from "../app/recent";
import { CollectionHeader } from "../components/CollectionHeader";
import { ConversationSection } from "../components/ConversationSection";
import { DocumentSection } from "../components/DocumentSection";

export function CollectionPage() {
  const params = useParams<{ collectionId: string }>();
  const collectionId = params.collectionId ?? "";
  const navigate = useNavigate();

  const [collection, setCollection] = useState<CollectionOut | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    if (!collectionId) {
      return;
    }
    setLoading(true);
    try {
      const [collectionData, documentData, conversationData] = await Promise.all([
        getCollection(collectionId),
        listDocuments(collectionId),
        listConversations(collectionId),
      ]);
      setCollection(collectionData);
      setDocuments(documentData);
      setConversations(conversationData);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [collectionId]);

  const refreshDocuments = useCallback(async () => {
    if (!collectionId) {
      return;
    }
    try {
      setDocuments(await listDocuments(collectionId));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [collectionId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const hasPending = documents.some(
    (item) => item.status === "processing" || item.status === "uploading",
  );

  useEffect(() => {
    if (!hasPending || !collectionId) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshDocuments();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [hasPending, collectionId, refreshDocuments]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }
    setUploading(true);
    setError(null);
    const queue = Array.from(files);
    // 保存失败原因：只显示文件名的话，415/409/超时 在界面上完全看不出来。
    const failures: Array<{ file: File; reason: string }> = [];
    // 限并发 3 个：既比串行快，又不会一次把上传限流打满。
    const worker = async () => {
      while (queue.length > 0) {
        const file = queue.shift();
        if (!file) {
          return;
        }
        try {
          await uploadDocument(collectionId, file);
        } catch (err) {
          failures.push({ file, reason: errorMessage(err) });
        }
      }
    };
    try {
      await Promise.all(
        Array.from({ length: Math.min(3, queue.length) }, () => worker()),
      );
      await refreshDocuments();
      if (failures.length > 0) {
        setError(
          `${failures.length} 个文件上传失败：${failures
            .map((item) => `${item.file.name}（${item.reason}）`)
            .join("、")}`,
        );
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function handleCreateText(title: string, content: string) {
    setImporting(true);
    setError(null);
    try {
      await createTextDocument(collectionId, title, content);
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err));
      throw err;
    } finally {
      setImporting(false);
    }
  }

  async function handleImportUrl(url: string) {
    setImporting(true);
    setError(null);
    try {
      await importUrlDocument(collectionId, url);
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err));
      throw err;
    } finally {
      setImporting(false);
    }
  }

  async function handleReplace(
    document: DocumentItem,
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    try {
      await replaceDocument(document.id, file);
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleToggle(document: DocumentItem) {
    try {
      await setDocumentEnabled(document.id, !document.is_enabled);
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleRetry(document: DocumentItem) {
    try {
      await retryDocument(document.id);
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDeleteDocument(document: DocumentItem) {
    if (!window.confirm(`确认删除文件“${document.filename}”？删除后不再参与检索。`)) {
      return;
    }
    try {
      await deleteDocument(document.id);
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleCreateConversation() {
    try {
      const conversation = await createConversation(collectionId);
      notifyConversationsChanged();
      navigate(`/conversations/${conversation.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleRenameCollection() {
    if (!collection) {
      return;
    }
    const nextName = window.prompt("新的资料集名称", collection.name);
    if (!nextName || !nextName.trim()) {
      return;
    }
    try {
      await renameCollection(collection.id, nextName.trim());
      await loadAll();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleReindex() {
    if (
      !window.confirm(
        "重建索引会重新调用 Embedding 服务，可能产生费用，耗时取决于片段数量。确认继续？",
      )
    ) {
      return;
    }
    setReindexing(true);
    setError(null);
    setNotice(null);
    try {
      const result = await reindexCollection(collectionId);
      setCollection(result);
      setNotice(
        `索引已重建：${result.chunk_count} 个片段，当前版本 v${result.index_version}。`,
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setReindexing(false);
    }
  }

  async function handleDeleteConversation(conversation: ConversationSummary) {
    if (!window.confirm(`确认删除会话“${conversation.title}”？`)) {
      return;
    }
    try {
      await deleteConversation(conversation.id);
      setConversations(await listConversations(collectionId));
      notifyConversationsChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (loading) {
    return <p className="py-10 text-xs text-ink-mute">读取资料集…</p>;
  }

  if (!collection) {
    return (
      <div className="space-y-4">
        <p className="border-l-2 border-vermilion bg-vermilion-wash px-3 py-2 text-xs text-vermilion">
          {error ?? "资料集不存在"}
        </p>
        <Link to="/" className="link-quiet text-ui-sm">
          ← 返回资料集列表
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 animate-rise">
      <CollectionHeader
        collection={collection}
        documentCount={documents.length}
        reindexing={reindexing}
        onReindex={() => void handleReindex()}
        onRename={() => void handleRenameCollection()}
      />

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-vermilion/20 bg-vermilion-wash px-4 py-3 text-sm leading-relaxed text-vermilion"
        >
          {error}
        </p>
      )}
      {notice && (
        <p
          role="status"
          className="rounded-xl border border-jade/20 bg-jade-wash px-4 py-3 text-sm leading-relaxed text-jade"
        >
          {notice}
        </p>
      )}

      {/* 显式 minmax(0,…) 列宽：否则长文件名会把网格轨道撑宽，窄屏横向被裁掉。 */}
      <div className="grid min-w-0 grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <DocumentSection
          documents={documents}
          uploading={uploading}
          importing={importing}
          onUpload={handleUpload}
          onCreateText={handleCreateText}
          onImportUrl={handleImportUrl}
          onReplace={handleReplace}
          onToggle={handleToggle}
          onRetry={handleRetry}
          onDelete={handleDeleteDocument}
        />

        <ConversationSection
          conversations={conversations}
          onCreate={handleCreateConversation}
          onDelete={handleDeleteConversation}
        />
      </div>
    </div>
  );
}
