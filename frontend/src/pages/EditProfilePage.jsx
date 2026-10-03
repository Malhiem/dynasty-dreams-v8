// @ts-nocheck
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Save, Camera, Trash2, User as UserIcon } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

const SPORT_OPTIONS = [
  { value: "Hockey", label: "Hockey" },
  { value: "Football", label: "Football" },
  { value: "Basketball", label: "Basketball" },
  { value: "Baseball", label: "Baseball" },
  { value: "Soccer", label: "Soccer" },
  { value: "Other", label: "Other" },
];

const ACCEPTED = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"];
const MAX_BYTES = 1 * 1024 * 1024;

export default function EditProfilePage() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState({
    username: "",
    email: "",
    favourite_sport: "",
    favourite_team: "",
    city: "",
    province_state: "",
    country: "",
  });
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.get("/auth/me").then(({ data }) => {
      setForm({
        username: data.username || "",
        email: data.email || "",
        favourite_sport: data.favourite_sport || "",
        favourite_team: data.favourite_team || "",
        city: data.city || "",
        province_state: data.province_state || "",
        country: data.country || "",
      });
      setAvatarPreview(data.avatar_url || null);
    });
  }, [user]);

  const update = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = { ...form };
      // Empty strings = leave unchanged (treat as null on backend)
      Object.keys(payload).forEach((k) => { if (payload[k] === "") payload[k] = null; });
      const { data } = await api.put("/users/me/profile", payload);
      toast.success("Profile updated");
      const newUsername = data?.user?.username || form.username;
      if (refreshUser) await refreshUser();
      if (newUsername && user?.username && newUsername !== user.username) {
        // Username changed — bounce them to the new public profile URL
        toast.info(`Username changed → /u/${newUsername}`);
        navigate(`/u/${newUsername}`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update profile");
    } finally {
      setBusy(false);
    }
  };

  const onUploadAvatar = async (file) => {
    if (!ACCEPTED.includes(file.type)) {
      toast.error("Use PNG, JPEG, WEBP, or GIF.");
      return;
    }
    if (file.size > MAX_BYTES) {
      toast.error(`Image too large (${(file.size / 1024 / 1024).toFixed(2)} MB). Max 1 MB.`);
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/users/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setAvatarPreview(data?.avatar_url || null);
      toast.success("Profile photo updated");
      if (refreshUser) await refreshUser();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to upload");
    } finally {
      setBusy(false);
    }
  };

  const onRemoveAvatar = async () => {
    setBusy(true);
    try {
      await api.delete("/users/me/avatar");
      setAvatarPreview(null);
      toast.success("Profile photo removed");
      if (refreshUser) await refreshUser();
    } catch (err) {
      toast.error("Failed to remove photo");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppLayout>
      <div className="container max-w-2xl py-8" data-testid="edit-profile-page">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">
            <UserIcon className="h-7 w-7 text-[#00D2FF]" />
            Edit Profile
          </h1>
          <p className="text-sm text-[#A1A1AA]">Update your account details and profile picture.</p>
        </div>

        <Card className="border-white/10 bg-[#141414]">
          <CardHeader>
            <CardTitle className="text-white text-lg">Profile Photo</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-5">
            <div className="h-20 w-20 rounded-full bg-[#00D2FF]/15 flex items-center justify-center overflow-hidden border border-white/10">
              {avatarPreview ? (
                <img src={avatarPreview} alt="Avatar" className="h-full w-full object-cover" data-testid="edit-profile-avatar-preview" />
              ) : (
                <UserIcon className="h-10 w-10 text-[#00D2FF]/40" />
              )}
            </div>
            <div className="flex-1 space-y-2">
              <Input
                type="file"
                accept={ACCEPTED.join(",")}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onUploadAvatar(f);
                  if (e.target) e.target.value = "";
                }}
                disabled={busy}
                className="bg-[#0A0A0A] border-white/10 text-white file:bg-[#1A1A1A] file:text-white file:border-0 file:rounded file:px-3 file:py-1 file:mr-3"
                data-testid="edit-profile-avatar-input"
              />
              <p className="text-xs text-[#A1A1AA]">PNG, JPEG, WEBP, or GIF · max 1 MB · resized to 256×256.</p>
              {avatarPreview && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onRemoveAvatar}
                  disabled={busy}
                  className="text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
                  data-testid="edit-profile-avatar-remove"
                >
                  <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Remove
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <form onSubmit={onSubmit} className="mt-4 space-y-4">
          <Card className="border-white/10 bg-[#141414]">
            <CardHeader>
              <CardTitle className="text-white text-lg">Account</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="username" className="text-white">Username</Label>
                <Input
                  id="username"
                  value={form.username}
                  onChange={(e) => update("username", e.target.value)}
                  required
                  className="bg-[#0A0A0A] border-white/10 text-white"
                  data-testid="edit-profile-username"
                />
                <p className="text-xs text-[#A1A1AA] mt-1">3-32 chars · letters, numbers, _ . -</p>
              </div>
              <div>
                <Label htmlFor="email" className="text-white">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={form.email}
                  onChange={(e) => update("email", e.target.value)}
                  required
                  className="bg-[#0A0A0A] border-white/10 text-white"
                  data-testid="edit-profile-email"
                />
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-[#141414]">
            <CardHeader>
              <CardTitle className="text-white text-lg">Fandom <span className="text-xs text-[#A1A1AA] font-normal">(optional)</span></CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="sport" className="text-white">Favourite sport</Label>
                <Select value={form.favourite_sport || undefined} onValueChange={(v) => update("favourite_sport", v)}>
                  <SelectTrigger id="sport" className="bg-[#0A0A0A] border-white/10 text-white" data-testid="edit-profile-sport">
                    <SelectValue placeholder="Pick a sport" />
                  </SelectTrigger>
                  <SelectContent>
                    {SPORT_OPTIONS.map((s) => (
                      <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="team" className="text-white">Favourite team</Label>
                <Input
                  id="team"
                  value={form.favourite_team}
                  onChange={(e) => update("favourite_team", e.target.value)}
                  placeholder="e.g. Toronto Maple Leafs"
                  className="bg-[#0A0A0A] border-white/10 text-white"
                  data-testid="edit-profile-favourite-team"
                />
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-[#141414]">
            <CardHeader>
              <CardTitle className="text-white text-lg">Location <span className="text-xs text-[#A1A1AA] font-normal">(optional)</span></CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              <div>
                <Label htmlFor="city" className="text-white">City</Label>
                <Input
                  id="city"
                  value={form.city}
                  onChange={(e) => update("city", e.target.value)}
                  className="bg-[#0A0A0A] border-white/10 text-white"
                  data-testid="edit-profile-city"
                />
              </div>
              <div>
                <Label htmlFor="state" className="text-white">Province/State</Label>
                <Input
                  id="state"
                  value={form.province_state}
                  onChange={(e) => update("province_state", e.target.value)}
                  className="bg-[#0A0A0A] border-white/10 text-white"
                  data-testid="edit-profile-province-state"
                />
              </div>
              <div>
                <Label htmlFor="country" className="text-white">Country</Label>
                <Input
                  id="country"
                  value={form.country}
                  onChange={(e) => update("country", e.target.value)}
                  className="bg-[#0A0A0A] border-white/10 text-white"
                  data-testid="edit-profile-country"
                />
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => navigate(-1)}
              data-testid="edit-profile-cancel"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={busy}
              className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
              data-testid="edit-profile-save"
            >
              {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              Save changes
            </Button>
          </div>
        </form>
      </div>
    </AppLayout>
  );
}
