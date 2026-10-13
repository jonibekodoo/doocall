import { useId } from "react";

/** Official Kotib Analytics mark (kotib.ai), inlined so it renders in both the
 * cabinet and the landing without an extra request. The gradient id comes
 * from useId so several marks on one page don't share/clash defs. */
export function KotibLogo({
  className,
  decorative = false,
}: {
  className?: string;
  /** Hide from assistive tech when a visible "Kotib" label sits next to it. */
  decorative?: boolean;
}) {
  const gradientId = `kotib-gradient-${useId().replace(/:/g, "")}`;
  return (
    <svg
      viewBox="0 0 617 410"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      {...(decorative
        ? { "aria-hidden": true }
        : { role: "img", "aria-label": "Kotib" })}
      data-testid="kotib-logo"
    >
      <path
        d="M532.113 409.719H418.025C387.737 409.719 359.762 393.547 344.639 367.305L206.172 127.24C173.549 70.6818 214.333 0 279.558 0H419.74C433.872 0 446.929 7.54794 453.995 19.7901L605.519 282.479C638.142 339.037 597.359 409.719 532.133 409.719H532.113Z"
        fill={`url(#${gradientId})`}
      />
      <path
        d="M84.8573 409.719H198.903C229.181 409.719 257.145 393.547 272.263 367.305L452.192 55.255C466.36 30.688 448.66 0 420.324 0H223.253C192.976 0 165.012 16.1712 149.894 42.4132L11.4771 282.479C-21.134 339.037 19.635 409.719 84.8366 409.719H84.8573Z"
        fill="#981BFF"
      />
      <defs>
        <radialGradient
          id={gradientId}
          cx="0"
          cy="0"
          r="1"
          gradientUnits="userSpaceOnUse"
          gradientTransform="translate(256.191 14.248) scale(464.573 464.994)"
        >
          <stop stopColor="#1E0038" />
          <stop offset="1" stopColor="#981BFF" />
        </radialGradient>
      </defs>
    </svg>
  );
}

/** Tile lockup: the mark + bold "Kotib" wordmark. Tiles are `bg-white
 * dark:bg-surface-2`, and surface-2 follows the app theme ([data-theme]), so
 * the tile is only dark (#222625) under OS-dark AND data-theme=dark. The
 * wordmark mirrors that: #981BFF on white/#f1f1ee (5.34 / 4.71:1), #B77BFF on
 * #222625 (5.31:1) — WCAG AA everywhere. */
export function KotibTileLogo() {
  return (
    <span className="inline-flex items-center gap-1.5">
      <KotibLogo className="h-6 w-auto" decorative />
      <span className="text-lg font-extrabold text-[#981BFF] dark:[[data-theme=dark]_&]:text-[#B77BFF]">
        Kotib
      </span>
    </span>
  );
}
