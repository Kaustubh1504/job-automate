// Equal distribution of people across sending accounts.
//
// Assignment is sticky per person and happens once, at CSV import: a reply
// lands in whichever mailbox sent the message, so a person's follow-ups have
// to come from the same account as their first email. Balancing therefore has
// to happen when people are added, not when mail goes out.
//
// `existingCounts` is how many people each account already owns, so balance
// holds across repeated uploads rather than only within one CSV.

export function assignSenders(
  addresses: string[],
  existingCounts: Record<string, number>,
  count: number
): string[] {
  if (addresses.length === 0) throw new Error("No sending accounts configured");

  const counts = new Map(addresses.map((a) => [a, existingCounts[a] ?? 0]));
  const assigned: string[] = [];

  for (let i = 0; i < count; i++) {
    // Fewest-first; ties break on the account order from .env, which keeps
    // the result deterministic for a given input.
    let pick = addresses[0];
    for (const address of addresses) {
      if (counts.get(address)! < counts.get(pick)!) pick = address;
    }
    counts.set(pick, counts.get(pick)! + 1);
    assigned.push(pick);
  }

  return assigned;
}
