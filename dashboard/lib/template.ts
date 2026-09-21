// Merge-field rendering. Deliberately dumb string replacement -- no LLM in the
// send path, so what you preview is exactly what goes out.

export type MergeFields = {
  name: string;
  email: string;
  title: string | null;
  company: string | null;
};

export const MERGE_FIELDS = ["first_name", "name", "email", "title", "company"] as const;

export function render(template: string, person: MergeFields): string {
  const values: Record<string, string> = {
    first_name: person.name.trim().split(/\s+/)[0] ?? "",
    name: person.name,
    email: person.email,
    title: person.title ?? "",
    company: person.company ?? "",
  };
  return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, key: string) =>
    key in values ? values[key] : match
  );
}

// Placeholders in the template that aren't merge fields -- surfaced in the UI
// so a typo like {{firstname}} doesn't silently ship as literal text.
export function unknownFields(template: string): string[] {
  const found = [...template.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]);
  return [...new Set(found.filter((f) => !MERGE_FIELDS.includes(f as never)))];
}
