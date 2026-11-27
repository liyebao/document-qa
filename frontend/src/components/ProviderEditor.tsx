import { useEffect, useState } from "react";
import { errorMessage } from "../api/client";
import {
  fetchProviderModels,
  fetchProviderSettings,
  saveProvider,
  testProvider,
  type SaveProviderPayload,
} from "../api/settings";
import type {
  ModelProviderConfig,
  ModelProviderSettings,
  ProviderInfo,
} from "../api/types";
import { buildModelOptions, countUnlistedModels } from "../lib/modelOptions";
import { NOTICE_AUTO_CLOSE_MS } from "../lib/notice";

export const CUSTOM_MODEL = "__custom__";

function resolveModel(choice: string, custom: string): string {
  return choice === CUSTOM_MODEL ? custom.trim() : choice;
}

function initialCustom(value: string, options: string[]): string {
  return value && !options.includes(value) ? value : "";
}

function initialChoice(value: string | undefined, options: string[]): string {
  if (!value) {
    return options[0] ?? "";
  }
  return options.includes(value) ? value : CUSTOM_MODEL;
}

function buildForm(settings: ModelProviderSettings, key: string) {
  const provider: ProviderInfo | undefined = settings.providers.find(
    (item) => item.key === key,
  );
  const config: ModelProviderConfig | undefined = settings.configs.find(
    (item) => item.provider_key === key,
  );
  const embeddingOptions = provider?.embedding_models ?? [];
  const chatOptions = provider?.chat_models ?? [];
  const embeddingValue = config?.embedding_model ?? embeddingOptions[0] ?? "";
  const chatValue = config?.chat_model ?? chatOptions[0] ?? "";
  return {
    embeddingChoice: initialChoice(embeddingValue, embeddingOptions),
    embeddingCustom: initialCustom(embeddingValue, embeddingOptions),
    chatChoice: initialChoice(chatValue, chatOptions),
    chatCustom: initialCustom(chatValue, chatOptions),
    rerankChoice: config?.rerank_model ?? "",
  };
}

/**
 * "测试连接"实际会先落库再测试，因此需要提前让用户知道：
 * 只要填了新 Key 或改了模型选择，按钮文案就应显示"保存并测试"。
 */
function needsSave(
  payload: SaveProviderPayload,
  existing: ModelProviderConfig | undefined,
): boolean {
  return (
    Boolean(payload.api_key) ||
    (payload.embedding_model ?? "") !== (existing?.embedding_model ?? "") ||
    (payload.chat_model ?? "") !== (existing?.chat_model ?? "") ||
    (payload.rerank_model ?? "") !== (existing?.rerank_model ?? "")
  );
}

interface Props {
  settings: ModelProviderSettings;
  onChanged: (settings: ModelProviderSettings) => void;
}

