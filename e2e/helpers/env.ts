import fs from "fs";
import path from "path";

/** Load lab credentials from .secrets/validation.env without printing values. */
export function loadValidationEnv(): void {
  const root = path.resolve(__dirname, "../..");
  const envFile =
    process.env.MSSP_VALIDATION_ENV || path.join(root, ".secrets", "validation.env");
  if (!fs.existsSync(envFile)) {
    return;
  }
  const text = fs.readFileSync(envFile, "utf8");
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

export function requireCred(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(
      `Missing ${name}. Create /opt/mssp-control/.secrets/validation.env from deploy/environments/validation.lab.example.env`
    );
  }
  return v;
}
