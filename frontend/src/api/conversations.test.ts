import { describe, expect, it, vi } from "vitest";
import type { MessageExchange } from "./types";
import { sendMessageStream } from "./conversations";

function sseResponse(blocks: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const block of blocks) {
        controller.enqueue(encoder.encode(block));
      }
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

const DONE = {
  user_message: {},
  assistant_message: {},
} as unknown as MessageExchange;

describe("sendMessageStream", () => {
  it("forwards retrieval trace events", async () => {
    const trace = {
      queries: ["知识库检索词"],
      documents: [{ name: "资料A.pdf", location: "第 1 页", marker: 1 }],
      searches: 1,
      expanded: 0,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          `event: retrieval\ndata: ${JSON.stringify(trace)}\n\n`,
          `event: done\ndata: ${JSON.stringify(DONE)}\n\n`,
        ]),
      ),
    );

    const onRetrieval = vi.fn();
    await sendMessageStream("conversation-1", "问题", undefined, {
      onDelta: vi.fn(),
      onRetrieval,
      onDone: vi.fn(),
      onError: vi.fn(),
    });

    expect(onRetrieval).toHaveBeenCalledWith(trace);
  });
});
