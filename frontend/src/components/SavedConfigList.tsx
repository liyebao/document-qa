import type { ModelProviderSettings } from "../api/types";

const STATUS_META: Record<string, { label: string; dot: string; text: string }> = {
  ok: { label: "连接正常", dot: "bg-jade", text: "text-jade" },
  error: { label: "连接失败", dot: "bg-vermilion", text: "text-vermilion" },
  configured: { label: "未测试", dot: "bg-ochre", text: "text-ochre" },
  // 主密钥轮换后旧密文解不开，需要用户重新填写 API Key
  key_unreadable: {
    label: "密钥不可读，请重新填写",
    dot: "bg-vermilion",
    text: "text-vermilion",
  },
};

interface Props {
  settings: ModelProviderSettings;
  testingId: string | null;
  onTest: (configId: string) => void;
  onDelete: (configId: string, providerLabel: string) => void;
}

export function SavedConfigList({ settings, testingId, onTest, onDelete }: Props) {
  const activeIds = new Set(
    [
      settings.effective_embedding?.config_id,
      settings.effective_chat?.config_id,
      settings.effective_rerank?.config_id,
    ].filter(Boolean),
  );

  return (
    <section className="surface mt-6 p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">已保存的服务商</h2>
          <p className="mt-1 text-sm text-ink-mute">管理密钥、查看状态或移除配置</p>
        </div>
        <span className="rounded-full bg-paper px-3 py-1.5 text-xs text-ink-mute">
          {settings.configs.length} 个
        </span>
      </div>

      <p className="mt-3 text-xs text-ink-mute">
        修改配置：在上方选择服务商，已保存的模型会自动带出。
      </p>

      {settings.configs.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {settings.configs.map((config) => {
            const provider = settings.providers.find(
              (item) => item.key === config.provider_key,
            );
            const status = STATUS_META[config.status] ?? {
              label: config.status,
              dot: "bg-ink-mute",
              text: "text-ink-mute",
            };
            return (
              <li
                key={config.id}
                className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-xl border border-ink-line p-4 transition duration-200 hover:border-accent/30 hover:bg-paper/70"
              >
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
                    {provider?.label ?? config.provider_key}
                    <span className="rounded-md bg-paper px-2 py-1 text-xs text-ink-mute">
                      {config.key_masked}
                    </span>
                    {activeIds.has(config.id) && (
                      <span className="rounded-full bg-accent-wash px-2.5 py-1 text-xs font-medium text-accent">
                        使用中
                      </span>
                    )}
                    <span
                      className={`inline-flex items-center gap-1.5 text-xs font-medium ${status.text}`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${status.dot}`}
                        aria-hidden="true"
                      />
                      {status.label}
                    </span>
                  </p>
                  <p className="mt-2 text-xs text-ink-mute">
                    {config.embedding_model
                      ? `检索 ${config.embedding_model}`
                      : "不用于检索"}
                    {" · "}
                    {config.chat_model ? `回答 ${config.chat_model}` : "不用于回答"}
                    {config.rerank_model ? ` · 重排 ${config.rerank_model}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <button
                    type="button"
                    onClick={() => onTest(config.id)}
                    disabled={testingId === config.id}
                    className="row-action disabled:opacity-50"
                  >
                    {testingId === config.id ? "测试中…" : "测试"}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onDelete(config.id, provider?.label ?? config.provider_key)
                    }
                    className="row-action hover:text-vermilion"
                  >
                    删除
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="py-8 text-[13px] text-ink-soft">
          还没有保存的模型服务，先在上方选择一个服务商并填入 API Key。
        </p>
      )}
    </section>
  );
}
