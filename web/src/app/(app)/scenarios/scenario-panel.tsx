"use client";

import { useActionState, useState } from "react";
import { runScenario, type DrugImpact, type ScenarioState } from "./actions";

const SCOPES = [
  { value: "country", label: "Country", hint: "Three-letter country code, such as IND" },
  { value: "company", label: "Manufacturer", hint: "Manufacturer DUNS number" },
  { value: "facility", label: "Facility", hint: "Facility DUNS number" },
];

const PRESETS = [
  { label: "India stops supplying for 60 days", scope: "country", entity: "IND", days: 60 },
  { label: "China stops supplying for 90 days", scope: "country", entity: "CHN", days: 90 },
];

const INITIAL: ScenarioState = { status: "idle" };
const VISIBLE_ROWS = 15;

function plural(count: number, one: string, many: string) {
  return `${count.toLocaleString("en-US")} ${count === 1 ? one : many}`;
}

function Chance({ value }: { value: number }) {
  const percent = Math.round(value * 100);
  return (
    <div className="flex items-center gap-3" title={`${percent}% chance of running out`}>
      <div className="h-1.5 w-28 shrink-0 rounded-full bg-rule" aria-hidden="true">
        <div className="h-1.5 rounded-full bg-caution-mark" style={{ width: `${percent}%` }} />
      </div>
      <span className="w-10 text-right tabular-nums">{percent}%</span>
    </div>
  );
}

function daysLeft(drug: DrugImpact, horizon: number) {
  if (drug.median_days_to_runout === null || drug.median_days_to_runout === undefined) {
    return `Over ${horizon}`;
  }
  return Math.round(drug.median_days_to_runout).toLocaleString("en-US");
}

