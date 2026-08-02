import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "../api/client";
import type { Chokepoint, DemoState, Leg, Meta, Persona, PortStatus } from "../api/types";

interface World {
  meta: Meta;
  personas: Persona[];
  ports: PortStatus[];
  legs: Leg[];
  chokepoints: Chokepoint[];
}

interface Store {
  world: World | null;
  error: string | null;
  demo: DemoState | null;
  /** Bumped whenever the simulated world changes; views refetch on it. */
  version: number;
  busy: boolean;
  personaId: string;
  setPersonaId: (id: string) => void;
  persona: Persona | null;
  advance: () => Promise<void>;
  trigger: () => Promise<void>;
  reset: () => Promise<void>;
  refresh: () => void;
}

const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [world, setWorld] = useState<World | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<DemoState | null>(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [personaId, setPersonaId] = useState("amina");

  const loadWorld = useCallback(async () => {
    try {
      const [meta, personas, ports, legs, chokepoints] = await Promise.all([
        api.meta(),
        api.personas(),
        api.ports(),
        api.legs(),
        api.chokepoints(),
      ]);
      setWorld({ meta, personas, ports, legs, chokepoints });
      setDemo(meta.demo);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach the PortPulse API.");
    }
  }, []);

  useEffect(() => {
    void loadWorld();
  }, [loadWorld]);

  const run = useCallback(
    async (action: () => Promise<DemoState>) => {
      setBusy(true);
      try {
        const next = await action();
        setDemo(next);
        // Port status and chokepoint risk move with the clock.
        const [ports, chokepoints] = await Promise.all([api.ports(), api.chokepoints()]);
        setWorld((prev) => (prev ? { ...prev, ports, chokepoints } : prev));
        setVersion((v) => v + 1);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Demo control failed.");
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const value = useMemo<Store>(
    () => ({
      world,
      error,
      demo,
      version,
      busy,
      personaId,
      setPersonaId,
      persona: world?.personas.find((p) => p.id === personaId) ?? null,
      advance: () => run(api.advance),
      trigger: () => run(api.trigger),
      reset: () => run(api.reset),
      refresh: () => setVersion((v) => v + 1),
    }),
    [world, error, demo, version, busy, personaId, run],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): Store {
  const store = useContext(StoreContext);
  if (!store) throw new Error("useStore must be used inside StoreProvider");
  return store;
}

/** Small fetch-on-dependency hook; the demo has no need for a query library. */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
): { data: T | null; loading: boolean; stale: boolean; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fn()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Request failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // `stale` means: something is on screen, but a newer answer is on its way.
  // The demo changes the world with a button click, so silently showing the
  // previous world as if it were current is the one failure mode that would
  // actually mislead a jury.
  return { data, loading, stale: loading && data !== null, error };
}
