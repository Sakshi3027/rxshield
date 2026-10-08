"use client";

import { Children, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Sources } from "./actions";

const CITATION_SPLIT = /(\[(?:G|H|L\d+|P\d+)\])/g;
const CITATION_ONLY = /^\[(G|H|L\d+|P\d+)\]$/;
const CITATION_ALL = /\[(G|H|L\d+|P\d+)\]/g;

type Kind = "public" | "private";
type Entry = { id: string; kind: Kind; name: string; detail: ReactNode };

function describe(id: string): { label: string; kind: Kind } {
  if (id === "G") return { label: "Shortage graph", kind: "public" };
  if (id === "H") return { label: "Your inventory", kind: "private" };
  if (id.startsWith("L")) return { label: `Label ${id.slice(1)}`, kind: "public" };
  return { label: `Document ${id.slice(1)}`, kind: "private" };
}

function Citation({ id }: { id: string }) {
  const { label, kind } = describe(id);
  const tone = kind === "public" ? "bg-public-soft text-public" : "bg-private-soft text-private";
  return (
    <a
      href={`#source-${id}`}
      className={`mx-0.5 inline-block rounded px-1.5 text-[0.8125rem] font-medium leading-6 no-underline hover:underline ${tone}`}
    >
      {label}
    </a>
  );
}

function withCitations(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child !== "string") return child;
    return child.split(CITATION_SPLIT).map((part, index) => {
      const match = part.match(CITATION_ONLY);
      return match ? <Citation key={index} id={match[1]} /> : part;
    });
  });
}

const components: Components = {
  p: ({ children }) => <p className="mb-4 last:mb-0">{withCitations(children)}</p>,
  li: ({ children }) => <li>{withCitations(children)}</li>,
  strong: ({ children }) => <strong className="font-semibold">{withCitations(children)}</strong>,
  ul: ({ children }) => <ul className="mb-4 list-disc space-y-1.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-4 list-decimal space-y-1.5 pl-5">{children}</ol>,
  table: ({ children }) => (
    <div className="mb-4 overflow-x-auto">
      <table className="w-full text-sm tabular-nums">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b border-ink px-3 py-2 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b border-rule px-3 py-2 align-top">{withCitations(children)}</td>,
  a: ({ children }) => <span>{children}</span>,
};

function amount(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "not recorded";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-US") : String(value);
}

function sourceEntries(sources: Sources): Entry[] {
  const entries: Entry[] = [];
  if (sources.inventory.length > 0) {
    entries.push({
      id: "H",
      kind: "private",
      name: "Your inventory",
      detail: (
        <ul className="space-y-3">
          {sources.inventory.map((row) => (
            <li key={String(row.drug_rxcui)}>
              <p className="font-medium text-ink">{row.drug_name}</p>
              <p className="tabular-nums">
                {amount(row.days_on_hand)} days left, {amount(row.on_hand_units)} on hand,{" "}
                {amount(row.avg_daily_units)} used a day
              </p>
              {(row.supplier || row.unit_price) && (
                <p className="tabular-nums">
                  {row.supplier ?? "No supplier on file"}
                  {row.unit_price ? `, $${amount(row.unit_price)} per unit` : ""}
                </p>
              )}
            </li>
          ))}
        </ul>
      ),
    });
  }
  sources.documents.forEach((doc, index) => {
    entries.push({ id: `P${index + 1}`, kind: "private", name: `Document ${index + 1}`, detail: doc.title });
  });
  if (sources.graph_rows > 0) {
    entries.push({
      id: "G",
      kind: "public",
      name: "Shortage graph",
      detail: `${sources.graph_rows} matching ${sources.graph_rows === 1 ? "drug" : "drugs"} in FDA shortage, manufacturing, and RxNorm data.`,
    });
  }
  sources.labels.forEach((label, index) => {
    entries.push({
      id: `L${index + 1}`,
      kind: "public",
      name: `Label ${index + 1}`,
      detail: `${label.product}, ${label.section}`,
    });
  });
  return entries;
}

function citedIds(answer: string) {
  return new Set(Array.from(answer.matchAll(CITATION_ALL), (match) => match[1]));
}

function EntryItem({ entry }: { entry: Entry }) {
  return (
    <li id={`source-${entry.id}`} data-kind={entry.kind} className="source">
      <p className={`font-medium ${entry.kind === "public" ? "text-public" : "text-private"}`}>{entry.name}</p>
      <div className="mt-0.5 text-muted">{entry.detail}</div>
    </li>
  );
}

function SourceList({ sources, answer }: { sources: Sources; answer: string }) {
  const entries = sourceEntries(sources);
  const cited = citedIds(answer);
  const used = entries.filter((entry) => cited.has(entry.id));
  const other = entries.filter((entry) => !cited.has(entry.id));

  return (
    <aside aria-labelledby="sources-heading" className="text-sm lg:border-l lg:border-rule lg:pl-8">
      <h2 id="sources-heading" className="text-base font-semibold">
        Sources
      </h2>
      {entries.length === 0 && <p className="mt-3 text-muted">No sources were returned with this answer.</p>}
      {entries.length > 0 && used.length === 0 && (
        <p className="mt-3 text-muted">The answer doesn&apos;t cite any of the sources below.</p>
      )}

      {used.length > 0 && (
        <section className="mt-4">
          <h3 className="font-medium text-muted">Cited in this answer</h3>
          <ul className="mt-3 space-y-4">
            {used.map((entry) => (
              <EntryItem key={entry.id} entry={entry} />
            ))}
          </ul>
        </section>
      )}

      {other.length > 0 && (
        <details className="mt-6">
          <summary className="cursor-pointer font-medium text-muted hover:text-ink">
            Also consulted ({other.length})
          </summary>
          <ul className="mt-3 space-y-4">
            {other.map((entry) => (
              <EntryItem key={entry.id} entry={entry} />
            ))}
          </ul>
        </details>
      )}
    </aside>
  );
}

export function Answer({
  answer, cache, traceId, sources,
}: { answer: string; cache: string; traceId: string | null; sources: Sources }) {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <article className="max-w-prose text-[1.0625rem] leading-relaxed">
        <Markdown remarkPlugins={[remarkGfm]} components={components}>
          {answer}
        </Markdown>
        <p className="mt-6 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
          <span>{cache === "hit" ? "Answered from a recent matching question" : "New answer"}</span>
          {traceId && <span>Reference {traceId.slice(0, 8)}</span>}
        </p>
      </article>
      <SourceList sources={sources} answer={answer} />
    </div>
  );
}
