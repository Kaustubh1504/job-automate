// Gmail app passwords are encrypted before they touch the database, so a
// dumped table is useless on its own. AES-256-GCM: authenticated, so a
// tampered ciphertext fails loudly at decrypt rather than yielding garbage.
//
// ENCRYPTION_KEY lives in .env. Changing or losing it makes every stored
// account unreadable -- they'd have to be re-entered.

import "server-only";
import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from "node:crypto";

function key(): Buffer {
  const secret = process.env.ENCRYPTION_KEY;
  if (!secret) throw new Error("ENCRYPTION_KEY must be set in .env");
  // Fixed salt: the same secret has to derive the same key on every boot.
  return scryptSync(secret, "mailer-gmail-app-password", 32);
}

export function encrypt(plaintext: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(), iv);
  const body = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  return [iv, cipher.getAuthTag(), body].map((b) => b.toString("base64")).join(".");
}

export function decrypt(payload: string): string {
  const [iv, tag, body] = payload.split(".").map((part) => Buffer.from(part, "base64"));
  if (!iv || !tag || !body) throw new Error("Stored password is not in the expected format");
  const decipher = createDecipheriv("aes-256-gcm", key(), iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(body), decipher.final()]).toString("utf8");
}
