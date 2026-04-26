// @ts-nocheck
import { useRef, useState } from "react";
import api from "@/lib/api";
import { Camera, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import TeamLogo from "@/lovable/components/TeamLogo";
import { Button } from "@/components/ui/button";

const ACCEPTED = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"];
const MAX_BYTES = 1 * 1024 * 1024; // 1 MB

/**
 * TeamLogoUploader — circular logo with a hover-camera that opens a file
 * picker. Validates type + size client-side before uploading. On success,
 * calls onChange(newLogoUrl). Shows a spinner while uploading.
 *
 * Only render this when the current user has rights to edit `teamId` (own
 * team or commissioner mode); otherwise just render <TeamLogo /> directly.
 */
export default function TeamLogoUploader({
  teamId,
  name,
  abbr,
  logo,
  size = "lg",
  onChange,
}: {
  teamId: string;
  name: string;
  abbr?: string;
  logo?: string | null;
  size?: "sm" | "md" | "lg" | "xl";
  onChange?: (logoUrl: string | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);

  const pickFile = () => inputRef.current?.click();

  const handleFile = async (file: File) => {
    if (!ACCEPTED.includes(file.type)) {
      toast.error("Unsupported image type. Use PNG, JPEG, WEBP, or GIF.");
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
      const { data } = await api.post(`/teams/${teamId}/logo`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Team logo updated");
      onChange?.(data?.logo_url || null);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to upload logo");
    } finally {
      setBusy(false);
    }
  };

  const removeLogo = async () => {
    setBusy(true);
    try {
      await api.delete(`/teams/${teamId}/logo`);
      toast.success("Team logo removed");
      onChange?.(null);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to remove logo");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative group" data-testid="team-logo-uploader">
      <TeamLogo logo={logo || undefined} name={name} abbr={abbr} size={size} />

      <button
        type="button"
        onClick={pickFile}
        disabled={busy}
        title="Change team logo"
        data-testid="team-logo-upload-btn"
        className="absolute inset-0 flex items-center justify-center rounded-lg bg-black/55 text-white opacity-0 group-hover:opacity-100 transition-opacity disabled:cursor-not-allowed"
      >
        {busy ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Camera className="h-5 w-5" />
        )}
      </button>

      {logo && !busy && (
        <Button
          type="button"
          variant="destructive"
          size="icon"
          onClick={removeLogo}
          title="Remove logo"
          data-testid="team-logo-remove-btn"
          className="absolute -top-1 -right-1 h-6 w-6 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(",")}
        className="hidden"
        data-testid="team-logo-file-input"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
          if (inputRef.current) inputRef.current.value = "";
        }}
      />
    </div>
  );
}
