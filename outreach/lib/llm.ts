// All "intelligent" steps go through here. Each function shells out to
// `claude -p` (headless Claude Code — rides the user's existing subscription
// auth, no API key) and returns a zod-validated PROPOSAL. Nothing in this
// module may mark a draft as passed/approved or trigger a send — that is the
// rigid layer's job (lint.ts, routes, cron).

import "server-only";
import { spawn } from "child_process";
import { z } from "zod";

const CLAUDE_BIN = process.env.CLAUDE_BIN ?? "claude";
const TIMEOUT_MS = 180_000;

function runClaude(prompt: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(CLAUDE_BIN, ["-p", "--output-format", "json"], {
      stdio: ["pipe", "pipe", "pipe"],
      timeout: TIMEOUT_MS,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        return reject(new Error(`claude -p exited ${code}: ${stderr.slice(0, 500)}`));
      }
      try {
        const envelope = JSON.parse(stdout);
        if (envelope.is_error) return reject(new Error(`claude -p error: ${envelope.result}`));
        resolve(envelope.result as string);
      } catch {
        reject(new Error(`claude -p returned unparseable output: ${stdout.slice(0, 500)}`));
      }
    });
    child.stdin.write(prompt);
    child.stdin.end();
  });
}

// Parse the model's text as JSON (tolerating markdown fences), then validate.
function parseModelJson<T>(schema: z.ZodType<T>, text: string): T {
  const stripped = text
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "");
  return schema.parse(JSON.parse(stripped));
}

async function ask<T>(schema: z.ZodType<T>, prompt: string): Promise<T> {
  const text = await runClaude(prompt);
  try {
    return parseModelJson(schema, text);
  } catch {
    // One retry with the error surfaced; if it fails again, let it throw.
    const retry = await runClaude(
      `${prompt}\n\nYour previous reply was not valid JSON matching the required shape. Reply again with ONLY the JSON.`
    );
    return parseModelJson(schema, retry);
  }
}

const JD_JSON = `{"company_name": string, "role_title": string, "email_domain": string | null, "requirements": string[]}`;

const ParsedJd = z.object({
  company_name: z.string(),
  role_title: z.string(),
  email_domain: z.string().nullable(),
  requirements: z.array(z.string()),
});
export type ParsedJd = z.infer<typeof ParsedJd>;

export function parseJd(jdText: string): Promise<ParsedJd> {
  return ask(
    ParsedJd,
    `Parse this job description. Reply with ONLY a JSON object, no prose, shaped exactly:
${JD_JSON}

- company_name: the hiring company's common name
- role_title: the job title as posted
- email_domain: your best hypothesis for the company's corporate email domain (e.g. "stripe.com"), or null if you can't guess
- requirements: 3-8 key requirements/qualifications, each a short phrase

Job description:
"""
${jdText}
"""`
  );
}

const PEOPLE_JSON = `{"people": [{"name": string, "title": string | null, "company": string | null, "linkedin_url": string}]}`;

const ExtractedPeople = z.object({
  people: z.array(
    z.object({
      name: z.string(),
      title: z.string().nullable(),
      company: z.string().nullable(),
      linkedin_url: z.string(),
    })
  ),
});
export type ExtractedPerson = z.infer<typeof ExtractedPeople>["people"][number];

export async function extractPeople(text: string): Promise<ExtractedPerson[]> {
  const result = await ask(
    ExtractedPeople,
    `Extract every person from this freeform pasted text (copied from LinkedIn — may be messy). Reply with ONLY a JSON object, no prose, shaped exactly:
${PEOPLE_JSON}

- Include a person only if a linkedin.com/in/... URL can be found for them
- title: their current job title if present, else null
- company: their current company name if present, else null
- Do not invent URLs or people

Pasted text:
"""
${text}
"""`
  );
  return result.people;
}

const TARGETS_JSON = `{"targets": [{"linkedin_url": string, "relevance_score": number, "relevance_reason": string}]}`;

const SelectedTargets = z.object({
  targets: z.array(
    z.object({
      linkedin_url: z.string(),
      relevance_score: z.number(),
      relevance_reason: z.string(),
    })
  ),
});
export type SelectedTarget = z.infer<typeof SelectedTargets>["targets"][number];

const PURPOSE_HINT: Record<string, string> = {
  referral: "asking for a referral — peers/engineers at the company are ideal",
  recruiter_followup: "following up with recruiters — recruiters/talent/sourcing roles are ideal",
  hiring_manager_intro: "introducing yourself to the hiring manager — managers/leads on the relevant team are ideal",
};

export async function selectTargets(input: {
  company: string;
  roleTitle: string;
  purpose: string;
  requirements: string[];
  people: { name: string; title: string | null; company: string | null; linkedin_url: string }[];
}): Promise<SelectedTarget[]> {
  const result = await ask(
    SelectedTargets,
    `I'm doing job outreach for the ${input.roleTitle} role at ${input.company}. Purpose: ${input.purpose} (${PURPOSE_HINT[input.purpose] ?? input.purpose}).
Key requirements: ${input.requirements.join("; ")}

Below is my saved list of LinkedIn people. Select ONLY the ones relevant to contact for this campaign (right company — match company names loosely, e.g. subsidiaries/short forms — and a role that fits the purpose). Rank them. Reply with ONLY a JSON object, no prose, shaped exactly:
${TARGETS_JSON}

- linkedin_url: copied EXACTLY from the list below
- relevance_score: 0-100, higher = better target
- relevance_reason: one short sentence on why this person, mentioning their role
- Return them best-first. Exclude people at other companies or irrelevant to the purpose.

People:
${JSON.stringify(input.people, null, 2)}`
  );
  return result.targets;
}
