import { createContext, useContext } from "react";

/** 打开预览抽屉时需要的定位信息。 */
export interface PreviewRequest {
  documentId: string;
  filename: string;
  format: string;
  /** PDF 跳转页码；其它格式忽略。 */
  page?: number | null;
  /** 命中的片段，用于在文本预览里整块高亮。 */
  chunkId?: string | null;
  /** 引用原文，用于在片段内部再做一次关键词高亮。 */
  highlightText?: string | null;
  /** 形如"第 76-78 页"的位置描述，显示在标题栏。 */
  location?: string;
}

export interface PreviewContextValue {
  openPreview: (request: PreviewRequest) => void;
  closePreview: () => void;
}

/**
 * 默认值给空实现而不是抛错：组件被单独渲染（单元测试、局部复用）时不该直接崩，
 * 但预览打不开属于功能性问题，开发环境下留一条告警便于定位。
 */
const PREVIEW_FALLBACK: PreviewContextValue = {
  openPreview: () => {
    if (import.meta.env.DEV) {
      console.warn("openPreview 在 PreviewProvider 之外调用，预览不会显示");
    }
  },
  closePreview: () => {},
};

export const PreviewContext = createContext<PreviewContextValue>(PREVIEW_FALLBACK);

/**
 * 引用只带文件名，没有格式字段；按后缀推断即可决定用 iframe 还是文本预览。
 */
export function formatFromFilename(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
}

export function usePreview(): PreviewContextValue {
  return useContext(PreviewContext);
}
