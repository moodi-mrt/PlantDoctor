export type Role = "farmer" | "consultant" | "admin";
export interface User {
  id: number; email: string; name: string; role: Role; locale: string; location: string | null;
  prefs: Record<string, unknown>; email_verified: boolean; created_at: string;
}
export interface Reference { id: string; title: string; publisher?: string; url: string; checked?: string }
export interface Chemical { ai: string; group?: string; note?: string }
export interface Treatment {
  immediate: string[]; organic: string[]; chemical: Chemical[]; preventive: string[];
  watering: string; soil: string; fertilizer: string; long_term: string[];
}
export interface KBEntry {
  label: string; crop_key: string | null; crop: string | null; name: string; kind: string; pathogen: string;
  affected_parts: string[]; symptoms: string; causes: string; conditions: string;
  risk?: unknown; treatment: Treatment; chemical_notice: string | null; references: Reference[]; kb_complete: boolean;
  in_model?: boolean;
}
export interface PlantInfo {
  key: string; name: string; scientific: string; family: string; type: string; about: string;
  aliases: string[]; care: Record<string, string>; model: string; supported?: boolean; disease_count?: number;
}
export type Status = "confident" | "tentative" | "uncertain" | "needs_input" | "unknown" | "no_leaf" | "unsupported_crop";
export interface Alt { label: string; name: string; crop: string | null; kind: string; probability: number }
export interface ExpertHelp { name: string; note?: string; url?: string }
export interface DiagnosisResult {
  id: number | null; saved: boolean; created_at: string; status: Status; message: string | null;
  model_version: string | null; latency_ms: number;
  plant: null | {
    source: "image" | "user" | null; model_crop: string | null; confidence: number | null; agrees_with_user?: boolean | null;
    typed: string | null; info: PlantInfo | null; candidates: { crop: string; probability: number; info: PlantInfo | null }[];
  };
  diagnosis: null | { label: string; name: string; kind: string; healthy: boolean; confidence: number; calibrated: boolean; knowledge: KBEntry };
  alternatives: Alt[]; findings: Alt[];
  ood: null | { score: number; threshold: number; out_of_distribution: boolean };
  quality: { sharpness: number; brightness: number; warnings: { code: string; message: string }[] };
  image_url: string | null; heatmap_url: string | null; expert_help: ExpertHelp[];
  notes: string | null; feedback: string | null; plant_id: number | null;
}
export interface DiagnosisSummary {
  id: number; created_at: string; status: Status; crop_key: string | null; crop: string | null; label: string | null;
  name: string | null; kind: string | null; healthy: boolean; confidence: number; plant_id: number | null;
  thumbnail_url: string | null; model_version: string;
}
export interface Page<T> { items: T[]; next_cursor: number | null; total: number }
export interface ProductItem {
  id: string; title: string; company: string | null; active_ingredient: string; pack_size: string | null;
  price_pkr: number | null; store: string; url: string; verified_on: string; type: "verified";
  combination: boolean; also_contains: string[]; seed_treatment: boolean;
}
export interface ProductGroup {
  active_ingredient: string; resistance_group?: string; note?: string; verified: ProductItem[];
  search: { store: string; url: string; label: string; type: "search" }[];
}
export interface Products { label: string; disease: string; crop: string; groups: ProductGroup[]; notice: string | null; catalog_checked: string | null; disclaimer: string }
export interface MyPlant {
  id: number; nickname: string; crop_key: string | null; crop: string | null; scientific: string | null;
  location: string | null; notes: string | null; created_at: string; diagnosis_count: number;
  last_status: Status | null; last_healthy: boolean | null; last_condition: string | null; last_checked: string | null;
}
export interface Risk { label: string; crop: string; disease: string; kind: string; level: "High" | "Elevated"; favourable_hours: number; needed_hours: number; conditions: string; advice: string[] }
export interface Weather {
  place: { name: string; admin1?: string; country?: string; lat: number; lon: number };
  current: Record<string, number | string> | null; daily: Record<string, (number | string)[]>;
  hourly: Record<string, (number | string)[]>; risks: Risk[]; irrigation: string | null;
  source: string; fetched_at: string; stale: boolean; risk_method: string;
}
export interface Citation { doc_id: string; title: string; type: string; link: string | null; references: Reference[] }
export interface ChatReply {
  conversation_id: number; answer: string; citations: Citation[]; needs_expert: boolean; mode: "ai" | "knowledge_base";
  reason?: string; label: string; expert_help: ExpertHelp[];
}
export interface Meta {
  model_loaded: boolean; model_version: string | null; classes: number; crops: number; device: string | null;
  calibrated: boolean; ood_detection: boolean; pest_model: string | null;
  metrics: any; pest_metrics?: any;
}
