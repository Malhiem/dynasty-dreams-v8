/**
 * Iter 207 — Lightweight device fingerprint.
 *
 * Generates a stable per-browser hash by combining the user-agent,
 * screen resolution, color depth, timezone, language, hardware
 * concurrency, and a 1x1 canvas render. Used by the backend's
 * `user_login_audit` collection for multi-account detection across
 * different IPs / VPNs.
 *
 * NOT a security-critical primitive — sophisticated actors can spoof
 * this trivially. It's a moderation signal, not authentication.
 */
async function _sha256(str) {
  try {
    const enc = new TextEncoder().encode(str);
    const buf = await crypto.subtle.digest("SHA-256", enc);
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    // Fallback hash (Java string hash variant)
    let h = 0;
    for (let i = 0; i < str.length; i++) {
      h = ((h << 5) - h + str.charCodeAt(i)) | 0;
    }
    return String(h);
  }
}

function _canvasFingerprint() {
  try {
    const cv = document.createElement("canvas");
    cv.width = 200; cv.height = 50;
    const ctx = cv.getContext("2d");
    ctx.textBaseline = "top";
    ctx.font = "14px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(0, 0, 200, 50);
    ctx.fillStyle = "#069";
    ctx.fillText("DynastyDreams.fp.v1", 2, 15);
    ctx.strokeStyle = "rgba(0,0,128,0.7)";
    ctx.strokeText("DynastyDreams.fp.v1", 4, 17);
    return cv.toDataURL();
  } catch {
    return "no-canvas";
  }
}

export async function getDeviceHash() {
  try {
    const parts = [
      navigator.userAgent || "",
      navigator.language || "",
      navigator.hardwareConcurrency || "",
      navigator.platform || "",
      `${screen.width}x${screen.height}x${screen.colorDepth}`,
      Intl.DateTimeFormat().resolvedOptions().timeZone || "",
      _canvasFingerprint(),
    ];
    return await _sha256(parts.join("|"));
  } catch {
    return null;
  }
}
