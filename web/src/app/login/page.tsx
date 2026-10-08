"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Scope = { label: string; kind: "public" | "private" };

const PERSONAS: { userId: string; role: string; detail: string; scopes: Scope[] }[] = [
  {
    userId: "northshore-pharmacist",
    role: "Pharmacist",
    detail: "Inventory, protocols, and patient impact. Drafts shortage memos.",
    scopes: [{ label: "FDA data", kind: "public" }, { label: "Inventory", kind: "private" }, { label: "Protocols", kind: "private" }],
  },
  {
    userId: "northshore-procurement",
    role: "Procurement",
    detail: "Inventory, contracts, and pricing. Drafts shortage memos.",
    scopes: [{ label: "FDA data", kind: "public" }, { label: "Inventory", kind: "private" }, { label: "Contracts", kind: "private" }],
  },
  {
    userId: "northshore-clinician",
    role: "Clinician",
    detail: "Clinical protocols only. No inventory or pricing.",
    scopes: [{ label: "FDA data", kind: "public" }, { label: "Protocols", kind: "private" }],
  },
  {
    userId: "northshore-executive",
    role: "Executive",
    detail: "Everything, plus approving memos drafted by others.",
    scopes: [{ label: "FDA data", kind: "public" }, { label: "All hospital data", kind: "private" }],
  },
];

function ScopeChip({ scope }: { scope: Scope }) {
  const tone = scope.kind === "public" ? "bg-public-soft text-public" : "bg-private-soft text-private";
  return <span className={`rounded px-1.5 text-xs font-medium leading-5 ${tone}`}>{scope.label}</span>;
}

export default function LoginPage() {
  const router = useRouter();
  const [userId, setUserId] = useState(PERSONAS[0].userId);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId, password }),
      });
      if (!response.ok) {
        setError("Invalid user or password.");
        return;
      }
      router.push("/");
      router.refresh();
    } catch {
      setError("RxShield is unreachable right now. Try again in a moment.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto grid min-h-screen max-w-5xl content-center gap-12 px-6 py-12 lg:grid-cols-[1fr_26rem] lg:gap-16">
      <section className="max-w-md self-center">
        <p className="text-sm font-medium text-public">RxShield</p>
        <h1 className="mt-3 text-3xl font-semibold leading-tight text-ink">
          Drug shortage intelligence for Northshore Health
        </h1>
        <p className="mt-4 leading-relaxed text-muted">
          Answers combine public FDA shortage, label, and manufacturing data with the hospital&apos;s own inventory
          and protocols. Every claim links to its source, and each role sees only what its permissions allow.
        </p>
        <dl className="mt-8 space-y-2 text-sm">
          <div className="flex items-center gap-3">
            <dt className="h-2.5 w-2.5 rounded-full bg-public" aria-hidden="true" />
            <dd className="text-muted">Public evidence from FDA and RxNorm</dd>
          </div>
          <div className="flex items-center gap-3">
            <dt className="h-2.5 w-2.5 rounded-full bg-private" aria-hidden="true" />
            <dd className="text-muted">Private evidence from your hospital</dd>
          </div>
        </dl>
      </section>

      <form onSubmit={submit} className="rounded-xl border border-rule bg-surface p-6 sm:p-8">
        <fieldset>
          <legend className="text-base font-semibold text-ink">Sign in as</legend>
          <div className="mt-4 space-y-2">
            {PERSONAS.map((persona) => {
              const selected = userId === persona.userId;
              return (
                <label
                  key={persona.userId}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                    selected ? "border-ink" : "border-rule hover:border-muted"
                  }`}
                >
                  <input
                    type="radio"
                    name="persona"
                    value={persona.userId}
                    checked={selected}
                    onChange={() => setUserId(persona.userId)}
                    className="mt-1 accent-public"
                  />
                  <span>
                    <span className="block text-sm font-medium text-ink">{persona.role}</span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-muted">{persona.detail}</span>
                    <span className="mt-2 flex flex-wrap gap-1.5">
                      {persona.scopes.map((scope) => (
                        <ScopeChip key={scope.label} scope={scope} />
                      ))}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <label className="mt-6 block">
          <span className="text-sm font-medium text-ink">Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1.5 w-full rounded-lg border border-rule bg-paper px-3 py-2 text-ink outline-none focus:border-public"
            required
          />
        </label>

        {error && (
          <p role="alert" className="mt-4 rounded-lg bg-caution-soft px-3 py-2 text-sm text-caution">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={pending}
          className="mt-6 w-full rounded-lg bg-ink py-2.5 font-medium text-paper transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
