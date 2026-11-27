const STATUS_MAP: Record<string, { label: string; dot: string; text: string }> = {
  uploading: { label: "上传中", dot: "bg-sky-500", text: "text-sky-700" },
  processing: { label: "处理中", dot: "bg-ochre animate-blink", text: "text-ochre" },
  ready: { label: "可检索", dot: "bg-jade", text: "text-jade" },
  failed: { label: "处理失败", dot: "bg-vermilion", text: "text-vermilion" },
};

export function FileStatus({
  status,
  failureReason,
}: {
  status: string;
  failureReason?: string | null;
}) {
  const meta = STATUS_MAP[status] ?? {
    label: status,
    dot: "bg-ink-mute",
    text: "text-ink-mute",
  };
  return (
    <span
      title={failureReason ?? undefined}
      className={`inline-flex items-center gap-1.5 text-xs font-medium ${meta.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden="true" />
      {meta.label}
    </span>
  );
}
