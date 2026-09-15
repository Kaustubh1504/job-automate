"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Paperclip, Plus, Upload, X } from "lucide-react"

import { signOut } from "./login/actions"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

// Gmail rejects messages over 25MB; stop short of it so the failure is a clear
// message here rather than an SMTP error per recipient.
const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

type Person = {
  id: string
  name: string
  email: string
  title: string | null
  company: string | null
  sender_address: string
}

type MailAccount = { id: string; address: string }

type SendResult = {
  sent: number
  failed: number
  errors: string[]
  perAccount: Record<string, number>
}

const BLANK_PERSON = { name: "", email: "", linkedin_url: "", company: "", title: "" }
const BLANK_ACCOUNT = { address: "", appPassword: "" }

// Manual entries go through the CSV path rather than a second endpoint, so
// they get the same dedup and sending-account assignment as an upload.
function toCsv(person: typeof BLANK_PERSON): string {
  const cell = (value: string) => `"${value.trim().replace(/"/g, '""')}"`
  const columns = ["name", "email", "linkedin_url", "company", "title"] as const
  return `${columns.join(",")}\n${columns.map((c) => cell(person[c])).join(",")}`
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function Page() {
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [attachments, setAttachments] = useState<File[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [filter, setFilter] = useState("")
  const [draft, setDraft] = useState<typeof BLANK_PERSON | null>(null)
  const [mailAccounts, setMailAccounts] = useState<MailAccount[]>([])
  const [showAccounts, setShowAccounts] = useState(false)
  const [accountDraft, setAccountDraft] = useState({ ...BLANK_ACCOUNT })
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SendResult | null>(null)
  const csvInput = useRef<HTMLInputElement>(null)
  const attachInput = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    const res = await fetch("/api/people")
    const data = await res.json()
    if (res.ok) setPeople(data.people)
    else setError(data.error)
  }, [])

  const refreshAccounts = useCallback(async () => {
    const res = await fetch("/api/accounts")
    const data = await res.json()
    if (res.ok) setMailAccounts(data.accounts)
  }, [])

  useEffect(() => {
    refresh()
    refreshAccounts()
  }, [refresh, refreshAccounts])

  async function addAccount() {
    setBusy(true)
    setError(null)
    setNote(null)
    try {
      const res = await fetch("/api/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(accountDraft),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? res.statusText)
      setMailAccounts(data.accounts)
      setAccountDraft({ ...BLANK_ACCOUNT })
      setNote("Account verified and saved")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add account")
    } finally {
      setBusy(false)
    }
  }

  async function removeAccount(id: string) {
    const res = await fetch("/api/accounts", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    })
    const data = await res.json()
    if (res.ok) setMailAccounts(data.accounts)
    else setError(data.error)
  }

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return people
    return people.filter((p) =>
      [p.name, p.email, p.company, p.title].some((f) => f?.toLowerCase().includes(q))
    )
  }, [people, filter])

  // Company is the organising unit — you usually mail a whole company at once.
  const companies = useMemo(() => {
    const groups = new Map<string, Person[]>()
    for (const person of visible) {
      const key = person.company ?? "No company"
      const group = groups.get(key)
      if (group) group.push(person)
      else groups.set(key, [person])
    }
    return [...groups.entries()]
  }, [visible])

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleCompany(members: Person[], allSelected: boolean) {
    setSelected((prev) => {
      const next = new Set(prev)
      for (const person of members) {
        if (allSelected) next.delete(person.id)
        else next.add(person.id)
      }
      return next
    })
  }

  function addAttachments(files: File[]) {
    const combined = [...attachments, ...files]
    const total = combined.reduce((sum, f) => sum + f.size, 0)
    if (total > MAX_ATTACHMENT_BYTES) {
      setError(`Attachments total ${fileSize(total)} — keep them under ${fileSize(MAX_ATTACHMENT_BYTES)}`)
      return
    }
    setError(null)
    setAttachments(combined)
  }

  async function importCsv(csv: string) {
    setBusy(true)
    setError(null)
    setNote(null)
    try {
      const res = await fetch("/api/people", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csv }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? res.statusText)
      setNote(
        `${data.added} added, ${data.updated} updated` +
          (data.skipped.length ? `, ${data.skipped.length} skipped` : "")
      )
      setDraft(null)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed")
    } finally {
      setBusy(false)
      if (csvInput.current) csvInput.current.value = ""
    }
  }

  async function send() {
    // Modal confirm rather than an armed button: this fires real mail at real
    // people with no undo, and a button that merely changes its own label
    // reads as "nothing happened".
    const count = selected.size
    const extra = attachments.length ? ` with ${attachments.length} attachment(s)` : ""
    if (!window.confirm(`Send "${subject}" to ${count} ${count === 1 ? "person" : "people"}${extra}?\n\nThis cannot be undone.`)) {
      return
    }
    setBusy(true)
    setError(null)
    setNote(null)
    setResult(null)
    try {
      const form = new FormData()
      form.set("subject", subject)
      form.set("body", body)
      form.set("personIds", JSON.stringify([...selected]))
      for (const file of attachments) form.append("attachments", file)

      const res = await fetch("/api/send", { method: "POST", body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? res.statusText)
      setResult(data)
      setSelected(new Set())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed")
    } finally {
      setBusy(false)
    }
  }

  const canSend = subject.trim() && body.trim() && selected.size > 0 && !busy

  return (
    <main className="mx-auto flex h-screen max-w-3xl flex-col gap-4 p-6">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">Mailer</span>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-7"
          onClick={() => setShowAccounts(!showAccounts)}
        >
          {mailAccounts.length} account{mailAccounts.length === 1 ? "" : "s"}
        </Button>
        <form action={signOut}>
          <Button type="submit" variant="ghost" size="sm" className="h-7">
            Sign out
          </Button>
        </form>
      </div>

      {showAccounts && (
        <div className="space-y-2 rounded-md border p-3">
          {mailAccounts.map((account) => (
            <div key={account.id} className="flex items-center gap-2 text-sm">
              <span className="flex-1 truncate">{account.address}</span>
              <Button variant="ghost" size="sm" className="h-7" onClick={() => removeAccount(account.id)}>
                Remove
              </Button>
            </div>
          ))}
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              addAccount()
            }}
          >
            <Input
              required
              type="email"
              value={accountDraft.address}
              onChange={(e) => setAccountDraft({ ...accountDraft, address: e.target.value })}
              placeholder="you@gmail.com"
              className="h-8"
            />
            <Input
              required
              value={accountDraft.appPassword}
              onChange={(e) => setAccountDraft({ ...accountDraft, appPassword: e.target.value })}
              placeholder="app password"
              className="h-8"
            />
            <Button type="submit" size="sm" disabled={busy}>
              Add
            </Button>
          </form>
          <p className="text-xs text-muted-foreground">
            Gmail app password, created at myaccount.google.com/apppasswords (needs 2FA).
            Stored encrypted; login is verified before it is kept.
          </p>
        </div>
      )}

      <Input
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
        placeholder="Subject"
      />
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={"Hi {{first_name}} —\n\nI saw {{company}} is hiring…"}
        className="h-40 resize-none"
      />

      <div className="-mt-2 flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">
          {"{{first_name}} {{name}} {{company}} {{title}} {{email}}"}
        </span>
        <input
          ref={attachInput}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            addAttachments([...(e.target.files ?? [])])
            e.target.value = ""
          }}
        />
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-7"
          onClick={() => attachInput.current?.click()}
        >
          <Paperclip className="mr-1.5 h-3.5 w-3.5" />
          Attach
        </Button>
        {attachments.map((file, i) => (
          <Badge key={`${file.name}-${i}`} variant="secondary" className="gap-1 font-normal">
            {file.name}
            <span className="text-muted-foreground">{fileSize(file.size)}</span>
            <button
              type="button"
              aria-label={`Remove ${file.name}`}
              onClick={() => setAttachments(attachments.filter((_, j) => j !== i))}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={`Filter ${people.length} people`}
          className="h-8"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSelected(new Set(visible.map((p) => p.id)))}
          disabled={visible.length === 0}
        >
          All
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
          None
        </Button>
        <input
          ref={csvInput}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) file.text().then(importCsv)
          }}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => csvInput.current?.click()}
          disabled={busy}
        >
          <Upload className="mr-2 h-3.5 w-3.5" />
          CSV
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setDraft(draft ? null : { ...BLANK_PERSON })}
          disabled={busy}
        >
          <Plus className="mr-2 h-3.5 w-3.5" />
          Add
        </Button>
      </div>

      {draft && (
        <form
          className="grid grid-cols-3 gap-2 rounded-md border p-3"
          onSubmit={(e) => {
            e.preventDefault()
            importCsv(toCsv(draft))
          }}
        >
          <Input
            required
            autoFocus
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Name"
            className="h-8"
          />
          <Input
            required
            type="email"
            value={draft.email}
            onChange={(e) => setDraft({ ...draft, email: e.target.value })}
            placeholder="Email"
            className="h-8"
          />
          <Input
            required
            value={draft.linkedin_url}
            onChange={(e) => setDraft({ ...draft, linkedin_url: e.target.value })}
            placeholder="LinkedIn URL"
            className="h-8"
          />
          <Input
            value={draft.company}
            onChange={(e) => setDraft({ ...draft, company: e.target.value })}
            placeholder="Company (optional)"
            className="h-8"
          />
          <Input
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            placeholder="Title (optional)"
            className="h-8"
          />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy}>
              Save
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      <div className="flex-1 overflow-y-auto rounded-md border">
        {companies.map(([company, members]) => {
          const chosen = members.filter((p) => selected.has(p.id)).length
          const all = chosen === members.length

          return (
            <div key={company}>
              <label className="sticky top-0 flex cursor-pointer items-center gap-2 border-b bg-muted/70 px-3 py-1.5 backdrop-blur">
                <input
                  type="checkbox"
                  checked={all}
                  ref={(el) => {
                    if (el) el.indeterminate = chosen > 0 && !all
                  }}
                  onChange={() => toggleCompany(members, all)}
                />
                <span className="text-sm font-semibold">{company}</span>
                <span className="text-xs text-muted-foreground">
                  {chosen > 0 ? `${chosen}/${members.length}` : members.length}
                </span>
              </label>
              {members.map((person) => (
                <label
                  key={person.id}
                  className="flex cursor-pointer items-center gap-3 border-b px-3 py-2 pl-8 text-sm last:border-b-0 hover:bg-muted/50"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(person.id)}
                    onChange={() => toggle(person.id)}
                  />
                  <span className="w-40 shrink-0 truncate font-medium">{person.name}</span>
                  <span className="w-44 shrink-0 truncate text-xs text-muted-foreground">
                    {person.title ?? "—"}
                  </span>
                  <span className="flex-1 truncate text-muted-foreground">{person.email}</span>
                  <span
                    title={person.sender_address}
                    className="w-32 shrink-0 truncate text-right text-xs text-muted-foreground"
                  >
                    {person.sender_address.split("@")[0]}
                  </span>
                </label>
              ))}
            </div>
          )
        })}
        {visible.length === 0 && (
          <p className="p-4 text-sm text-muted-foreground">
            {people.length === 0 ? "No people yet — upload a CSV." : "Nothing matches that filter."}
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={send} disabled={!canSend}>
          {busy ? "Sending…" : `Send to ${selected.size}`}
        </Button>
        {note && <span className="text-sm text-muted-foreground">{note}</span>}
        {error && <span className="text-sm text-destructive">{error}</span>}
        {result && (
          <span className="text-sm">
            Sent {result.sent}
            {result.failed > 0 && `, ${result.failed} failed`}
            {Object.entries(result.perAccount).map(([address, n]) => (
              <Badge key={address} variant="secondary" className="ml-1 font-normal">
                {address.split("@")[0]} {n}
              </Badge>
            ))}
          </span>
        )}
      </div>
    </main>
  )
}
