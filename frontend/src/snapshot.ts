// Static hosting reads exported Atlas responses instead of the live API (see scripts/export_snapshot.py).
export const STATIC = (import.meta as unknown as { env: Record<string, string | undefined> }).env.VITE_STATIC === "1";
export const snapshotKey = (path: string) => path.replace(/[?&]offline=true/, "").replace(/^\//, "").replace(/[^A-Za-z0-9_-]/g, "_");
export const endpoint = (path: string) => (STATIC ? `/snapshot/${snapshotKey(path)}.json` : `/api${path}`);
