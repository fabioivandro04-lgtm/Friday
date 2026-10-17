// Ligação de voz ao Friday Core (Pipecat sobre WebSocket), com reconexão automática.

import { PipecatClient } from "@pipecat-ai/client-js";
import { WebSocketTransport } from "@pipecat-ai/websocket-transport";
import type { CoreEvent } from "./state";

export type ClientCallbacks = {
  onConnected: () => void;
  onDisconnected: () => void;
  onServerMessage: (data: any) => void;
};

export interface PipecatLike {
  connect(params: { wsUrl: string }): Promise<unknown>;
  disconnect(): Promise<void>;
  enableMic(on: boolean): void;
  sendClientMessage(type: string, data?: unknown): void;
}

export function backoffDelay(attempt: number): number {
  return Math.min(500 * 2 ** attempt, 10_000);
}

export function wsUrlFor(coreUrl: string, token: string): string {
  const u = new URL(coreUrl);
  const proto = u.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${u.host}/ws?token=${encodeURIComponent(token)}`;
}

export function createPipecatClient(callbacks: ClientCallbacks): PipecatLike {
  return new PipecatClient({ transport: new WebSocketTransport(), enableMic: false, enableCam: false, callbacks });
}

type Options = {
  url: string;
  onEvent: (e: CoreEvent) => void;
  createClient: (cb: ClientCallbacks) => PipecatLike;
};

export class FridayConnection {
  private client: PipecatLike;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private manual = false;

  constructor(private opts: Options) {
    this.client = opts.createClient({
      onConnected: () => {
        this.attempt = 0;
        opts.onEvent({ type: "connection", data: { connected: true } });
      },
      onDisconnected: () => this.handleDrop(),
      onServerMessage: (data) => opts.onEvent(data),
    });
  }

  async connect(): Promise<void> {
    this.manual = false;
    try {
      await this.client.connect({ wsUrl: this.opts.url });
    } catch {
      this.handleDrop();
    }
  }

  async disconnect(): Promise<void> {
    this.manual = true;
    clearTimeout(this.timer);
    this.timer = undefined;
    await this.client.disconnect();
  }

  setMicEnabled(on: boolean): void {
    this.client.enableMic(on);
  }

  confirm(id: string): void {
    this.client.sendClientMessage("confirm", { id });
  }

  cancel(): void {
    this.client.sendClientMessage("cancel", {});
  }

  private handleDrop(): void {
    this.opts.onEvent({ type: "connection", data: { connected: false } });
    if (this.manual || this.timer !== undefined) return;
    const delay = backoffDelay(this.attempt++);
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.connect();
    }, delay);
  }
}
