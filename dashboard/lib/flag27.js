// Fire-and-forget ping to the Summer 2027 Discord channel when a role is
// flagged. Called from each view's toggle the moment Flag27 flips on. The
// webhook secret lives in the server route (/api/flag27), never the client.
// Failures are swallowed so a notify hiccup never blocks the checkbox.
export function notifyFlag27(job) {
  fetch('/api/flag27', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      company: job.company,
      title: job.title,
      location: job.location,
      url: job.apply_url,
    }),
  }).catch(() => {});
}
