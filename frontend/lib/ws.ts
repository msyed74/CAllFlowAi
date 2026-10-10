/**
 * WebSocket client manager for live supervisor dashboard streaming.
 * Connects to `/ws/live-dashboard/{orgId}` and handles reconnection and event dispatching.
 */

export type DashboardEvent = {
  type: string;
  call_id?: string;
  [key: string]: any;
};

export type DashboardEventHandler = (event: DashboardEvent) => void;

export class LiveDashboardSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private listeners: Set<DashboardEventHandler> = new Set();
  private reconnectTimeout: any = null;
  private isExplicitlyClosed = false;

  constructor(orgId: string, customBaseUrl?: string) {
    if (customBaseUrl) {
      this.url = `${customBaseUrl}/ws/live-dashboard/${orgId}`;
    } else {
      let wsProto = "ws:";
      let wsHost = "localhost:8000";
      if (typeof window !== "undefined") {
        wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsHost = window.location.host;
      }
      if (process.env.NEXT_PUBLIC_API_URL) {
        const clean = process.env.NEXT_PUBLIC_API_URL.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
        if (clean) wsHost = clean;
      }
      this.url = `${wsProto}//${wsHost}/ws/live-dashboard/${orgId}`;
    }
  }

  public connect(): void {
    if (typeof window === "undefined") return;
    this.isExplicitlyClosed = false;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log("[LiveDashboardSocket] Connected to supervisor stream");
      };

      this.ws.onmessage = (event) => {
        try {
          const data: DashboardEvent = JSON.parse(event.data);
          this.listeners.forEach((fn) => fn(data));
        } catch (e) {
          console.error("[LiveDashboardSocket] Failed to parse message:", e);
        }
      };

      this.ws.onclose = () => {
        if (!this.isExplicitlyClosed) {
          console.warn("[LiveDashboardSocket] Connection dropped. Reconnecting in 3s...");
          this.reconnectTimeout = setTimeout(() => this.connect(), 3000);
        }
      };

      this.ws.onerror = (err) => {
        console.error("[LiveDashboardSocket] Error:", err);
      };
    } catch (e) {
      console.error("[LiveDashboardSocket] Connection initialization error:", e);
    }
  }

  public subscribe(handler: DashboardEventHandler): () => void {
    this.listeners.add(handler);
    return () => this.listeners.delete(handler);
  }

  public send(payload: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  public whisper(callId: string, message: string): void {
    this.send({
      type: "supervisor.whisper",
      call_id: callId,
      message,
    });
  }

  public takeover(callId: string, reason?: string): void {
    this.send({
      type: "supervisor.takeover",
      call_id: callId,
      reason,
    });
  }

  public disconnect(): void {
    this.isExplicitlyClosed = true;
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
