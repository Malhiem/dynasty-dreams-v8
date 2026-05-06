// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Loader2, Camera, Trash2, Image as ImageIcon, Save } from "lucide-react";
import { toast } from "sonner";
import TeamLogo from "@/lovable/components/TeamLogo";

const ACCEPTED = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"];
const MAX_BYTES = 1 * 1024 * 1024;

/**
 * TeamSettingsModal — edit team name, abbreviation (max 3 chars),
 * and logo (URL or file upload). Wired to PUT /teams/{id} for name/abbr/url
 * and POST /teams/{id}/logo for file upload, DELETE /teams/{id}/logo to remove.
 */
export default function TeamSettingsModal({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { myTeam, reloadTeams } = useActiveLeague();
  const [name, setName] = useState("");
  const [abbr, setAbbr] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [previewLogo, setPreviewLogo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (myTeam && open) {
      setName(myTeam.name || "");
      setAbbr(myTeam.logo_abbr || "");
      setLogoUrl("");
      setPreviewLogo(myTeam.logo_url || null);
    }
  }, [myTeam, open]);

  if (!myTeam) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="bg-[#141414] border-white/10" data-testid="team-settings-modal">
          <DialogHeader>
            <DialogTitle className="text-white">Team Settings</DialogTitle>
            <DialogDescription>You don't have a team in any league yet.</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  const saveDetails = async () => {
    setBusy(true);
    try {
      const payload: any = {};
      if (name && name !== myTeam.name) payload.name = name;
      if (abbr !== (myTeam.logo_abbr || "")) payload.logo_abbr = abbr;
      if (Object.keys(payload).length === 0) {
        toast.info("No changes to save");
        setBusy(false);
        return;
      }
      await api.put(`/teams/${myTeam.id}`, payload);
      toast.success("Team updated");
      reloadTeams();
      onOpenChange(false);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to update team");
    } finally {
      setBusy(false);
    }
  };

  const saveLogoUrl = async () => {
    if (!logoUrl) return;
    setBusy(true);
    try {
      await api.put(`/teams/${myTeam.id}`, { logo_url: logoUrl });
      toast.success("Logo URL saved");
      setPreviewLogo(logoUrl);
      reloadTeams();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save logo URL");
    } finally {
      setBusy(false);
    }
  };

  const uploadFile = async (file: File) => {
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
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(`/teams/${myTeam.id}/logo`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Logo uploaded");
      setPreviewLogo(data?.logo_url || null);
      reloadTeams();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to upload logo");
    } finally {
      setBusy(false);
    }
  };

  const removeLogo = async () => {
    setBusy(true);
    try {
      await api.delete(`/teams/${myTeam.id}/logo`);
      toast.success("Logo removed");
      setPreviewLogo(null);
      setLogoUrl("");
      reloadTeams();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to remove logo");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#141414] border-white/10 max-w-lg" data-testid="team-settings-modal">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <TeamLogo logo={previewLogo} name={myTeam.name} abbr={abbr || myTeam.logo_abbr} size="sm" />
            Team Settings
          </DialogTitle>
          <DialogDescription className="text-[#A1A1AA]">
            Update your team name, abbreviation, and logo.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="details">
          <TabsList className="grid w-full grid-cols-2 bg-[#0A0A0A]">
            <TabsTrigger value="details" data-testid="team-settings-tab-details">Details</TabsTrigger>
            <TabsTrigger value="logo" data-testid="team-settings-tab-logo">Logo</TabsTrigger>
          </TabsList>

          <TabsContent value="details" className="space-y-4 pt-3">
            <div>
              <Label htmlFor="ts-name" className="text-white">Team Name</Label>
              <Input
                id="ts-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={80}
                className="bg-[#0A0A0A] border-white/10 text-white"
                data-testid="team-settings-name-input"
              />
            </div>
            <div>
              <Label htmlFor="ts-abbr" className="text-white">Abbreviation (max 3 chars)</Label>
              <Input
                id="ts-abbr"
                value={abbr}
                onChange={(e) => setAbbr(e.target.value.toUpperCase().slice(0, 3))}
                maxLength={3}
                placeholder="e.g. ZF"
                className="bg-[#0A0A0A] border-white/10 text-white uppercase tracking-wider"
                data-testid="team-settings-abbr-input"
              />
              <p className="text-xs text-[#A1A1AA] mt-1">
                Shown on standings tables, scoreboards, and trade cards. Letters and digits only.
              </p>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-white" data-testid="team-settings-cancel">Cancel</Button>
              <Button
                onClick={saveDetails}
                disabled={busy}
                className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
                data-testid="team-settings-save-details"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                Save Details
              </Button>
            </DialogFooter>
          </TabsContent>

          <TabsContent value="logo" className="space-y-5 pt-3">
            <div className="flex justify-center py-2">
              <TeamLogo logo={previewLogo} name={myTeam.name} abbr={abbr || myTeam.logo_abbr} size="xl" />
            </div>

            <div className="space-y-2">
              <Label htmlFor="ts-url" className="text-white flex items-center gap-2">
                <ImageIcon className="h-4 w-4" /> Logo URL
              </Label>
              <div className="flex gap-2">
                <Input
                  id="ts-url"
                  value={logoUrl}
                  onChange={(e) => setLogoUrl(e.target.value)}
                  placeholder="https://example.com/logo.png"
                  className="bg-[#0A0A0A] border-white/10 text-white flex-1"
                  data-testid="team-settings-logo-url-input"
                />
                <Button
                  onClick={saveLogoUrl}
                  disabled={busy || !logoUrl}
                  className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
                  data-testid="team-settings-logo-url-save"
                >
                  Save URL
                </Button>
              </div>
              <p className="text-xs text-[#A1A1AA]">
                Paste an image URL hosted on the web (https://...).
              </p>
            </div>

            <div className="space-y-2 pt-2 border-t border-white/10">
              <Label className="text-white flex items-center gap-2">
                <Camera className="h-4 w-4" /> Or upload a file (max 1 MB)
              </Label>
              <Input
                type="file"
                accept={ACCEPTED.join(",")}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadFile(f);
                  if (e.target) e.target.value = "";
                }}
                disabled={busy}
                className="bg-[#0A0A0A] border-white/10 text-white file:bg-[#1A1A1A] file:text-white file:border-0 file:rounded file:px-3 file:py-1 file:mr-3"
                data-testid="team-settings-logo-file-input"
              />
              <p className="text-xs text-[#A1A1AA]">PNG, JPEG, WEBP, or GIF. Resized server-side to 256×256.</p>
            </div>

            {previewLogo && (
              <Button
                variant="outline"
                onClick={removeLogo}
                disabled={busy}
                className="w-full text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
                data-testid="team-settings-logo-remove"
              >
                <Trash2 className="h-4 w-4 mr-2" /> Remove logo
              </Button>
            )}

            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-white" data-testid="team-settings-close-logo">Close</Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
