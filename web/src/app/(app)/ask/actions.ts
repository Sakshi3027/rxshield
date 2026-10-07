"use server";

import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export type Sources = {
  labels: { product: string | null; section: string | null }[];
  documents: { title: string | null; type: string | null }[];
  inventory: Record<string, string | number | null>[];
  graph_rows: number;
};

export type AskState =
  | { status: "idle" }
  | { status: "answered"; question: string; answer: string; cache: string; traceId: string | null; sources: Sources }
  | { status: "failed"; question: string; message: string; traceId: string | null };

type AskResponse = { answer: string; cache: string; trace_id: string | null; sources: Sources };

const MESSAGES: Record<number, string> = {
  403: "Your role doesn't have access to the information this question needs.",
  422: "RxShield's data can't answer that. Try naming a drug on your formulary, a manufacturer, or a country.",
  429: "You've asked several questions in the last minute. Wait a moment, then ask again.",
  503: "The answer service is unavailable right now. Try again in a few minutes.",
};

export async function ask(_previous: AskState, formData: FormData): Promise<AskState> {
  const question = String(formData.get("question") ?? "").trim();
  if (question.length < 3 || question.length > 500) {
    return { status: "failed", question, message: "Ask a question between 3 and 500 characters long.", traceId: null };
  }
  try {
    const data = await api<AskResponse>("/ask", { method: "POST", body: JSON.stringify({ question }) });
    return {
      status: "answered", question, answer: data.answer, cache: data.cache,
      traceId: data.trace_id, sources: data.sources,
    };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) redirect("/login");
    return {
      status: "failed", question,
      message: MESSAGES[error.status] ?? "Something went wrong while answering.",
      traceId: error.traceId ?? null,
    };
  }
}
