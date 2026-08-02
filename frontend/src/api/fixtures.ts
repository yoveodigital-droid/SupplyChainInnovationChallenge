/**
 * Replay layer for the hosted preview.
 *
 * The published preview runs under a content-security policy that blocks every
 * network request, so there is no FastAPI to talk to. Rather than build a
 * separate marketing mock — which would drift from the product the moment
 * either changed — the preview ships the *real* UI on top of API responses
 * recorded from a live backend at each step of the scripted demo.
 *
 * `scripts/record_preview.py` produces the bundle. Everything here is read-only
 * except the demo controls, which move between recorded states.
 */

export interface FixtureBundle {
  version: number;
  generated_at: string;
  initial: string;
  /** Responses that never change between states. */
  shared: Record<string, unknown>;
  /** state key -> { request path -> response }. */
  states: Record<string, Record<string, unknown>>;
  /** state key -> { advance | trigger | reset : state key }. */
  transitions: Record<string, Record<string, string>>;
  /**
   * `${state}|${shipmentId}` -> patch applied when that shipment's recommended
   * option is accepted: the accept response plus the reads it invalidates.
   */
  accepts: Record<
    string,
    { response: unknown; patch: Record<string, unknown>; option_id: string }
  >;
}

declare global {
  interface Window {
    __PORTPULSE_FIXTURES__?: FixtureBundle;
  }
}

export class PreviewUnavailable extends Error {
  constructor(what: string) {
    super(
      `${what} isn't part of this recorded preview. Run the demo locally ` +
        `(\`make dev\`) for the full interactive build.`,
    );
    this.name = "PreviewUnavailable";
  }
}

class FixtureStore {
  private state: string;
  /** Reads overridden by an accepted recommendation, cleared on reset. */
  private overrides: Record<string, unknown> = {};

  constructor(private readonly bundle: FixtureBundle) {
    this.state = bundle.initial;
  }

  get currentState(): string {
    return this.state;
  }

  private lookup(path: string): unknown {
    if (path in this.overrides) return this.overrides[path];
    const state = this.bundle.states[this.state] ?? {};
    if (path in state) return state[path];
    if (path in this.bundle.shared) return this.bundle.shared[path];
    return undefined;
  }

  get(path: string): unknown {
    const hit = this.lookup(path);
    if (hit === undefined) throw new PreviewUnavailable(`\`${path}\``);
    return structuredClone(hit);
  }

  move(action: "advance" | "trigger" | "reset"): unknown {
    const next = this.bundle.transitions[this.state]?.[action];
    if (!next) throw new PreviewUnavailable(`"${action}" from here`);
    if (action === "reset") this.overrides = {};
    this.state = next;
    return this.get("/demo/state");
  }

  accept(shipmentId: string): unknown {
    const entry = this.bundle.accepts[`${this.state}|${shipmentId}`];
    if (!entry) throw new PreviewUnavailable("Applying this option");
    Object.assign(this.overrides, entry.patch);
    return structuredClone(entry.response);
  }

  /** Is this exact decision in the recording? */
  canAccept(shipmentId: string, optionId: string): boolean {
    const entry = this.bundle.accepts[`${this.state}|${shipmentId}`] as
      | { option_id?: string }
      | undefined;
    return entry?.option_id === optionId;
  }

  revert(shipmentId: string): unknown {
    // Drop every override that mentions this shipment, restoring the recording.
    for (const key of Object.keys(this.overrides)) {
      if (key.includes(shipmentId)) delete this.overrides[key];
    }
    return this.get(`/shipments/${shipmentId}`);
  }
}

let store: FixtureStore | null = null;

export function fixturesActive(): boolean {
  if (store) return true;
  const bundle = typeof window !== "undefined" ? window.__PORTPULSE_FIXTURES__ : undefined;
  if (!bundle) return false;
  store = new FixtureStore(bundle);
  return true;
}

/** True in the hosted preview, false against a live backend. */
export function isPreview(): boolean {
  return fixturesActive();
}

/**
 * Only the recommended option at each recorded step was captured. Anything else
 * is disabled rather than allowed to fail, so the preview never shows an error
 * a live build would not produce.
 */
export function canAcceptInPreview(shipmentId: string, optionId: string): boolean {
  if (!fixturesActive() || !store) return true;
  return store.canAccept(shipmentId, optionId);
}

export function fixtureGeneratedAt(): string | null {
  return typeof window !== "undefined"
    ? (window.__PORTPULSE_FIXTURES__?.generated_at ?? null)
    : null;
}

/** Resolve a request against the recording. Rejects for anything unrecorded. */
export async function serveFromFixtures(path: string, method: string, body?: unknown) {
  if (!store) throw new PreviewUnavailable(path);
  // A touch of latency keeps the loading and "refreshing" states visible, which
  // is part of what the preview is meant to show.
  await new Promise((resolve) => setTimeout(resolve, 90));

  if (method === "POST") {
    if (path === "/demo/advance") return store.move("advance");
    if (path === "/demo/trigger") return store.move("trigger");
    if (path === "/demo/reset") return store.move("reset");
    if (path === "/feedback") return { id: 1, ...(body as object), sim_date: null };
    const accept = path.match(/^\/shipments\/([^/]+)\/accept/);
    if (accept) return store.accept(accept[1]);
    const revert = path.match(/^\/shipments\/([^/]+)\/revert$/);
    if (revert) return store.revert(revert[1]);
    throw new PreviewUnavailable(path);
  }
  return store.get(path);
}
