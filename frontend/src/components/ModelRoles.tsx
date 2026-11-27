import type { EffectiveModel, ModelProviderSettings } from "../api/types";

interface RoleOption {
  id: string;
  label: string;
}

interface RoleRowProps {
  label: string;
  hint: string;
  role: "embedding" | "chat";
  effective: EffectiveModel | null;
  options: RoleOption[];
  busy: boolean;
  onRoleChange: (role: "embedding" | "chat", configId: string) => void;
}

function RoleRow({
  label,
  hint,
  role,
  effective,
  options,
  busy,
  onRoleChange,
}: RoleRowProps) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-ink-line bg-paper-card p-4">
      <div className="min-w-0">
        <p className="text-xs font-semibold text-ink-mute">{label}</p>
        <p className="mt-1 truncate text-sm font-semibold text-ink">
          {effective ? `${effective.provider_label} · ${effective.model}` : "未配置"}
        </p>
        <p className="mt-1 text-xs text-ink-mute">{hint}</p>
      </div>
      {options.length > 0 && (
        <select
          value={effective?.config_id ?? ""}
          onChange={(event) => onRoleChange(role, event.target.value)}
          disabled={busy}
          className="field-select w-full sm:max-w-xs"
          aria-label={`更换${label}`}
        >
          {!effective && <option value="">选择模型</option>}
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

interface Props {
  settings: ModelProviderSettings;
  busy: boolean;
  onRoleChange: (role: "embedding" | "chat", configId: string) => void;
}

export function ModelRoles({ settings, busy, onRoleChange }: Props) {
  const providerLabel = (key: string) =>
    settings.providers.find((item) => item.key === key)?.label ?? key;
  const embeddingOptions = settings.configs
    .filter((item) => item.embedding_model)
    .map((item) => ({
      id: item.id,
      label: `${providerLabel(item.provider_key)} · ${item.embedding_model}`,
    }));
  const chatOptions = settings.configs
    .filter((item) => item.chat_model)
    .map((item) => ({
      id: item.id,
      label: `${providerLabel(item.provider_key)} · ${item.chat_model}`,
    }));

  return (
    <section className="mt-7">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-ink">当前使用</h2>
          <p className="mt-1 text-sm text-ink-mute">检索和回答可以分别使用不同模型</p>
        </div>
        <span className="rounded-full bg-paper-card px-3 py-1.5 text-xs text-ink-mute shadow-sm">
          {settings.effective_rerank
            ? `重排：${settings.effective_rerank.model}`
            : "重排未启用"}
        </span>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <RoleRow
          label="检索"
          hint="用于把文档和问题转成向量，切换后需要在资料集页面重建索引"
          role="embedding"
          effective={settings.effective_embedding}
          options={embeddingOptions}
          busy={busy}
          onRoleChange={onRoleChange}
        />
        <RoleRow
          label="回答"
          hint="用于生成最终回答，可以和检索使用不同服务商"
          role="chat"
          effective={settings.effective_chat}
          options={chatOptions}
          busy={busy}
          onRoleChange={onRoleChange}
        />
      </div>

      {(!settings.effective_embedding || !settings.effective_chat) && (
        <p className="mt-3 rounded-xl border border-ochre/30 bg-ochre-wash px-4 py-3 text-sm leading-relaxed text-ochre">
          {!settings.effective_embedding && "缺少检索模型，无法处理文件和提问。"}
          {!settings.effective_chat && "缺少回答模型，无法生成回答。"}
          请在下方配置一个服务商。
        </p>
      )}
    </section>
  );
}
