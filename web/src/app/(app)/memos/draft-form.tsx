"use client";

import { useActionState } from "react";
import { draftMemo, type DraftState } from "./actions";

const INITIAL: DraftState = { status: "idle" };

export function DraftForm() {
  const [state, formAction, pending] = useActionState(draftMemo, INITIAL);

  return (
    <form action={formAction} className="mt-6">
      <label htmlFor="ingredient" className="mb-2 block text-sm font-medium">
        Ingredient
      </label>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          id="ingredient"
          name="ingredient"
          required
          minLength={2}
          maxLength={60}
          pattern="[A-Za-z][A-Za-z \-]*"
          placeholder="rocuronium"
          className="w-full rounded-md border border-rule bg-surface px-3 py-2 sm:w-72"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-ink px-5 py-2 font-medium text-paper disabled:opacity-60"
        >
          {pending ? "Drafting..." : "Draft memo"}
        </button>
      </div>
      <div aria-live="polite" aria-busy={pending} className="mt-4 max-w-3xl">
        {pending && (
          <p className="text-muted">
            The agent is gathering evidence, writing the memo, and checking every number against its sources. This
            can take up to a minute.
          </p>
        )}
        {!pending && state.status === "failed" && (
          <div role="alert" className="rounded-md border border-caution/40 bg-caution-soft px-4 py-3">
            <p>{state.message}</p>
            {state.problems.length > 0 && (
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                {state.problems.map((problem, index) => (
                  <li key={index}>{problem}</li>
                ))}
              </ul>
            )}
            {state.traceId && <p className="mt-2 text-sm text-muted">Reference {state.traceId.slice(0, 8)}</p>}
          </div>
        )}
      </div>
    </form>
  );
}
