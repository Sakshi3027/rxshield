"use server";

import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export type DrugImpact = {
  drug_rxcui: string;
  drug_name: string;
  status: "lost" | "partial";
  p_stockout: number;
  median_days_to_runout: number | null;
  patients?: number;
  patients_at_risk?: number;
  icu_patients?: number;
};

export type ScenarioState =
  | { status: "idle" }
  | {
      status: "done";
      scope: string;
      entity: string;
      entityName: string;
      days: number;
      patients: number | null;
      drugs: DrugImpact[];
    }
  | { status: "failed"; message: string; traceId: string | null };

type WhatIfResponse = {
  scope: string;
  entity: string;
  entity_name: string;
  duration_days: number;
  patients_affected: number | null;
  drugs: DrugImpact[];
};

const MESSAGES: Record<number, string> = {
  403: "Your role can't run supply simulations. Pharmacists, procurement, and executives can.",
  422: "Check the scenario: choose a scope, enter a code such as IND, and a duration from 1 to 365 days.",
  503: "The simulation service is unavailable right now. Try again in a few minutes.",
};

export async function runScenario(_previous: ScenarioState, formData: FormData): Promise<ScenarioState> {
  const scope = String(formData.get("scope") ?? "country");
  const entity = String(formData.get("entity") ?? "").trim();
  const days = Number(formData.get("days") ?? 60);
  try {
    const data = await api<WhatIfResponse>("/simulations/whatif", {
      method: "POST",
      body: JSON.stringify({ scope, entity, duration_days: days }),
    });
    return {
      status: "done",
      scope: data.scope,
      entity: data.entity,
      entityName: data.entity_name,
      days: data.duration_days,
      patients: data.patients_affected,
      drugs: data.drugs,
    };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) redirect("/login");
    return {
      status: "failed",
      message: MESSAGES[error.status] ?? "Something went wrong while running the simulation.",
      traceId: error.traceId ?? null,
    };
  }
}
