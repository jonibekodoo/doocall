/** Staff monitoring ("Xodimlar nazorati") is hidden for now: the URL just
 * redirects to the cabinet. The coming-soon teaser lives in git history
 * (504f4e0, app/cabinet/monitoring/page.tsx) — restore it from there and
 * re-add the nav item in components/shell/Sidebar.tsx to enable. */

import { redirect } from "next/navigation";

export default function MonitoringPage() {
  redirect("/cabinet");
}
