export const pct = (p: number | null | undefined, d = 0) => (p == null ? "—" : `${(p * 100).toFixed(d)}%`);
export const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
export const dateTime = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
export const ago = (iso: string) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return date(iso);
};
export const rupees = (n: number | null) => (n == null ? "Price not listed" : `Rs ${Math.round(n).toLocaleString()}`);
export const KIND_LABEL: Record<string, string> = {
  fungal: "Fungal disease", oomycete: "Water mould (oomycete)", bacterial: "Bacterial disease", viral: "Viral disease",
  phytoplasma: "Phytoplasma", pest: "Insect / mite pest", abiotic: "Non-infectious (nutrient / environment)",
  healthy: "Healthy", none: "—", unknown: "Unknown",
};
