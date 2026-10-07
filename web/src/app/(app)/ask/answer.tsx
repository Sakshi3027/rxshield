"use client";

import { Children, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Sources } from "./actions";

const CITATION_SPLIT = /(\[(?:G|H|L\d+|P\d+)\])/g;
const CITATION_ONLY = /^\[(G|H|L\d+|P\d+)\]$/;

function describe(id: string) {
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

function SourceList({ sources }: { sources: Sources }) {
  const empty =
    !sources.graph_rows && !sources.inventory.length && !sources.labels.length && !sources.documents.length;
  return (
    <aside aria-labelledby="sources-heading" className="text-sm lg:border-l lg:border-rule lg:pl-8">
      <h2 id="sources-heading" className="text-base font-semibold">
        Sources
      </h2>
      {empty && <p className="mt-3 text-muted">No sources were returned with this answer.</p>}

      {sources.inventory.length > 0 && (
        <section id="source-H" data-kind="private" className="source mt-6">
          <h3 className="font-medium text-private">Your inventory</h3>
          <ul className="mt-2 space-y-3">
            {sources.inventory.map((row) => (
              <li key={String(row.drug_rxcui)}>
                <p className="font-medium">{row.drug_name}</p>
                <p className="tabular-nums text-muted">
                  {amount(row.days_on_hand)} days left, {amount(row.on_hand_units)} on hand,{" "}
                  {amount(row.avg_daily_units)} used a day
                </p>
                {(row.supplier || row.unit_price) && (
                  <p className="tabular-nums text-muted">
                    {row.supplier ?? "No supplier on file"}
                    {row.unit_price ? `, $${amount(row.unit_price)} per unit` : ""}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {sources.documents.length > 0 && (
        <section className="mt-6">
          <h3 className="font-medium text-private">Your hospital&apos;s documents</h3>
          <ol className="mt-2 space-y-2">
            {sources.documents.map((doc, index) => (
              <li key={index} id={`source-P${index + 1}`} data-kind="private" className="source">
                <span className="font-medium text-private">Document {index + 1}</span> {doc.title}
              </li>
            ))}
          </ol>
        </section>
      )}

      {sources.graph_rows > 0 && (
        <section id="source-G" data-kind="public" className="source mt-6">
          <h3 className="font-medium text-public">Shortage graph</h3>
          <p className="mt-1 text-muted">
            {sources.graph_rows} matching {sources.graph_rows === 1 ? "drug" : "drugs"} in FDA shortage,
            manufacturing, and RxNorm data.
          </p>
        </section>
      )}

      {sources.labels.length > 0 && (
        <section className="mt-6">
          <h3 className="font-medium text-public">FDA labels</h3>
          <ol className="mt-2 space-y-2">
            {sources.labels.map((label, index) => (
              <li key={index} id={`source-L${index + 1}`} data-kind="public" className="source">
                <span className="font-medium text-public">Label {index + 1}</span> {label.product},{" "}
                {label.section}
              </li>
            ))}
          </ol>
        </section>
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
      <SourceList sources={sources} />
    </div>
  );
}
