// Rigid: canonicalize LinkedIn profile URLs so dedup on linkedin_url works
// regardless of how sloppily they were pasted.
export function normalizeLinkedinUrl(url: string): string | null {
  const match = url.match(/linkedin\.com\/in\/([^/?#\s]+)/i);
  if (!match) return null;
  return `https://www.linkedin.com/in/${match[1].toLowerCase()}`;
}
