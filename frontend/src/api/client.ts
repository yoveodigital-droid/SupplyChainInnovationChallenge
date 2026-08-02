import { fixturesActive, serveFromFixtures } from "./fixtures";
import type {
  AcceptResult,
  Alert,
  Chokepoint,
  DemoState,
  DisruptionEvent,
  Exposure,
  Forecast,
  Leg,
  Meta,
  Persona,
  PortPressure,
  PortStatus,
  Recommendations,
  Shipment,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // The hosted preview has no backend to call; it replays a recording instead.
  if (fixturesActive()) {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    return (await serveFromFixtures(path, method, body)) as T;
  }
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(body || response.statusText, response.status);
  }
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  meta: () => request<Meta>("/meta"),
  personas: () => request<Persona[]>("/personas"),
  ports: () => request<PortStatus[]>("/ports"),
  legs: () => request<Leg[]>("/legs"),
  chokepoints: () => request<Chokepoint[]>("/chokepoints"),
  events: (limit = 25) => request<DisruptionEvent[]>(`/events?limit=${limit}`),

  forecast: (portId: string, horizon = 14) =>
    request<Forecast>(`/ports/${portId}/forecast?horizon=${horizon}`),
  pressure: (portId: string, horizon = 14, historyDays = 60) =>
    request<PortPressure>(
      `/ports/${portId}/pressure?horizon=${horizon}&history_days=${historyDays}`,
    ),

  shipments: (persona?: string) =>
    request<Shipment[]>(`/shipments${persona ? `?persona=${persona}` : ""}`),
  shipment: (id: string) => request<Shipment>(`/shipments/${id}`),
  exposure: (id: string) => request<Exposure>(`/shipments/${id}/exposure`),
  recommendations: (id: string) => request<Recommendations>(`/shipments/${id}/recommendations`),
  alert: (id: string, lang = "en") => request<Alert>(`/shipments/${id}/alert?lang=${lang}`),

  accept: (id: string, optionId: string, lang = "en") =>
    post<AcceptResult>(`/shipments/${id}/accept?lang=${lang}`, { option_id: optionId }),
  revert: (id: string) => post<Shipment>(`/shipments/${id}/revert`),

  demoState: () => request<DemoState>("/demo/state"),
  advance: () => post<DemoState>("/demo/advance"),
  trigger: () => post<DemoState>("/demo/trigger"),
  reset: () => post<DemoState>("/demo/reset"),

  feedback: (shipmentId: string, helpful: boolean, note = "") =>
    post<unknown>("/feedback", { shipment_id: shipmentId, helpful, note }),
};
