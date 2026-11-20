import { Link } from "react-router-dom";
export default function Logo({ to = "/", light }: { to?: string; light?: boolean }) {
  return (
    <Link to={to} className="flex items-center gap-2 rounded-lg focus-ring" aria-label="PlantDoctor home">
      <span className="grid h-8 w-8 place-items-center rounded-[9px] bg-forest-800 text-white">
        <svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true"><path d="M10 22c0-7 4.5-11.5 12-12.5-1 7.5-5.5 12.5-12 12.5zm0 0l6-6" stroke="currentColor" strokeWidth="2.4" fill="none" strokeLinecap="round" /></svg>
      </span>
      <span className={`text-[17px] font-semibold tracking-tight ${light ? "text-white" : "text-ink"}`}>PlantDoctor</span>
    </Link>
  );
}
