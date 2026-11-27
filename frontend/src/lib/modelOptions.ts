/** 下拉选项：把"本地已安装"排到前面，未下载的保留在原地但标注出来。 */
export interface ModelOption {
  value: string;
  installed: boolean;
  recommended: boolean;
}

/**
 * Ollama 的 /api/tags 返回 `bge-m3:latest`，而模型清单里写的是 `bge-m3`。
 * 比较前统一去掉 `:latest`，否则同一个模型会被判成"未下载"。
 */
export function normalizeModelName(name: string): string {
  return name.endsWith(":latest") ? name.slice(0, -":latest".length) : name;
}

/**
 * 只按推荐清单出选项，标记哪些本地已下载。
 *
 * 不把清单外的已安装模型塞进下拉：Ollama 的 tags 不区分用途，
 * 混进来会把聊天模型（如 qwen3:4b）列成"检索模型"，选了必然失败。
 * 这类模型留给"自定义模型"手动填写。
 */
export function buildModelOptions(
  catalog: string[],
  installed: string[] | null,
): ModelOption[] {
  if (!installed) {
    return catalog.map((value, index) => ({
      value,
      installed: false,
      recommended: index === 0,
    }));
  }
  const present = new Set(installed.map(normalizeModelName));
  const local = catalog.filter((model) => present.has(normalizeModelName(model)));
  const missing = catalog.filter((model) => !present.has(normalizeModelName(model)));
  return [
    ...local.map((value) => ({ value, installed: true, recommended: false })),
    ...missing.map((value) => ({ value, installed: false, recommended: false })),
  ];
}

/** 本地已下载、但不在任何推荐清单里的模型数量；这些需要手动输入模型名。 */
export function countUnlistedModels(
  installed: string[] | null,
  catalogs: string[][],
): number {
  if (!installed || installed.length === 0) {
    return 0;
  }
  const known = new Set(catalogs.flat().map(normalizeModelName));
  return installed.filter((model) => !known.has(normalizeModelName(model))).length;
}
