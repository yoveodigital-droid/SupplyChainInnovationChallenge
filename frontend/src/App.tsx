import { DemoBar } from "./components/DemoBar";
import { ActivityBar } from "./components/primitives";
import { DashboardView } from "./views/DashboardView";
import { PhoneView } from "./views/PhoneView";
import { PortView } from "./views/PortView";
import { useStore } from "./state/store";

const VIEW_LABEL: Record<string, string> = {
  phone: "Phone alert",
  dashboard: "Forwarder dashboard",
  port: "Port authority",
};

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-accent text-white shadow-card">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
          <path
            d="M3 14h2.2l1.6-4.4 2.4 8.4 2.6-12 2.4 9 1.6-5H21"
            stroke="currentColor"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight">PortPulse</div>
        <div className="text-[10.5px] uppercase tracking-[0.13em] text-ink-faint">
          Predict · Personalise · Prescribe
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const { world, error, personaId, setPersonaId, persona, busy } = useStore();

  if (error && !world) {
    return (
      <div className="grid min-h-screen place-items-center p-6">
        <div className="card max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold">Cannot reach the PortPulse API</h1>
          <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{error}</p>
          <p className="mt-3 text-[12px] text-ink-faint">
            Start the backend with <code className="rounded bg-paper-sunken px-1">make dev</code> and
            reload.
          </p>
        </div>
      </div>
    );
  }

  if (!world || !persona) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="flex items-center gap-3 text-sm text-ink-faint">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
          Loading the corridor…
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur">
        <ActivityBar active={busy} />
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-4 px-4 py-3 sm:px-6">
          <Logo />
          <div className="ml-auto order-3 w-full lg:order-2 lg:ml-auto lg:w-auto">
            <DemoBar />
          </div>
        </div>

        <nav className="mx-auto flex max-w-[1400px] gap-1.5 overflow-x-auto px-4 pb-2.5 sm:px-6">
          {world.personas.map((p) => {
            const active = p.id === personaId;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setPersonaId(p.id)}
                aria-current={active ? "page" : undefined}
                className={`flex shrink-0 items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition ${
                  active
                    ? "border-accent bg-accent text-white shadow-card"
                    : "border-line bg-paper-raised hover:border-line-strong"
                }`}
              >
                <span
                  className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg text-base ${
                    active ? "bg-white/15" : "bg-paper-sunken"
                  }`}
                  aria-hidden
                >
                  {p.avatar}
                </span>
                <span className="leading-tight">
                  <span className="block text-[12.5px] font-semibold">{p.name}</span>
                  <span
                    className={`block text-[10.5px] ${active ? "text-white/75" : "text-ink-faint"}`}
                  >
                    {VIEW_LABEL[p.view]} · {p.location}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto max-w-[1400px] px-4 py-5 sm:px-6">
        <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-xl font-semibold tracking-tight">{persona.role}</h1>
          <p className="text-[13px] text-ink-soft">{persona.blurb}</p>
        </div>

        {persona.view === "phone" && <PhoneView persona={persona} />}
        {persona.view === "dashboard" && <DashboardView persona={persona} />}
        {persona.view === "port" && <PortView persona={persona} />}
      </main>

      <footer className="mx-auto max-w-[1400px] px-4 pb-8 pt-2 sm:px-6">
        <div className="hairline flex flex-wrap items-center justify-between gap-3 pt-4 text-[11.5px] text-ink-faint">
          <p>{world.meta.disclaimer}</p>
          <p className="tnum">
            {String(world.meta.model.algorithm)} · trained on{" "}
            {Number(world.meta.model.training_rows).toLocaleString("en-US")} rows through{" "}
            {String(world.meta.model.trained_through)} · held-out MAE{" "}
            {String(world.meta.model.congestion_mae)} vs {String(world.meta.model.congestion_mae_naive)}{" "}
            for persistence
          </p>
        </div>
      </footer>
    </div>
  );
}
