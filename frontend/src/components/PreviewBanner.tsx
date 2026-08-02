import { fixtureGeneratedAt } from "../api/fixtures";

/**
 * Shown only in the hosted preview. A jury member who opens a link deserves to
 * know immediately that they are driving a recording rather than a live model —
 * the alternative is letting them assume it either way.
 */
export function PreviewBanner() {
  const seeded = fixtureGeneratedAt();
  return (
    <div className="border-b border-accent/20 bg-accent-soft">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1.5 sm:px-6">
        <span className="chip bg-accent px-2 py-0.5 text-white">Preview</span>
        <p className="text-[11.5px] leading-snug text-accent-deep">
          Hosted staging build. Every number is a real response recorded from the running
          backend at each step of the demo{seeded ? ` (world seeded ${seeded})` : ""} — the
          persona switcher and the demo clock are live, model inference is not.
        </p>
        <code className="ml-auto hidden rounded bg-white/60 px-1.5 py-0.5 text-[11px] text-accent-deep sm:block">
          make dev
        </code>
      </div>
    </div>
  );
}
