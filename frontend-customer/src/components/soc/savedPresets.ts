/** Persist named SOC filter presets in localStorage (per portal + page). */

export type SocSavedPreset = {
  id: string;
  name: string;
  filters: Record<string, string>;
  createdAt: string;
};

function storageKey(namespace: string): string {
  return `kevantic.soc.presets.${namespace}`;
}

export function loadSocPresets(namespace: string): SocSavedPreset[] {
  try {
    const raw = localStorage.getItem(storageKey(namespace));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SocSavedPreset[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveSocPresets(namespace: string, presets: SocSavedPreset[]): void {
  localStorage.setItem(storageKey(namespace), JSON.stringify(presets.slice(0, 24)));
}

export function upsertSocPreset(
  namespace: string,
  name: string,
  filters: Record<string, string>
): SocSavedPreset[] {
  const trimmed = name.trim().slice(0, 80);
  if (!trimmed) return loadSocPresets(namespace);
  const clean: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== "") clean[k] = String(v).trim();
  }
  const existing = loadSocPresets(namespace).filter((p) => p.name !== trimmed);
  const next: SocSavedPreset = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: trimmed,
    filters: clean,
    createdAt: new Date().toISOString(),
  };
  const all = [next, ...existing];
  saveSocPresets(namespace, all);
  return all;
}

export function deleteSocPreset(namespace: string, id: string): SocSavedPreset[] {
  const all = loadSocPresets(namespace).filter((p) => p.id !== id);
  saveSocPresets(namespace, all);
  return all;
}
