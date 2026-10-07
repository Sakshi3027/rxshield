import Link from "next/link";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { DraftForm } from "./draft-form";

type Pending = { action_id: number; subject: string; created_by: string; created_at: string };

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

async function PendingList() {
  let memos: Pending[];
  try {
    memos = (await api<{ memos: Pending[] }>("/memos/pending")).memos;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) {
      return <p className="mt-3 text-muted">Your role doesn&apos;t review memos.</p>;
    }
    throw error;
  }
  if (memos.length === 0) {
    return <p className="mt-3 text-muted">No memos are waiting for review.</p>;
  }
  return (
    <ul className="mt-3 divide-y divide-rule border-y border-rule">
      {memos.map((memo) => (
        <li key={memo.action_id}>
          <Link
            href={`/memos/${memo.action_id}`}
            className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-3 hover:text-public"
          >
            <span className="font-medium">{memo.subject}</span>
            <span className="text-sm text-muted">
              Drafted by {memo.created_by} on {formatDate(memo.created_at)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function MemosPage() {
  return (
    <section className="max-w-3xl">
      <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">Shortage memos</h1>
      <p className="mt-2 leading-relaxed text-muted">
        The agent drafts a memo from your inventory, protocols, and FDA data, and checks every number against its
        sources. An executive who didn&apos;t write it approves or rejects it before it goes out.
      </p>
      <DraftForm />
      <h2 className="mt-14 text-base font-semibold">Waiting for review</h2>
      <Suspense fallback={<p className="mt-3 text-muted">Loading memos...</p>}>
        <PendingList />
      </Suspense>
    </section>
  );
}