export function ProviderEditor({ settings, onChanged }: Props) {
  const initialKey =
    settings.configs[0]?.provider_key ?? settings.providers[0]?.key ?? "";
  const [providerKey, setProviderKey] = useState(initialKey);
  const initialForm = buildForm(settings, initialKey);
  const [apiKey, setApiKey] = useState("");
  const [embeddingChoice, setEmbeddingChoice] = useState(initialForm.embeddingChoice);
  const [embeddingCustom, setEmbeddingCustom] = useState(initialForm.embeddingCustom);
  const [chatChoice, setChatChoice] = useState(initialForm.chatChoice);
  const [chatCustom, setChatCustom] = useState(initialForm.chatCustom);
  const [rerankChoice, setRerankChoice] = useState(initialForm.rerankChoice);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // null 表示"没有探测结果"（云端服务商，或本地服务连不上）——此时沿用静态推荐清单。
  const [localModels, setLocalModels] = useState<string[] | null>(null);
  const [localHint, setLocalHint] = useState("");

  // 保存/测试结果自动消失，避免长期占住表单下方。
  useEffect(() => {
    if (!notice && !error) {
      return;
    }
    const timer = window.setTimeout(() => {
      setNotice(null);
      setError(null);
    }, NOTICE_AUTO_CLOSE_MS);
    return () => window.clearTimeout(timer);
  }, [notice, error]);

  const provider = settings.providers.find((item) => item.key === providerKey);
  const existing = settings.configs.find((item) => item.provider_key === providerKey);
  // 只有本地服务商（不需要 Key）才有"已下载模型"的概念。
  const needsLocalProbe = Boolean(provider && !provider.requires_api_key);

  useEffect(() => {
    if (!needsLocalProbe) {
      setLocalModels(null);
      setLocalHint("");
      return;
    }
    let cancelled = false;
    fetchProviderModels(providerKey)
      .then((result) => {
        if (cancelled) {
          return;
        }
        // 连不上本地服务时保持 null，不要显示成"一个模型都没有"。
        setLocalModels(result.reachable ? result.installed : null);
        setLocalHint(result.reachable ? "" : result.message);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setLocalModels(null);
        setLocalHint("无法读取本地模型列表，已回退到推荐清单");
      });
    return () => {
      cancelled = true;
    };
  }, [providerKey, needsLocalProbe]);

  const embeddingOptions = buildModelOptions(
    provider?.embedding_models ?? [],
    localModels,
  );
  const chatOptions = buildModelOptions(provider?.chat_models ?? [], localModels);
  const unlisted = countUnlistedModels(localModels, [
    provider?.embedding_models ?? [],
    provider?.chat_models ?? [],
  ]);

  function loadProvider(key: string) {
    const form = buildForm(settings, key);
    setProviderKey(key);
    setEmbeddingChoice(form.embeddingChoice);
    setEmbeddingCustom(form.embeddingCustom);
    setChatChoice(form.chatChoice);
    setChatCustom(form.chatCustom);
    setRerankChoice(form.rerankChoice);
    setApiKey("");
    setNotice(null);
    setError(null);
  }

  function buildPayload(): SaveProviderPayload {
    const embeddingModel = provider?.embedding_models.length
      ? resolveModel(embeddingChoice, embeddingCustom)
      : "";
    const chatModel = resolveModel(chatChoice, chatCustom);
    return {
      provider_key: providerKey,
      ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      ...(embeddingModel ? { embedding_model: embeddingModel } : {}),
      ...(chatModel ? { chat_model: chatModel } : {}),
      ...(rerankChoice
        ? { rerank_model: rerankChoice }
        : existing?.rerank_model
          ? { rerank_model: "" }
          : {}),
    };
  }

  async function handleSave() {
    if (!provider) {
      setError("请选择服务商");
      return;
    }
    if (!existing && provider.requires_api_key && !apiKey.trim()) {
      setError("首次配置需要填写 API Key");
      return;
    }
    if (provider.embedding_models.length > 0 && embeddingChoice === CUSTOM_MODEL) {
      if (!embeddingCustom.trim()) {
        setError("请输入自定义检索模型名");
        return;
      }
    }
    if (chatChoice === CUSTOM_MODEL && !chatCustom.trim()) {
      setError("请输入自定义回答模型名");
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await saveProvider(buildPayload());
      setApiKey("");
      onChanged(await fetchProviderSettings());
      setNotice(
        existing ? "配置已更新，当前使用的模型没有改变" : "配置已保存，可以开始提问",
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleTest() {
    if (!provider) {
      return;
    }
    setTesting(true);
    setError(null);
    setNotice(null);
    const payload = buildPayload();
    // 下拉改了但没点保存时，测试的应是当前选择而不是数据库里的旧模型。
    const pendingSave = needsSave(payload, existing);
    let savedNow = false;
    try {
      let configId = existing?.id;
      if (!configId || pendingSave) {
        const saved = await saveProvider(payload);
        configId = saved.id;
        savedNow = true;
        onChanged(await fetchProviderSettings());
      }

      const result = await testProvider(configId as string);
      onChanged(await fetchProviderSettings());
      if (result.ok) {
        setNotice(
          savedNow ? `已按当前选择保存并测试通过。${result.message}` : result.message,
        );
      } else {
        // 测试可能失败，但配置已经在上面写库了，必须说清楚。
        setError(
          savedNow ? `配置已保存，但连接测试未通过：${result.message}` : result.message,
        );
      }
    } catch (err) {
      const detail = errorMessage(err);
      setError(savedNow ? `配置已保存，但测试请求失败：${detail}` : detail);
    } finally {
      setTesting(false);
    }
  }

  const embeddingModel = provider?.embedding_models.length
    ? resolveModel(embeddingChoice, embeddingCustom)
    : "";
  const chatModel = resolveModel(chatChoice, chatCustom);
  const modelSummary = [
    embeddingModel ? `检索 ${embeddingModel}` : null,
    chatModel ? `回答 ${chatModel}` : null,
    rerankChoice ? `重排 ${rerankChoice}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  // 按钮上提前暴露"会写库"，不用点下去才知道配置被改了。
  const pendingSave = needsSave(buildPayload(), existing);

  return (
    <section className="surface mt-6 overflow-hidden">
      <div className="flex items-center justify-between border-b border-ink-line bg-paper-card px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-ink">连接配置</h2>
          <p className="mt-1 text-xs text-ink-mute">选择服务商并验证模型是否可用</p>
        </div>
        <span className="rounded-full bg-paper px-3 py-1.5 text-xs text-ink-mute">
          {settings.configs.length} 个配置
        </span>
      </div>

      <div className="space-y-5 px-5 py-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="provider" className="text-sm font-medium text-ink-soft">
              服务商
            </label>
            <select
              id="provider"
              value={providerKey}
              onChange={(event) => loadProvider(event.target.value)}
              className="field-select mt-2"
            >
              {settings.providers.map((item) => {
                const configured = settings.configs.some(
                  (config) => config.provider_key === item.key,
                );
                return (
                  <option key={item.key} value={item.key}>
                    {item.label}
                    {configured ? " · 已配置" : ""}
                    {!item.requires_api_key ? " · 无需 Key" : ""}
                  </option>
                );
              })}
            </select>
          </div>

          <div>
            <label htmlFor="api-key" className="text-sm font-medium text-ink-soft">
              API Key
            </label>
            <input
              id="api-key"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                existing
                  ? `已保存 ${existing.key_masked}，留空表示不修改`
                  : provider?.requires_api_key === false
                    ? "本地服务可留空"
                    : "粘贴服务商提供的 API Key"
              }
              className="field mt-2"
            />
          </div>
        </div>

        <div className="rounded-xl bg-paper px-4 py-3 text-xs leading-relaxed text-ink-mute">
          <p>
            保存后使用
            {modelSummary ? `：${modelSummary}` : "服务商推荐的默认模型"}
          </p>
          <button
            type="button"
            onClick={() => setAdvancedOpen((current) => !current)}
            className="mt-2 font-semibold text-accent underline decoration-accent/30 underline-offset-2 transition hover:text-accent-dark"
          >
            {advancedOpen ? "收起模型设置" : "更改模型"}
          </button>
        </div>

        {advancedOpen && (
          <div className="space-y-4 rounded-xl border border-ink-line bg-paper p-4">
            <div className="grid gap-4 sm:grid-cols-2">
              {provider && provider.embedding_models.length > 0 ? (
                <div>
                  <label
                    htmlFor="embedding-model"
                    className="text-sm font-medium text-ink-soft"
                  >
                    检索模型
                  </label>
                  <select
                    id="embedding-model"
                    value={embeddingChoice}
                    onChange={(event) => setEmbeddingChoice(event.target.value)}
                    className="field-select mt-2"
                  >
                    {embeddingOptions.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.value}
                        {item.installed
                          ? " · 本地已安装"
                          : localModels
                            ? " · 未下载"
                            : item.recommended
                              ? "（推荐）"
                              : ""}
                      </option>
                    ))}
                    <option value={CUSTOM_MODEL}>自定义模型…</option>
                  </select>
                  {embeddingChoice === CUSTOM_MODEL && (
                    <input
                      value={embeddingCustom}
                      onChange={(event) => setEmbeddingCustom(event.target.value)}
                      placeholder="输入服务商支持的检索模型名"
                      className="field mt-2"
                    />
                  )}
                </div>
              ) : (
                <p className="text-xs leading-relaxed text-ink-mute">
                  该服务商不提供检索模型，只能用于回答；检索需要另配一个支持 Embedding
                  的服务商。
                </p>
              )}

              <div>
                <label htmlFor="chat-model" className="text-sm font-medium text-ink-soft">
                  回答模型
                </label>
                <select
                  id="chat-model"
                  value={chatChoice}
                  onChange={(event) => setChatChoice(event.target.value)}
                  className="field-select mt-2"
                >
                  {chatOptions.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.value}
                      {item.installed
                        ? " · 本地已安装"
                        : localModels
                          ? " · 未下载"
                          : item.recommended
                            ? "（推荐）"
                            : ""}
                    </option>
                  ))}
                  <option value={CUSTOM_MODEL}>自定义模型…</option>
                </select>
                {chatChoice === CUSTOM_MODEL && (
                  <input
                    value={chatCustom}
                    onChange={(event) => setChatCustom(event.target.value)}
                    placeholder="输入服务商支持的回答模型名"
                    className="field mt-2"
                  />
                )}
              </div>
            </div>

            {needsLocalProbe && (
              <p
                className={`text-xs leading-relaxed ${
                  localModels ? "text-ink-mute" : "text-ochre"
                }`}
              >
                {localModels
                  ? localModels.length > 0
                    ? `已检测到本地 ${localModels.length} 个模型；标「本地已安装」的可直接使用，「未下载」的需先 ollama pull。${unlisted > 0 ? `另有 ${unlisted} 个不在推荐列表，可手动输入模型名使用。` : ""}`
                    : "本地 Ollama 还没下载任何模型，请先执行 ollama pull bge-m3"
                  : localHint || "正在检测本地模型…"}
              </p>
            )}

            {provider && provider.rerank_models.length > 0 && (
              <div>
                <label
                  htmlFor="rerank-model"
                  className="text-sm font-medium text-ink-soft"
                >
                  重排模型（可选）
                </label>
                <select
                  id="rerank-model"
                  value={rerankChoice}
                  onChange={(event) => setRerankChoice(event.target.value)}
                  className="field-select mt-2"
                >
                  <option value="">不启用重排</option>
                  {provider.rerank_models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-ui-2xs leading-relaxed text-ink-mute">
                  启用后对前 15 条候选重新排序；调用失败会自动回退，不影响问答。
                </p>
              </div>
            )}
          </div>
        )}

        {notice && (
          <p
            role="status"
            className="rounded-xl border border-jade/20 bg-jade-wash px-4 py-3 text-sm text-jade"
          >
            {notice}
          </p>
        )}
        {error && (
          <p
            role="alert"
            className="rounded-xl border border-vermilion/20 bg-vermilion-wash px-4 py-3 text-sm text-vermilion"
          >
            {error}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-ink-line bg-paper/70 px-5 py-4">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={busy}
          className="btn-accent"
        >
          {busy ? "保存中…" : existing ? "保存修改" : "保存配置"}
        </button>
        {existing && (
          <button
            type="button"
            onClick={() => void handleTest()}
            disabled={testing}
            className="btn-ghost min-h-10 text-sm disabled:opacity-50"
          >
            {testing ? "测试中…" : pendingSave ? "保存并测试" : "测试连接"}
          </button>
        )}
        <span className="ml-auto text-xs text-ink-mute">
          测试与提问会消耗你的服务商额度
        </span>
      </div>
    </section>
  );
}
