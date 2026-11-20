import { useState } from "react";
import { Link, Outlet } from "react-router-dom";
import clsx from "clsx";
import { useAuth } from "../../lib/auth";
import { ButtonLink } from "../ui/ui";
import { Icon } from "../ui/icons";
import Logo from "./Logo";

const NAV = [
  { to: "/#how", label: "How it works" },
  { to: "/#crops", label: "Crops" },
  { to: "/knowledge", label: "Disease library" },
  { to: "/#reliability", label: "Reliability" },
  { to: "/#faq", label: "FAQ" },
];

export default function PublicLayout() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-line/80 bg-paper/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-page items-center justify-between gap-6 px-5">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
            {NAV.map((n) => <Link key={n.to} to={n.to} className="rounded-lg px-3 py-2 text-sm text-ink-2 hover:bg-paper-2 hover:text-ink focus-ring">{n.label}</Link>)}
          </nav>
          <div className="hidden items-center gap-2 lg:flex">
            {user ? <ButtonLink to="/app" icon="home">Open dashboard</ButtonLink> : <>
              <ButtonLink to="/login" variant="ghost">Sign in</ButtonLink>
              <ButtonLink to="/try" icon="scan">Try disease detection</ButtonLink></>}
          </div>
          <button className="rounded-lg p-2 lg:hidden focus-ring" aria-expanded={open} aria-controls="mnav" aria-label="Menu" onClick={() => setOpen(!open)}>
            <Icon name={open ? "x" : "menu"} />
          </button>
        </div>
        <div id="mnav" className={clsx("border-t border-line bg-paper px-5 pb-5 pt-2 lg:hidden", !open && "hidden")}>
          {NAV.map((n) => <Link key={n.to} to={n.to} onClick={() => setOpen(false)} className="block rounded-lg px-2 py-3 text-ink-2">{n.label}</Link>)}
          <div className="mt-3 grid gap-2">
            {user ? <ButtonLink to="/app">Open dashboard</ButtonLink> : <>
              <ButtonLink to="/try" icon="scan">Try disease detection</ButtonLink>
              <ButtonLink to="/login" variant="secondary">Sign in</ButtonLink></>}
          </div>
        </div>
      </header>
      <main id="main" className="flex-1"><Outlet /></main>
      <footer className="border-t border-line bg-paper-2/60">
        <div className="mx-auto grid max-w-page gap-8 px-5 py-12 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2 lg:col-span-1">
            <Logo />
            <p className="mt-3 max-w-xs text-sm text-ink-3">Plant-health decision support for farmers and growers. Not a substitute for a laboratory test or an agronomist.</p>
          </div>
          <div>
            <h3 className="text-sm font-semibold">Product</h3>
            <ul className="mt-3 space-y-2 text-sm text-ink-3">
              <li><Link className="hover:text-ink" to="/try">Disease detection</Link></li>
              <li><Link className="hover:text-ink" to="/knowledge">Disease library</Link></li>
              <li><Link className="hover:text-ink" to="/#reliability">Model transparency</Link></li>
              <li><a className="hover:text-ink" href="/classic">Classic interface</a></li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold">Resources</h3>
            <ul className="mt-3 space-y-2 text-sm text-ink-3">
              <li><a className="hover:text-ink" href="/api/docs">API documentation</a></li>
              <li><a className="hover:text-ink" href="/report">Technical report (PDF)</a></li>
              <li><a className="hover:text-ink" href="https://www.parc.gov.pk/" target="_blank" rel="noopener noreferrer">PARC</a></li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold">Support</h3>
            <ul className="mt-3 space-y-2 text-sm text-ink-3">
              <li>For crop emergencies contact your district Agriculture Extension office.</li>
              <li>Punjab Agriculture helpline: 0800-17000</li>
            </ul>
          </div>
        </div>
        <div className="border-t border-line py-5 text-center text-xs text-ink-4">© {new Date().getFullYear()} PlantDoctor · Decision support only — always follow the product label.</div>
      </footer>
    </div>
  );
}
