import { useStore } from "../state/store";
import { fmtLongDate } from "../lib/format";

export function DemoBar() {
  const { demo, advance, trigger, reset, busy } = useStore();
  if (!demo) return null;

  return (
    <div className="flex flex-wrap items-center gap-2.5 rounded-full border border-line bg-paper-raised px-3 py-1.5 shadow-card">
      <div className="flex items-center gap-2 pr-1">
        <span className="relative flex h-2 w-2" aria-hidden>
          <span
            className={`absolute inline-flex h-full w-full rounded-full opacity-70 ${
              demo.scenario_active ? "animate-pulse-ring bg-risk-red" : "bg-risk-green"
            }`}
          />
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              demo.scenario_active ? "bg-risk-red" : "bg-risk-green"
            }`}
          />
        </span>
        <div className="leading-tight">
          <div className="label leading-none">Simulated date</div>
          <div className="tnum text-[12.5px] font-semibold leading-tight">
            {fmtLongDate(demo.sim_date)}
          </div>
        </div>
      </div>

      <span className="hidden h-6 w-px bg-line sm:block" aria-hidden />

      <button
        type="button"
        className="btn px-3 py-1 text-[12.5px]"
        onClick={() => void advance()}
        disabled={busy || !demo.can_advance}
        title={demo.can_advance ? "Step the simulated clock forward one day" : "End of the generated window"}
      >
        Advance day
      </button>

      <button
        type="button"
        className={`btn px-3 py-1 text-[12.5px] ${demo.scenario_active ? "" : "btn-danger"}`}
        onClick={() => void trigger()}
        disabled={busy || demo.scenario_active}
      >
        {demo.scenario_active ? `Scenario · day ${demo.scenario_day}` : "Trigger scenario"}
      </button>

      <button
        type="button"
        className="btn px-3 py-1 text-[12.5px]"
        onClick={() => void reset()}
        disabled={busy}
      >
        Reset
      </button>

      {demo.days_advanced > 0 && (
        <span className="tnum hidden text-[11px] text-ink-faint sm:inline">
          +{demo.days_advanced}d from seed
        </span>
      )}
    </div>
  );
}
