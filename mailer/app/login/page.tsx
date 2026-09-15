"use client"

import { useActionState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { signIn, signUp } from "./actions"

export default function LoginPage() {
  const [signInError, doSignIn, signingIn] = useActionState(signIn, null)
  const [signUpNote, doSignUp, signingUp] = useActionState(signUp, null)

  return (
    <main className="mx-auto flex h-screen max-w-sm flex-col justify-center gap-3">
      <h1 className="text-lg font-semibold">Mailer</h1>
      <form className="flex flex-col gap-3">
        <Input name="email" type="email" required placeholder="Email" autoComplete="email" />
        <Input
          name="password"
          type="password"
          required
          minLength={6}
          placeholder="Password"
          autoComplete="current-password"
        />
        <div className="flex gap-2">
          <Button formAction={doSignIn} disabled={signingIn || signingUp}>
            {signingIn ? "Signing in…" : "Sign in"}
          </Button>
          <Button
            variant="outline"
            formAction={doSignUp}
            disabled={signingIn || signingUp}
          >
            {signingUp ? "Creating…" : "Create account"}
          </Button>
        </div>
      </form>
      {signInError && <p className="text-sm text-destructive">{signInError}</p>}
      {signUpNote && <p className="text-sm text-muted-foreground">{signUpNote}</p>}
    </main>
  )
}
