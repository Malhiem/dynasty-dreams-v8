// @ts-nocheck
/* Small layout primitives shared between UserDetailDrawer and UserExtensionsSection. */
import React from "react";

export function DetailGrid({ children }) {
  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">{children}</div>;
}

export function DetailRow({ k, v }) {
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="text-xs text-muted-foreground min-w-[100px]">{k}</span>
      <span className="flex-1 break-all">{v}</span>
    </div>
  );
}
