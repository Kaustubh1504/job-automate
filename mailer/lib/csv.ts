// CSV intake. Rows are expected to carry a LinkedIn URL and an already-verified
// email; linkedin_url is the dedup key, so re-uploading a CSV updates people in
// place rather than duplicating them.

import Papa from "papaparse";

export type CsvPerson = {
  name: string;
  email: string;
  linkedin_url: string;
  company: string | null;
  title: string | null;
};

export type CsvResult = {
  people: CsvPerson[];
  skipped: { row: number; reason: string }[];
};

// Header aliases, since export tools disagree on naming.
const FIELDS: Record<keyof CsvPerson, string[]> = {
  name: ["name", "full name", "full_name", "fullname"],
  email: ["email", "email address", "email_address", "verified email", "verified_email"],
  linkedin_url: ["linkedin url", "linkedin_url", "linkedin", "linkedinurl", "profile url", "profile_url"],
  company: ["company", "company name", "company_name", "organization", "employer"],
  title: ["title", "role", "position", "job title", "job_title"],
};

function pick(row: Record<string, string>, field: keyof CsvPerson): string | null {
  for (const alias of FIELDS[field]) {
    const value = row[alias];
    if (value && value.trim()) return value.trim();
  }
  return null;
}

export function parseCsv(text: string): CsvResult {
  const parsed = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) => h.trim().toLowerCase(),
  });

  const people: CsvPerson[] = [];
  const skipped: CsvResult["skipped"] = [];

  parsed.data.forEach((row, index) => {
    const name = pick(row, "name");
    const email = pick(row, "email");
    const linkedin_url = pick(row, "linkedin_url");

    // Every row needs all three: linkedin_url dedups, email is the destination,
    // name fills the {{first_name}} merge field.
    const missing = [
      !name && "name",
      !email && "email",
      !linkedin_url && "linkedin_url",
    ].filter(Boolean);

    if (missing.length > 0) {
      skipped.push({ row: index + 2, reason: `missing ${missing.join(", ")}` });
      return;
    }

    people.push({
      name: name!,
      email: email!,
      linkedin_url: linkedin_url!,
      company: pick(row, "company"),
      title: pick(row, "title"),
    });
  });

  return { people, skipped };
}
