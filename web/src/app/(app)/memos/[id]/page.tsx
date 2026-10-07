import Link from "next/link";
import { Suspense } from "react";
import { notFound, redirect } from "next/navigation";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, ApiError } from "@/lib/api";
import { ReviewForm } from "./review-form";

type Memo = { action_id: number; subject: string; draft: string; status: string; review_note: string | null };

const STATUS: Record<string, string> = {
  pending_approval: "Waiting for review",
  approved: "Approved",
  rejected: "Rejected",
};

const components: Components = {
  h1: ({ children }) => <h2 className="mb-3 mt-8 text-xl font-semibold first:mt-0">{children}</h2>,
  h2: ({ children }) => <h2 className="mb-3 mt-8 text-lg font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-6 font-semibold">{children}</h3>,
  p: ({ children }) => <p className="mb-4">{children}</p>,
  ul: ({ children }) => <ul className="mb-4 list-disc space-y-1.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-4 list-decimal space-y-1.5 pl-5">{children}</ol>,
  table: ({ children }) => (
    <div className="mb-4 overflow-x-auto">
      <table className="w-full text-sm tabular-nums">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b border-ink px-3 py-2 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b border-rule px-3 py-2 align-top">{children}</td>,
  a: ({ children }) => <span>{children}</span>,
};

async function MemoView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const actionId = Number(id);
  if (!Number.isInteger(actionId) || actionId < 1) notFound();

  let memo: Memo;
  try {
    memo = await api<Memo>(`/memos/${actionId}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <article className="max-w-3xl">
      <Link href="/memos" className="text-sm text-public underline decoration-rule underline-offset-4">
        All memos
      </Link>
      <h1 className="mt-4 text-[1.75rem] font-semibold leading-tight tracking-tight">{memo.subject}</h1>
      <p className="mt-2 text-sm text-muted">{STATUS[memo.status] ?? memo.status}</p>
      {memo.review_note && (
        <div className="mt-6 border-l-2 border-caution-mark pl-4">
          <p className="text-sm font-medium">Reviewer note</p>
          <p className="mt-1 leading-relaxed">{memo.review_note}</p>
        </div>
      )}
      <div className="mt-8 leading-relaxed">
        <Markdown remarkPlugins={[remarkGfm]} components={components}>
          {memo.draft}
        </Markdown>
      </div>
      {memo.status === "pending_approval" && <ReviewForm actionId={memo.action_id} />}
    </article>
  );
}

export default function MemoPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<p className="text-muted">Loading memo...</p>}>
      <MemoView params={params} />
    </Suspense>
  );
}
