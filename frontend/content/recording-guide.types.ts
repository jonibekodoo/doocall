/** Structured content for the built-in call-recording guide.
 * One typed tree per locale — rendered by GuideRenderer with landing tokens.
 * Inline markup inside strings: **bold**, `code`, [label](https://url). */

export type GuideBlock =
  | { t: "p"; text: string }
  | { t: "h3"; text: string }
  | { t: "table"; head: string[]; rows: string[][] }
  | { t: "steps"; items: string[] }
  | { t: "list"; items: string[] }
  | { t: "note" | "tip" | "warn" | "danger"; text: string }
  | { t: "details"; summary: string; blocks: GuideBlock[]; open?: boolean }
  | { t: "links"; items: { label: string; href: string }[] }
  | { t: "video"; href: string; label: string };

export interface GuideSection {
  id: string;
  title: string;
  /** Brand accent for the section chip (landing palette). */
  tone?: "default" | "samsung" | "xiaomi" | "huawei";
  blocks: GuideBlock[];
}

export interface GuideContent {
  metaTitle: string;
  metaDescription: string;
  heroTitle: string;
  heroText: string;
  tocTitle: string;
  backToLanding: string;
  supportNote: string;
  legalNote: string;
  sections: GuideSection[];
}
