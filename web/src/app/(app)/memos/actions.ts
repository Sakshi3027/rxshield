"use server";

import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export type DraftState =
  | { status: "idle" }
  | { status: "failed"; message: string; problems: string[]; traceId: string | null };

export type ReviewState = { status: "idle" } | { status: "failed"; message: string };

type DraftResponse = { action_id: number; status: string; draft: string; attempts: number };

const DRAFT_MESSAGES: Record<number, string> = {
  400: "RxShield couldn't draft a memo for that request. Check the ingredient name.",
  403: "Your role can't draft shortage memos.",
  503: "The drafting service is unavailable right now. Try again in a few minutes.",
};

export async function draftMemo(_previous: DraftState, formData: FormData): Promise<DraftState> {
  const ingredient = String(formData.get("ingredient") ?? "").trim().toLowerCase();
  let actionId: number;
  try {
    const data = await api<DraftResponse>("/memos", { method: "POST", body: JSON.stringify({ ingredient }) });
    actionId = data.action_id;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) redirect("/login");
    const traceId = error.traceId ?? null;
    const details = error.details as { error?: string; problems?: string[] } | undefined;
    if (error.status === 422 && details?.error === "draft_failed_validation") {
      return {
        status: "failed",
        message: "The draft didn't pass RxShield's checks, so it wasn't saved.",
        problems: details.problems ?? [],
        traceId,
      };
    }
    if (error.status === 422) {
      return {
        status: "failed",
        message: "Enter an ingredient name using letters, spaces, or hyphens, such as rocuronium.",
        problems: [],
        traceId,
      };
    }
    return {
      status: "failed",
      message: DRAFT_MESSAGES[error.status] ?? "Something went wrong while drafting.",
      problems: [],
      traceId,
    };
  }
  redirect(`/memos/${actionId}`);
}

export async function reviewMemo(actionId: number, _previous: ReviewState, formData: FormData): Promise<ReviewState> {
  const decision = String(formData.get("decision") ?? "");
  const note = String(formData.get("note") ?? "").trim();
  if (decision === "rejected" && !note) {
    return { status: "failed", message: "Add a note saying what needs to change before rejecting." };
  }
  try {
    await api(`/memos/${actionId}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, note: note || null }),
    });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) redirect("/login");
    if (error.status === 403) {
      return {
        status: "failed",
        message:
          "You can't review this memo. Memos are reviewed by an executive other than the person who drafted them, and only once.",
      };
    }
    return { status: "failed", message: "Something went wrong while saving your review." };
  }
  redirect(`/memos/${actionId}`);
}
