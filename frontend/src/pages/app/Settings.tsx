import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { Button, Card, CardHeader, Input, Notice, PageHeader, Select } from "../../components/ui/ui";

function Toggle({ label, sub, checked, onChange }: { label: string; sub: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 py-3">
      <span><span className="block text-sm font-medium">{label}</span><span className="block text-sm text-ink-3">{sub}</span></span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 h-5 w-9 cursor-pointer accent-forest-800" />
    </label>
  );
}

export default function Settings() {
  const { user, refresh, logout } = useAuth();
  const nav = useNavigate();
  const [p, setP] = useState({ name: user?.name ?? "", locale: user?.locale ?? "en", location: user?.location ?? "" });
  const [prefs, setPrefs] = useState<Record<string, boolean>>({ email_notifications: false, weather_alerts: false, share_images_for_improvement: false, ...(user?.prefs as any) });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [delPw, setDelPw] = useState("");
  const profile = useMutation({ mutationFn: () => api("/users/me", { method: "PATCH", body: { ...p, location: p.location || null, prefs } }), onSuccess: refresh });
  const password = useMutation({ mutationFn: () => api("/auth/password", { body: pw }), onSuccess: () => setPw({ current_password: "", new_password: "" }) });
  const resend = useMutation({ mutationFn: () => api("/auth/resend-verification", { method: "POST" }) });
  const del = useMutation({ mutationFn: () => api("/users/me", { method: "DELETE", body: { password: delPw } }), onSuccess: async () => { await logout(); nav("/"); } });
  const setPref = (k: string) => (v: boolean) => setPrefs({ ...prefs, [k]: v });
  return (
    <div className="max-w-3xl space-y-5">
      <PageHeader title="Settings" />
      <Card>
        <CardHeader title="Account" sub={<>{user?.email} {user?.email_verified ? "· verified" : <>· not verified — <Button variant="link" onClick={() => resend.mutate()}>{resend.isSuccess ? "link sent" : "resend link"}</Button></>}</>} />
        <div className="grid gap-4 p-5 sm:grid-cols-2">
          <Input label="Name" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} />
          <Input label="Default location (for weather)" placeholder="e.g. Faisalabad" value={p.location} onChange={(e) => setP({ ...p, location: e.target.value })} />
          <Select label="Language" value={p.locale} onChange={(e) => setP({ ...p, locale: e.target.value })} hint="Urdu currently applies to the assistant and AI explanations.">
            <option value="en">English</option><option value="ur">اردو (Urdu)</option>
          </Select>
        </div>
        <div className="divide-y divide-line border-t border-line px-5">
          <Toggle label="Email notifications" sub="Occasional emails about your account and important updates." checked={!!prefs.email_notifications} onChange={setPref("email_notifications")} />
          <Toggle label="Weather risk alerts" sub="Show disease-risk alerts for my crops on the dashboard." checked={!!prefs.weather_alerts} onChange={setPref("weather_alerts")} />
          <Toggle label="Help improve the model" sub="Let PlantDoctor administrators view photos of uncertain or incorrect diagnoses to improve accuracy. Off by default." checked={!!prefs.share_images_for_improvement} onChange={setPref("share_images_for_improvement")} />
        </div>
        <div className="flex items-center gap-3 p-5">
          <Button onClick={() => profile.mutate()} loading={profile.isPending}>Save changes</Button>
          {profile.isSuccess && <span className="text-sm text-emerald-700">Saved.</span>}
          {profile.error && <span className="text-sm text-bad-700">{(profile.error as ApiError).message}</span>}
        </div>
      </Card>
      <Card>
        <CardHeader title="Password" sub="Changing it signs you out on your other devices." />
        <form className="grid gap-4 p-5 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); password.mutate(); }}>
          <Input label="Current password" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
          <Input label="New password" type="password" autoComplete="new-password" hint="At least 10 characters." value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
          <div className="sm:col-span-2">
            {password.error && <div className="mb-3"><Notice tone="bad">{(password.error as ApiError).message}</Notice></div>}
            {password.isSuccess && <div className="mb-3"><Notice tone="ok">Password changed.</Notice></div>}
            <Button type="submit" variant="secondary" loading={password.isPending} disabled={!pw.current_password || !pw.new_password}>Change password</Button>
          </div>
        </form>
      </Card>
      <Card>
        <CardHeader title="Privacy & data" />
        <div className="space-y-4 p-5 text-sm text-ink-2">
          <p>Your photos are stored privately and only you can see them (unless you enable “Help improve the model”). Location data (EXIF/GPS) is removed before storage. You can export your history as CSV from <b>History</b>, and delete individual diagnoses there.</p>
          <div className="rounded-xl border border-bad-100 bg-bad-50 p-4">
            <p className="font-semibold text-bad-700">Delete account</p>
            <p className="mt-1">Permanently deletes your account, all diagnoses, photos, plants and conversations. This cannot be undone.</p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
              <Input className="flex-1" label="Confirm with your password" type="password" autoComplete="current-password" value={delPw} onChange={(e) => setDelPw(e.target.value)} error={del.error ? (del.error as ApiError).message : undefined} />
              <Button variant="danger" icon="trash" disabled={!delPw} loading={del.isPending} onClick={() => { if (confirm("Delete your account and all data permanently?")) del.mutate(); }}>Delete account</Button>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
