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
 * theme colour, and logo (URL or file upload). Wired to PUT /teams/{id}
 * for name/abbr/url/theme_color and POST /teams/{id}/logo for file
 * upload, DELETE /teams/{id}/logo to remove.
 */
const COLOR_PRESETS: { id: string; label: string; hex: string }[] = [
  // Iter 230ai — Expanded palette: 6 → 16 swatches covering the main
  // colour wheel plus warm/cool greys. Users can also drop any hex
  // via the custom `<input type="color">` next to the presets, so the
  // total addressable space is the full 24-bit gamut.
  { id: "ice",        label: "Ice Blue",    hex: "#0ea5e9" },
  { id: "navy",       label: "Navy",         hex: "#1e3a8a" },
  { id: "fire",       label: "Forge Red",    hex: "#ef4444" },
  { id: "crimson",    label: "Crimson",      hex: "#9f1239" },
  { id: "forest",     label: "Pine Green",   hex: "#22c55e" },
  { id: "emerald",    label: "Emerald",      hex: "#047857" },
  { id: "teal",       label: "Teal",         hex: "#0d9488" },
  { id: "royal",      label: "Royal Gold",   hex: "#f59e0b" },
  { id: "sunshine",   label: "Sunshine",     hex: "#fde047" },
  { id: "orange",     label: "Burnt Orange", hex: "#ea580c" },
  { id: "violet",     label: "Twilight",     hex: "#8b5cf6" },
  { id: "magenta",    label: "Magenta",      hex: "#c026d3" },
  { id: "rose",       label: "Sunset",       hex: "#f43f5e" },
  { id: "pink",       label: "Bubblegum",    hex: "#ec4899" },
  { id: "slate",      label: "Slate",        hex: "#475569" },
  { id: "graphite",   label: "Graphite",     hex: "#27272a" },
];

export default function TeamSettingsModal({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { myTeam, reloadTeams } = useActiveLeague();
  const [name, setName] = useState("");
  const [abbr, setAbbr] = useState("");
  const [themeColor, setThemeColor] = useState<string | null>(null);
  const [logoUrl, setLogoUrl] = useState("");
  const [previewLogo, setPreviewLogo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (myTeam && open) {
      setName(myTeam.name || "");
      setAbbr(myTeam.logo_abbr || "");
      setThemeColor(myTeam.theme_color || null);
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
            <DialogDescription>You don&apos;t have a team in any league yet.</DialogDescription>
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
      // Iter 230ae — Theme colour persisted alongside name/abbr.
      // Sending `null` explicitly clears any previously-set colour.
      const currentColor = myTeam.theme_color || null;
      if (themeColor !== currentColor) payload.theme_color = themeColor;
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

            {/* Iter 230ae — Theme colour picker. Persists to
                `team.theme_color` (already supported by TeamUpdateInput);
                surfaces wherever TeamLogo renders (standings,
                trade-block, draft board) as the background tint when no
                uploaded logo is present. Owners can re-pick or clear
                at any time. */}
            <div>
              <Label className="text-white">Team colour</Label>
              <div className="flex items-center gap-3 mt-1.5">
                <div
                  className="h-10 w-10 rounded-md flex items-center justify-center text-xs font-semibold border border-white/10"
                  style={{ backgroundColor: themeColor || "transparent" }}
                  data-testid="team-settings-color-preview"
                >
                  <span className={themeColor ? "text-white drop-shadow" : "text-[#52525B]"}>
                    {abbr || myTeam.logo_abbr || "TEAM"}
                  </span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {COLOR_PRESETS.map((p) => {
                    const isPicked = themeColor === p.hex;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => setThemeColor(isPicked ? null : p.hex)}
                        className={`h-7 w-7 rounded-full ring-offset-2 ring-offset-[#141414] transition-all hover:scale-110 ${
                          isPicked ? "ring-2 ring-white scale-110" : "ring-1 ring-white/20"
                        }`}
                        style={{ backgroundColor: p.hex }}
                        aria-label={p.label}
                        title={p.label}
                        data-testid={`team-settings-color-${p.id}`}
                      />
                    );
                  })}
                  {/* Iter 230ai — Free-form custom colour via native
                      color input. Sits next to the preset row so users
                      can match a team's exact brand hex even if it's
                      not in the curated palette. */}
                  <label
                    className="relative inline-flex items-center justify-center h-7 w-7 rounded-full ring-1 ring-white/20 cursor-pointer hover:scale-110 transition-transform overflow-hidden"
                    title="Custom colour"
                    data-testid="team-settings-color-custom-label"
                  >
                    <div
                      className="absolute inset-0"
                      style={{
                        background:
                          "conic-gradient(from 0deg, #ef4444, #f59e0b, #fde047, #22c55e, #0d9488, #0ea5e9, #8b5cf6, #ec4899, #ef4444)",
                      }}
                    />
                    <input
                      type="color"
                      value={themeColor || "#0ea5e9"}
                      onChange={(e) => setThemeColor(e.target.value)}
                      className="absolute inset-0 opacity-0 cursor-pointer"
                      data-testid="team-settings-color-custom"
                      aria-label="Custom colour"
                    />
                  </label>
                  {themeColor && (
                    <button
                      type="button"
                      onClick={() => setThemeColor(null)}
                      className="text-xs text-[#A1A1AA] hover:text-white underline"
                      data-testid="team-settings-color-clear"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
              {themeColor && (
                <p className="text-[10px] text-[#A1A1AA] mt-1 font-mono" data-testid="team-settings-color-hex">
                  {themeColor.toUpperCase()}
                </p>
              )}
              <p className="text-xs text-[#A1A1AA] mt-1">
                Used as a background tint when no logo is uploaded. Pick a preset above or click the rainbow swatch for any custom colour.
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
