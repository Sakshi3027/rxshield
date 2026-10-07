"use client";

import { useActionState, useRef } from "react";
import { ask, type AskState } from "./actions";
import { Answer } from "./answer";

const EXAMPLES = [
  "How many days of heparin do we have?",
  "What should we use instead of pentostatin?",
  "Which critical shortage drugs are made only in India?",
];

const INITIAL: AskState = { status: "idle" };

export function AskPanel() {
  const [state, formAction, pending] = useActionState(ask, INITIAL);
  const questionRef = useRef<HTMLTextAreaElement>(null);

  function fillExample(example: string) {
    if (questionRef.current) {
      questionRef.current.value = example;
      questionRef.current.focus();
    }
  }

  return (
    <div className="mt-8">
      <form action={formAction} className="max-w-3xl">
        <label htmlFor="question" className="sr-only">
          Question
        </label>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <textarea
            id="question"
            name="question"
            ref={questionRef}
            rows={2}
            maxLength={500}
            required
            defaultValue={state.status === "idle" ? "" : state.question}
            placeholder="Ask about a drug, your stock, a manufacturer, or a country"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            className="flex-1 resize-y rounded-md border border-rule bg-surface px-3 py-2.5 leading-snug placeholder:text-muted focus:border-public"
          />
          <button
            type="submit"
            disabled={pending}
            className="rounded-md bg-ink px-5 py-2.5 font-medium text-paper disabled:opacity-60"
          >
            {pending ? "Answering..." : "Ask"}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm">
          <span className="text-muted">Try</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => fillExample(example)}
              className="text-public underline decoration-rule underline-offset-4 hover:decoration-public"
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      <div aria-live="polite" aria-busy={pending} className="mt-10">
        {pending && <p className="text-muted">Checking FDA data and your hospital&apos;s records...</p>}
        {!pending && state.status === "answered" && (
          <Answer answer={state.answer} cache={state.cache} traceId={state.traceId} sources={state.sources} />
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
