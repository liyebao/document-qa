import type { ChangeEvent } from "react";
import { documentFileUrl } from "../api/documents";
import type { DocumentItem } from "../api/types";
import { FileStatus } from "./FileStatus";
import { SourceImport } from "./SourceImport";

interface Props {
  documents: DocumentItem[];
  uploading: boolean;
  importing: boolean;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onCreateText: (title: string, content: string) => Promise<void>;
  onImportUrl: (url: string) => Promise<void>;
  onReplace: (document: DocumentItem, event: ChangeEvent<HTMLInputElement>) => void;
  onToggle: (document: DocumentItem) => void;
  onRetry: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
}

export function DocumentSection({
  documents,
  uploading,
  importing,
  onUpload,
  onCreateText,
  onImportUrl,
  onReplace,
  onToggle,
  onRetry,
  onDelete,
}: Props) {
  return (
    <section className="surface p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">文件</h2>
          <p className="mt-1 text-sm text-ink-mute">导入资料并查看处理状态</p>
        </div>
        <label className="btn-primary min-h-9 cursor-pointer px-3 text-xs">
          {uploading ? "上传中…" : "＋ 添加文件"}
          <input
            type="file"
            multiple
            accept=".pdf,.docx,.md,.markdown,.txt,.pptx,.xlsx"
            onChange={onUpload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      <p className="mt-3 text-xs leading-5 text-ink-mute">
        支持 PDF、DOCX、Markdown、TXT、PPTX、XLSX，单份不超过 100
        MB；内容重复的文件会被拒绝。
      </p>

      <SourceImport
        busy={importing}
        onCreateText={onCreateText}
        onImportUrl={onImportUrl}
      />

      {documents.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-ink-line bg-paper/70 px-5 py-12 text-center">
          <div
            className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-white text-lg font-bold text-accent shadow-sm"
            aria-hidden="true"
          >
            ＋
          </div>
          <p className="mt-3 text-sm font-semibold text-ink">还没有资料</p>
          <p className="mt-2 text-sm text-ink-soft">
            还没有文件。上传后系统会解析、切片并建立检索索引。
          </p>
        </div>
      ) : (
        <ul className="mt-4 space-y-2">
          {documents.map((document) => (
            <li
              key={document.id}
              className="group flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-ink-line p-4 transition duration-200 hover:border-accent/30 hover:bg-paper/70"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">
                  {document.filename}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-mute">
                  <FileStatus
                    status={document.status}
                    failureReason={document.failure_reason}
                  />
                  <span>版本 {document.version}</span>
                  {!document.is_enabled && <span>已停用</span>}
                  {document.status === "failed" && document.failure_reason && (
                    <span className="text-vermilion">{document.failure_reason}</span>
                  )}
                </div>
              </div>

              <div className="flex w-full flex-wrap items-center gap-1.5 border-t border-ink-line pt-2 sm:w-auto sm:justify-end sm:border-0 sm:pt-0">
                {document.status === "failed" && (
                  <button
                    type="button"
                    onClick={() => onRetry(document)}
                    className="row-action hover:text-ochre"
                  >
                    重试
                  </button>
                )}
                <a
                  href={documentFileUrl(document.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="row-action"
                  title={document.format === "docx" ? "下载原文件" : "查看原文件"}
                >
                  {document.format === "docx" ? "下载" : "查看"}
                </a>
                <button
                  type="button"
                  onClick={() => onToggle(document)}
                  className="row-action"
                >
                  {document.is_enabled ? "停用" : "启用"}
                </button>
                <label className="cursor-pointer text-[11px] text-ink-mute transition hover:text-vermilion">
                  替换
                  <input
                    type="file"
                    accept=".pdf,.docx,.md,.markdown,.txt,.pptx,.xlsx"
                    onChange={(event) => onReplace(document, event)}
                    className="hidden"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => onDelete(document)}
                  className="row-action hover:text-vermilion"
                >
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
