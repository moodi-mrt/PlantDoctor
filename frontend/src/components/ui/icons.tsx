/** Minimal stroke icon set (24px grid, 1.75 stroke). Decorative by default (aria-hidden). */
import type { SVGProps } from "react";
const P: Record<string, string> = {
  leaf: "M5 19c0-8 5-13 14-14-1 9-6 14-14 14zm0 0l7-7",
  upload: "M12 15V4m0 0L7.5 8.5M12 4l4.5 4.5M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 17a4 4 0 100-8 4 4 0 000 8z",
  home: "M4 11l8-7 8 7v9h-5v-6H9v6H4z",
  scan: "M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3M7 12h10",
  history: "M4 12a8 8 0 108-8 8 8 0 00-6 2.7L4 9M4 4v5h5M12 8v4l3 2",
  sprout: "M12 20v-8m0 0c0-4-3-6-7-6 0 4 3 6 7 6zm0 0c0-4 3-7 7-7 0 4-3 7-7 7z",
  book: "M5 4h10a4 4 0 014 4v12H9a4 4 0 01-4-4zM5 16a4 4 0 014-4h10",
  chat: "M5 5h14v10H9l-4 4z",
  cloud: "M7 18a4 4 0 01-.5-8A6 6 0 0118 9a4.5 4.5 0 01-1 9z",
  settings: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  shield: "M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z",
  check: "M5 12.5l4.5 4.5L19 7.5",
  alert: "M12 8v5m0 3.5v.5M10.3 4.3L2.6 18a2 2 0 001.7 3h15.4a2 2 0 001.7-3L13.7 4.3a2 2 0 00-3.4 0z",
  info: "M12 11v6m0-9.5V8M12 21a9 9 0 100-18 9 9 0 000 18z",
  x: "M6 6l12 12M18 6L6 18",
  arrowRight: "M5 12h14m-5-5l5 5-5 5",
  arrowLeft: "M19 12H5m5-5l-5 5 5 5",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zm9 2l-4-4",
  download: "M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M4 19h16",
  trash: "M4 7h16M9 7V4h6v3m-8 0l1 13h8l1-13",
  plus: "M12 5v14M5 12h14",
  logout: "M15 4h4v16h-4M10 17l5-5-5-5M15 12H3",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zm-7 9a7 7 0 0114 0",
  external: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5",
  droplet: "M12 3s6 6.5 6 11a6 6 0 01-12 0c0-4.5 6-11 6-11z",
  thermo: "M10 14V5a2 2 0 114 0v9a4 4 0 11-4 0z",
  bug: "M8 9h8v6a4 4 0 01-8 0zM9 9V7a3 3 0 016 0v2M4 13h4m8 0h4M5 8l3 2m11-2l-3 2M5 19l3-2m11 2l-3-2",
  menu: "M4 7h16M4 12h16M4 17h16",
  sun: "M12 16a4 4 0 100-8 4 4 0 000 8zM12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4l1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z",
  crop: "M6 2v14a2 2 0 002 2h14M2 6h14a2 2 0 012 2v14",
  rotate: "M4 4v5h5M20 12a8 8 0 11-2.3-5.7L20 9",
  layers: "M12 3l9 5-9 5-9-5zm-9 9l9 5 9-5M3 16l9 5 9-5",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  users: "M9 11a4 4 0 100-8 4 4 0 000 8zM2 21a7 7 0 0114 0M17 3a4 4 0 010 8m5 10a7 7 0 00-5-6.7",
  cpu: "M7 7h10v10H7zM9 2v3m6-3v3M9 19v3m6-3v3M2 9h3M2 15h3M19 9h3M19 15h3",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zm0 0v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  flag: "M5 21V4m0 0h11l-2 4 2 4H5",
  store: "M3 9l2-5h14l2 5M4 9v11h16V9M3 9h18M9 20v-6h6v6",
  send: "M4 12l16-8-6 16-2-7z",
};
export type IconName = keyof typeof P;
export function Icon({ name, size = 20, className, ...rest }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className} {...rest}>
      <path d={P[name]} />
    </svg>
  );
}
