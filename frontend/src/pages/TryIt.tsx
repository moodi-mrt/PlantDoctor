import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import DiagnoseFlow from "../components/diagnosis/DiagnoseFlow";
import { Loading, PageHeader } from "../components/ui/ui";

export default function TryIt() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (user) return <Navigate to="/app/diagnose" replace />;
  return (
    <div className="mx-auto max-w-4xl px-5 py-10">
      <PageHeader eyebrow="Guest check" title="Diagnose a plant" sub="Up to 3 free checks a day without an account. Results are not saved." />
      <DiagnoseFlow guest />
    </div>
  );
}
