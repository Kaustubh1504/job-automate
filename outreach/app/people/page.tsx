"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type Person = {
  id: string;
  name: string;
  title: string | null;
  linkedin_url: string;
  email: string | null;
  email_status: string;
  company: { name: string } | null;
};

export default function PeoplePage() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [people, setPeople] = useState<Person[]>([]);

  const refresh = useCallback(async () => {
    const res = await fetch("/api/people");
    const body = await res.json();
    if (res.ok) setPeople(body.people);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function submit() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const res = await fetch("/api/people", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? res.statusText);
      setStatus(`Extracted ${body.extracted} — saved ${body.inserted} new, skipped ${body.skipped} duplicates`);
      setText("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Add people</CardTitle>
          <CardDescription>
            Paste a freeform block of LinkedIn people (search results, profile blurbs — sloppy is
            fine). Claude extracts name/title/URL; duplicates are skipped on the profile URL.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="min-h-40 w-full rounded-md border bg-transparent p-3 text-sm"
            placeholder={"Jane Doe · Senior Recruiter at Acme\nhttps://www.linkedin.com/in/janedoe\n..."}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <Button onClick={submit} disabled={busy || !text.trim()}>
              {busy ? "Extracting…" : "Extract & save"}
            </Button>
            {status && <span className="text-sm text-muted-foreground">{status}</span>}
            {error && <span className="text-sm text-destructive">{error}</span>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Saved people ({people.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {people.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing saved yet.</p>
          ) : (
            <ul className="divide-y">
              {people.map((p) => (
                <li key={p.id} className="flex items-center gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{p.name}</span>
                      {p.company && <Badge variant="secondary">{p.company.name}</Badge>}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {p.title ?? "—"} ·{" "}
                      <a className="underline" href={p.linkedin_url} target="_blank" rel="noreferrer">
                        {p.linkedin_url.replace("https://www.linkedin.com/in/", "in/")}
                      </a>
                    </div>
                  </div>
                  {p.email && (
                    <span className="text-xs text-muted-foreground">
                      {p.email} <Badge variant="outline">{p.email_status}</Badge>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
