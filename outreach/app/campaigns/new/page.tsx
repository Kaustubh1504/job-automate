"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const PURPOSES = [
  { value: "referral", label: "Referral", hint: "ask an employee to refer you" },
  { value: "recruiter_followup", label: "Recruiter follow-up", hint: "follow up on an application" },
  { value: "hiring_manager_intro", label: "Hiring manager intro", hint: "introduce yourself to the manager" },
];

export default function NewCampaignPage() {
  const router = useRouter();
  const [jd, setJd] = useState("");
  const [purpose, setPurpose] = useState("referral");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/campaigns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd_text: jd, purpose }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? res.statusText);
      router.push(`/campaigns/${body.campaign_id}/review`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New campaign</CardTitle>
        <CardDescription>
          Paste the job description. Claude parses the company, role, and requirements, then you
          pick targets on the next screen.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <textarea
          className="min-h-72 w-full rounded-md border bg-transparent p-3 text-sm"
          placeholder="Paste the full job description here…"
          value={jd}
          onChange={(e) => setJd(e.target.value)}
        />
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Purpose</legend>
          {PURPOSES.map((p) => (
            <label key={p.value} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name="purpose"
                value={p.value}
                checked={purpose === p.value}
                onChange={() => setPurpose(p.value)}
              />
              <span className="font-medium">{p.label}</span>
              <span className="text-muted-foreground">— {p.hint}</span>
            </label>
          ))}
        </fieldset>
        <div className="flex items-center gap-3">
          <Button onClick={submit} disabled={busy || !jd.trim()}>
            {busy ? "Parsing JD…" : "Create campaign"}
          </Button>
          {error && <span className="text-sm text-destructive">{error}</span>}
        </div>
      </CardContent>
    </Card>
  );
}
