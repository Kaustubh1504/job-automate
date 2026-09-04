// STUB — verification will be implemented later. Do not build it now.
// All email resolution must route through this function so the real
// implementation (Hunter.io etc.) drops in with zero refactoring.
// 'unverified' means "allowed to proceed" for now.
export async function verifyEmail(email: string): Promise<{
  status: "valid" | "invalid" | "catch_all" | "unknown" | "unverified";
  confidence: number | null;
}> {
  return { status: "unverified", confidence: null }; // pass-through for now
}
