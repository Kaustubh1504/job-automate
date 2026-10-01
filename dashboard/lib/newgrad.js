// What counts as New Grad, defined once and used by every view that shows it.
//
//   GitHub repos  -- the two new-grad listing repos (the intern repos are not)
//   Built In      -- its search URL is filtered to internship + entry-level, so
//                    any non-intern title from it is entry-level by construction
//
// An intern title is excluded up front, whatever the source said.
//   LinkedIn      -- JobSpy's linkedin rows that the scraper bucketed as newgrad
//                    (jobspy_jobs carries its own role_type; `jobs` does not)
//   jobhive       -- roles Claude judged this candidate eligible for
//                    (engine/llm_fit.py); roles refusing visa sponsorship are
//                    excluded there. Falls back to the years engine/yoe.py read
//                    out of the JD when a row wasn't judged.
//
// Anything else -- intern repos, Jobright, Wellfound, Nokia, Handshake -- has
// its own tab and is deliberately not folded in here.

export const MAX_YEARS_EXP = 2;

// Interns have their own tab, so they never count as New Grad no matter how a
// source labels them. Exported so the job table buckets on the same regex.
export const INTERN_RE = /\bintern(ship)?\b/i;

const NEWGRAD_REPOS = new Set(['simplify-newgrad', 'vansh-newgrad']);

export function isNewGrad(r) {
  const source = (r.source || '').toLowerCase();

  if (NEWGRAD_REPOS.has(source)) return true;
  if (INTERN_RE.test(r.title || '')) return false;

  if (source.startsWith('builtin')) return true;
  if (source === 'jobhive') {
    // Haiku's verdict wins where it judged the row -- it reads the whole posting,
    // so it catches junior roles whose JD never states a number. A null verdict
    // means NOT JUDGED (no key, call failed, over the run's ceiling), not "no",
    // so fall back to the number engine/yoe.py read out of the text.
    if (r.llm_junior_ok != null) return r.llm_junior_ok;
    // null years means the JD never stated one, which is not the same as 0 --
    // those stay out rather than being assumed junior.
    return r.min_years_exp != null && r.min_years_exp <= MAX_YEARS_EXP;
  }
  // Only jobspy_jobs rows have `site`; the scraper already split intern/newgrad.
  if (r.site) return String(r.site).toLowerCase().includes('linkedin') && r.role_type === 'newgrad';

  return false;
}
