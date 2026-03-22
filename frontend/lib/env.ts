/**
 * UI label for environment badges.
 * Treats Railway-hosted API URLs as production.
 */
export function getEnvironmentLabel(): "production" | "local dev" {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  return base.includes("railway") ? "production" : "local dev";
}
