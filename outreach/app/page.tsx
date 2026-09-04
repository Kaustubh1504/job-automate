import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { connectedEmail } from "@/lib/gmail";

export const dynamic = "force-dynamic";

export default async function Home() {
  let email: string | null = null;
  let statusError: string | null = null;
  try {
    email = await connectedEmail();
  } catch (err) {
    statusError = err instanceof Error ? err.message : "status check failed";
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Gmail</CardTitle>
          <CardDescription>
            Emails are sent from your real Gmail account over SMTP (app password, same as mailer/).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {email ? (
            <div className="flex items-center gap-2">
              <Badge>Connected</Badge>
              <span className="text-sm">{email}</span>
            </div>
          ) : (
            <div className="space-y-2">
              <Badge variant="secondary">Not connected</Badge>
              <p className="text-sm text-destructive">{statusError}</p>
              <p className="text-sm text-muted-foreground">
                Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in outreach/.env (create an app password
                at myaccount.google.com/apppasswords).
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
