"use client";

import { useActionState } from "react";
import { reviewMemo, type ReviewState } from "../actions";

const INITIAL: ReviewState = { status: "idle" };

export function ReviewForm({ actionId }: { actionId: number }) {
  const [state, formAction, pending] = useActionState(reviewMemo.bind(null, actionId), INITIAL);

  return (
    <form action={formAction} className="mt-12 border-t border-rule pt-6">
      <h2 className="text-base font-semibold">Review</h2>
      <p className="mt-1 text-sm leading-relaxed text-muted">
        An executive who didn&apos;t draft this memo approves or rejects it, once. A rejection needs a note so the next
        draft knows what to fix.
      </p>
      <label htmlFor="note" className="mt-5 block text-sm font-medium">
        Note
      </label>
      <textarea
        id="note"
        name="note"
        rows={3}
        maxLength={1000}
        className="mt-2 w-full rounded-md border border-rule bg-surface px-3 py-2"
      />
      <div className="mt-4 flex gap-3">
        <button
          type="submit"
          name="decision"
          value="approved"
          disabled={pending}
          className="rounded-md bg-ink px-5 py-2 font-medium text-paper disabled:opacity-60"
        >
          Approve
        </button>
        <button
          type="submit"
          name="decision"
          value="rejected"
          disabled={pending}
          className="rounded-md border border-rule px-5 py-2 font-medium hover:border-ink disabled:opacity-60"
        >
          Reject
        </button>
      </div>
      {state.status === "failed" && (
        <p role="alert" className="mt-4 rounded-md border border-caution/40 bg-caution-soft px-4 py-3">
          {state.message}
        </p>
      )}
    </form>
  );
}