function Results({ result }: { result: Extract<ScenarioState, { status: "done" }> }) {
  const [showAll, setShowAll] = useState(false);
  const lost = result.drugs.filter((drug) => drug.status === "lost").length;
  const partial = result.drugs.length - lost;
  const likely = result.drugs.filter((drug) => drug.p_stockout >= 0.5).length;
  const patientView = result.patients !== null;
  const rows = showAll ? result.drugs : result.drugs.slice(0, VISIBLE_ROWS);
  const source = result.scope === "country" ? result.entity : `${result.scope} ${result.entity}`;

  if (result.drugs.length === 0) {
    return (
      <p className="max-w-3xl text-lg">
        None of your formulary drugs depend on {source}. Try another country or manufacturer.
      </p>
    );
  }

  return (
    <div>
      <div className="max-w-3xl">
        <p className="text-6xl font-semibold leading-none tracking-tight tabular-nums">
          {(patientView ? result.patients ?? 0 : likely).toLocaleString("en-US")}
        </p>
        <p className="mt-3 text-lg leading-snug">
          {patientView
            ? `${(result.patients ?? 0) === 1 ? "patient is" : "patients are"} on drugs that could run short if supply from ${source} stops for ${result.days} days.`
            : `${likely === 1 ? "drug is" : "drugs are"} more likely than not to run out if supply from ${source} stops for ${result.days} days.`}
        </p>
        <p className="mt-3 leading-relaxed text-muted">
          {plural(lost, "drug loses", "drugs lose")} all known supply and {plural(partial, "drug loses", "drugs lose")} part
          of it. {patientView ? `${plural(likely, "is", "are")} more likely than not to run out.` : "Patient counts aren't shown for your role."}
        </p>
      </div>

      <div className="mt-10 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-sm">
          <caption className="sr-only">Drugs affected by this disruption, most urgent first</caption>
          <thead>
            <tr className="border-b border-ink text-left">
              <th scope="col" className="py-2 pr-4 font-semibold">Drug</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Supply lost</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Chance of running out</th>
              <th scope="col" className="py-2 pr-4 text-right font-semibold">Median days left</th>
              {patientView && (
                <>
                  <th scope="col" className="py-2 pr-4 text-right font-semibold">Patients on it</th>
                  <th scope="col" className="py-2 text-right font-semibold">In ICU</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((drug) => (
              <tr key={drug.drug_rxcui} className="border-b border-rule align-middle">
                <td className="py-2.5 pr-4">{drug.drug_name}</td>
                <td className="py-2.5 pr-4">{drug.status === "lost" ? "All" : "Part"}</td>
                <td className="py-2.5 pr-4">
                  <Chance value={drug.p_stockout} />
                </td>
                <td className="py-2.5 pr-4 text-right tabular-nums">{daysLeft(drug, result.days)}</td>
                {patientView && (
                  <>
                    <td className="py-2.5 pr-4 text-right tabular-nums">{drug.patients ?? 0}</td>
                    <td className="py-2.5 text-right tabular-nums">{drug.icu_patients ?? 0}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.drugs.length > VISIBLE_ROWS && (
        <button
          type="button"
          onClick={() => setShowAll((value) => !value)}
          className="mt-4 text-sm text-public underline decoration-rule underline-offset-4 hover:decoration-public"
        >
          {showAll ? "Show the first 15" : `Show all ${result.drugs.length} drugs`}
        </button>
      )}
    </div>
  );
}

export function ScenarioPanel() {
  const [state, formAction, pending] = useActionState(runScenario, INITIAL);
  const [scope, setScope] = useState("country");
  const [entity, setEntity] = useState("IND");
  const [days, setDays] = useState(60);
  const hint = SCOPES.find((option) => option.value === scope)?.hint;

  return (
    <div className="mt-8">
      <form action={formAction} className="flex flex-wrap items-end gap-x-6 gap-y-4">
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Disruption at</legend>
          <div className="flex overflow-hidden rounded-md border border-rule">
            {SCOPES.map((option) => (
              <label
                key={option.value}
                className={`cursor-pointer px-3 py-2 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-public ${
                  scope === option.value ? "bg-ink text-paper" : "bg-surface"
                }`}
              >
                <input
                  type="radio"
                  name="scope"
                  value={option.value}
                  checked={scope === option.value}
                  onChange={() => setScope(option.value)}
                  className="sr-only"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="block">
          <span className="mb-2 block text-sm font-medium">Code</span>
          <input
            name="entity"
            value={entity}
            onChange={(event) => setEntity(event.target.value)}
            required
            minLength={2}
            maxLength={20}
            pattern="[A-Za-z0-9]+"
            aria-describedby="entity-hint"
            className="w-40 rounded-md border border-rule bg-surface px-3 py-2 uppercase"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium">Lasting (days)</span>
          <input
            name="days"
            type="number"
            min={1}
            max={365}
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            required
            className="w-28 rounded-md border border-rule bg-surface px-3 py-2 tabular-nums"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-ink px-5 py-2 font-medium text-paper disabled:opacity-60"
        >
          {pending ? "Simulating..." : "Run simulation"}
        </button>
        <p id="entity-hint" className="basis-full text-sm text-muted">
          {hint}
        </p>
      </form>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm">
        <span className="text-muted">Try</span>
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            onClick={() => {
              setScope(preset.scope);
              setEntity(preset.entity);
              setDays(preset.days);
            }}
            className="text-public underline decoration-rule underline-offset-4 hover:decoration-public"
          >
            {preset.label}
          </button>
        ))}
      </div>

      <div aria-live="polite" aria-busy={pending} className="mt-12">
        {pending && <p className="text-muted">Running 2,000 supply simulations against your inventory...</p>}
        {!pending && state.status === "done" && (
          <Results key={`${state.scope}-${state.entity}-${state.days}`} result={state} />
        )}
        {!pending && state.status === "failed" && (
          <div role="alert" className="max-w-3xl rounded-md border border-caution/40 bg-caution-soft px-4 py-3">
            <p>{state.message}</p>
            {state.traceId && <p className="mt-1 text-sm text-muted">Reference {state.traceId.slice(0, 8)}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
