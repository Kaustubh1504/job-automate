"use client";

import { use, useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type Target = {
  id: string;
  selected: boolean;
  relevance_score: number | null;
  relevance_reason: string | null;
  person: { id: string; name: string; title: string | null; linkedin_url: string; email: string | null; email_status: string };
};

type Campaign = {
  id: string;
  role_title: string | null;
  purpose: string;
  parsed_requirements: string[] | null;
  company: { id: string; name: string } | null;
};

export default function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const res = await fetch(`/api/campaigns/${id}/targets`);
    const body = await res.json();
    if (!res.ok) {
      setError(body.error ?? res.statusText);
      return;
    }
    setCampaign(body.campaign);
    setTargets(body.targets);
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function generateTargets() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/campaigns/${id}/targets`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? res.statusText);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(target: Target) {
    // optimistic flip; user override is the final word on inclusion
    setTargets((ts) => ts.map((t) => (t.id === target.id ? { ...t, selected: !t.selected } : t)));
    await fetch(`/api/targets/${target.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected: !target.selected }),
    });
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            {campaign ? `${campaign.role_title ?? "Role"} @ ${campaign.company?.name ?? "?"}` : "Loading…"}
          </CardTitle>
          {campaign && (
            <CardDescription>
              Purpose: <Badge variant="secondary">{campaign.purpose}</Badge>
              {campaign.parsed_requirements && campaign.parsed_requirements.length > 0 && (
                <span className="mt-1 block">{campaign.parsed_requirements.join(" · ")}</span>
              )}
            </CardDescription>
          )}
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Targets</CardTitle>
          <CardDescription>
            Claude shortlists relevant people from your saved list with a one-line reason each. You
            have the final say — untick anyone you don&apos;t want contacted.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <Button onClick={generateTargets} disabled={busy}>
              {busy ? "Selecting…" : targets.length > 0 ? "Re-run selection" : "Select targets"}
            </Button>
            {error && <span className="text-sm text-destructive">{error}</span>}
          </div>
          {targets.length > 0 && (
            <ul className="divide-y">
              {targets.map((t) => (
                <li key={t.id} className="flex items-start gap-3 py-3">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={t.selected}
                    onChange={() => toggle(t)}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{t.person.name}</span>
                      {t.relevance_score !== null && <Badge variant="outline">{t.relevance_score}</Badge>}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {t.person.title ?? "—"} ·{" "}
                      <a className="underline" href={t.person.linkedin_url} target="_blank" rel="noreferrer">
                        profile
                      </a>
                    </div>
                    {t.relevance_reason && <p className="mt-1 text-sm">{t.relevance_reason}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Drafts</CardTitle>
          <CardDescription>
            Coming in the next build step: drafts are generated for the ticked targets, pass the
            rigid linter, and land here for your approval.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
