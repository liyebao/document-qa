import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("页面渲染失败", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
          <p className="font-serif text-2xl text-ink">页面出现了未处理的错误</p>
          <p className="mt-3 max-w-[42ch] text-ui-sm leading-6 text-ink-soft">
            已上传的资料和会话不会丢失。可以刷新页面重试；如果反复出现，请查看后端日志。
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="btn-accent mt-6 px-5 py-2"
          >
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
