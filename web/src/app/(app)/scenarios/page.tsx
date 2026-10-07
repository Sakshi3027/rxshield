import { ScenarioPanel } from "./scenario-panel";

export default function ScenariosPage() {
  return (
    <section>
      <div className="max-w-3xl">
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">Plan for a disruption</h1>
        <p className="mt-2 leading-relaxed text-muted">
          Simulate a country, manufacturer, or facility going offline and see which of your drugs run out first,
          and how many patients depend on them.
        </p>
      </div>
      <ScenarioPanel />
    </section>
  );
}
