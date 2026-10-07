"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const PERSONAS = [
  { userId: "northshore-pharmacist", role: "Pharmacist", detail: "Inventory, protocols, patient impact" },
  { userId: "northshore-procurement", role: "Procurement", detail: "Inventory, contracts, pricing" },
  { userId: "northshore-clinician", role: "Clinician", detail: "Clinical protocols only" },
  { userId: "northshore-executive", role: "Executive", detail: "Everything, plus memo approval" },
];

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
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId, password }),
    });
    setPending(false);
    if (!response.ok) {
      setError("Invalid user or password.");
      return;
    }
    router.push("/");
    router.refresh();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <h1 className="text-2xl font-semibold">RxShield</h1>
      <p className="mt-1 text-sm text-neutral-500">Drug shortage intelligence for Northshore Health</p>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Sign in as</legend>
          {PERSONAS.map((persona) => (
            <label
              key={persona.userId}
              className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${
                userId === persona.userId ? "border-neutral-900" : "border-neutral-200"
              }`}
            >
              <input
                type="radio"
                name="persona"
                value={persona.userId}
                checked={userId === persona.userId}
                onChange={() => setUserId(persona.userId)}
                className="mt-1"
              />
              <span>
                <span className="block text-sm font-medium">{persona.role}</span>
                <span className="block text-xs text-neutral-500">{persona.detail}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <label className="block">
          <span className="text-sm font-medium">Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-lg border border-neutral-300 px-3 py-2"
            required
          />
        </label>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-lg bg-neutral-900 py-2 text-white disabled:opacity-50"
        >
          {pending ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
