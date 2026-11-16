import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/client";
import {
  deleteProvider,
  fetchProviderSettings,
  setProviderRole,
  testProvider,
} from "../api/settings";
import type { ModelProviderSettings } from "../api/types";
import { ModelRoles } from "../components/ModelRoles";
import { ProviderEditor } from "../components/ProviderEditor";
import { SavedConfigList } from "../components/SavedConfigList";
import { NOTICE_AUTO_CLOSE_MS } from "../lib/notice";

export function SettingsPage() {
  const [settings, setSettings] = useState<ModelProviderSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await fetchProviderSettings();
    setSettings(data);
    return data;
  }, []);

  useEffect(() => {
    async function load() {
      try {
        await refresh();
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [refresh]);

  // 提示条自动消失，不需要用户手动关闭；文本变化会重新计时。
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

  async function handleRoleChange(role: "embedding" | "chat", configId: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const data = await setProviderRole(configId, role);
      setSettings(data);
      setNotice(
        role === "embedding"
          ? "已切换检索模型；使用旧索引的资料集需要重建索引后才能继续提问。"
          : "已切换回答模型。",
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleTest(configId: string) {
    setTestingId(configId);
    setError(null);
    setNotice(null);
    try {
      const result = await testProvider(configId);
      await refresh();
      if (result.ok) {
        setNotice(result.message);
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setTestingId(null);
    }
  }

  async function handleDelete(configId: string, providerLabel: string) {
    if (
      !window.confirm(
        `确认删除 ${providerLabel} 的本地配置？删除后如需继续使用，请在服务商处重新生成并填写 Key。`,
      )
    ) {
      return;
    }
    try {
      await deleteProvider(configId);
      await refresh();
      setNotice("配置已删除");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl animate-pulse py-10 text-sm text-ink-mute">
        正在读取模型配置…
      </div>
    );
  }

  if (!settings) {
    return (
      <p
        role="alert"
        className="mx-auto max-w-5xl rounded-xl border border-vermilion/20 bg-vermilion-wash px-4 py-3 text-sm leading-relaxed text-vermilion"
      >
        {error ?? "模型配置读取失败，请刷新重试"}
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-5xl animate-rise">
      <div className="surface bg-gradient-to-br from-white to-accent-wash/50 p-6 sm:p-8">
        <p className="text-sm font-semibold text-accent">系统配置</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          模型服务
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-soft">
          管理检索和回答模型。配置保存后，可分别测试连接并选择当前使用的模型。
        </p>
      </div>

      {(error || notice) && (
        // 页面较长，测试结果吸附在顶部，避免用户滚到下方操作后还要往上翻。
        // main 是滚动容器且已在移动端 header 下方，所以不需要额外让出 header 高度。
        <div className="sticky top-2 z-20 mt-4">
          <div
            role={error ? "alert" : "status"}
            className={`relative overflow-hidden rounded-xl border px-4 py-3 text-sm leading-relaxed shadow-card ${
              error
                ? "border-vermilion/20 bg-vermilion-wash text-vermilion"
                : "border-jade/20 bg-jade-wash text-jade"
            }`}
          >
            {error ?? notice}
            <span
              aria-hidden="true"
              className={`animate-shrink absolute inset-x-0 bottom-0 h-0.5 origin-left motion-reduce:hidden ${
                error ? "bg-vermilion/40" : "bg-jade/40"
              }`}
              style={{ animationDuration: `${NOTICE_AUTO_CLOSE_MS}ms` }}
            />
          </div>
        </div>
      )}

      <ModelRoles
        settings={settings}
        busy={busy}
        onRoleChange={(role, configId) => void handleRoleChange(role, configId)}
      />

      <ProviderEditor settings={settings} onChanged={setSettings} />

      <SavedConfigList
        settings={settings}
        testingId={testingId}
        onTest={(id) => void handleTest(id)}
        onDelete={(id, label) => void handleDelete(id, label)}
      />

      <p className="mt-6 rounded-xl bg-white px-4 py-3 text-xs leading-relaxed text-ink-mute">
        资料入库时片段会发送给所选检索服务；提问时问题与检索片段会发送给所选回答服务。
      </p>
    </div>
  );
}
