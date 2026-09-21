import { NextResponse } from "next/server";
import { addAccount, listAccounts, listAddresses, removeAccount } from "@/lib/accounts";
import { requireUser, UnauthorizedError } from "@/lib/auth";
import { verifyAccount } from "@/lib/gmail";

function fail(err: unknown) {
  if (err instanceof UnauthorizedError) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  return NextResponse.json(
    { error: err instanceof Error ? err.message : String(err) },
    { status: 500 }
  );
}

// Addresses only. The passwords never leave the server.
export async function GET() {
  try {
    const user = await requireUser();
    return NextResponse.json({ accounts: await listAddresses(user.id) });
  } catch (err) {
    return fail(err);
  }
}

export async function POST(request: Request) {
  try {
    const user = await requireUser();
    const { address, appPassword } = await request.json();
    if (!address?.trim() || !appPassword?.trim()) {
      return NextResponse.json({ error: "Address and app password are required" }, { status: 400 });
    }

    await addAccount(user.id, address.trim(), appPassword.trim());

    // Confirm the credentials actually work now, rather than at send time.
    const stored = (await listAccounts(user.id)).find((a) => a.address === address.trim())!;
    const smtpError = await verifyAccount(stored);
    if (smtpError) {
      await removeAccount(user.id, stored.id);
      return NextResponse.json({ error: `Gmail rejected it: ${smtpError}` }, { status: 400 });
    }

    return NextResponse.json({ accounts: await listAddresses(user.id) });
  } catch (err) {
    return fail(err);
  }
}

export async function DELETE(request: Request) {
  try {
    const user = await requireUser();
    const { id } = await request.json();
    await removeAccount(user.id, id);
    return NextResponse.json({ accounts: await listAddresses(user.id) });
  } catch (err) {
    return fail(err);
  }
}
