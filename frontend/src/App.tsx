import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { Loading } from "./components/ui/ui";
import PublicLayout from "./components/layout/PublicLayout";
import AppLayout from "./components/layout/AppLayout";
import Landing from "./pages/Landing";

const Login = lazy(() => import("./pages/auth/Login"));
const Register = lazy(() => import("./pages/auth/Register"));
const Verify = lazy(() => import("./pages/auth/Verify"));
const Forgot = lazy(() => import("./pages/auth/Forgot"));
const Reset = lazy(() => import("./pages/auth/Reset"));
const TryIt = lazy(() => import("./pages/TryIt"));
const Dashboard = lazy(() => import("./pages/app/Dashboard"));
const Diagnose = lazy(() => import("./pages/app/Diagnose"));
const History = lazy(() => import("./pages/app/History"));
const DiagnosisDetail = lazy(() => import("./pages/app/DiagnosisDetail"));
const Plants = lazy(() => import("./pages/app/Plants"));
const Knowledge = lazy(() => import("./pages/app/Knowledge"));
const DiseasePage = lazy(() => import("./pages/app/DiseasePage"));
const Assistant = lazy(() => import("./pages/app/Assistant"));
const WeatherPage = lazy(() => import("./pages/app/WeatherPage"));
const Settings = lazy(() => import("./pages/app/Settings"));
const Admin = lazy(() => import("./pages/admin/Admin"));
const NotFound = lazy(() => import("./pages/NotFound"));

function RequireAuth({ children, admin }: { children: ReactNode; admin?: boolean }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (admin && user.role !== "admin") return <Navigate to="/app" replace />;
  return <>{children}</>;
}

function ScrollTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) { window.scrollTo(0, 0); return; }
    // In-page anchors (/#faq): wait for the section to render, then scroll to it.
    let tries = 0;
    const t = setInterval(() => {
      const el = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (el || ++tries > 20) { clearInterval(t); el?.scrollIntoView({ behavior: "smooth", block: "start" }); }
    }, 50);
    return () => clearInterval(t);
  }, [pathname, hash]);
  return null;
}

export default function App() {
  return (
    <>
      <ScrollTop />
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route element={<PublicLayout />}>
            <Route path="/" element={<Landing />} />
            <Route path="/try" element={<TryIt />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/verify" element={<Verify />} />
            <Route path="/forgot" element={<Forgot />} />
            <Route path="/reset" element={<Reset />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/knowledge/:label" element={<DiseasePage />} />
          </Route>
          <Route path="/app" element={<RequireAuth><AppLayout /></RequireAuth>}>
            <Route index element={<Dashboard />} />
            <Route path="diagnose" element={<Diagnose />} />
            <Route path="diagnoses" element={<History />} />
            <Route path="diagnoses/:id" element={<DiagnosisDetail />} />
            <Route path="plants" element={<Plants />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="knowledge/:label" element={<DiseasePage />} />
            <Route path="assistant" element={<Assistant />} />
            <Route path="weather" element={<WeatherPage />} />
            <Route path="settings" element={<Settings />} />
          </Route>
          <Route path="/admin/*" element={<RequireAuth admin><AppLayout admin /></RequireAuth>}>
            <Route path="*" element={<Admin />} />
          </Route>
          <Route element={<PublicLayout />}>
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </>
  );
}
