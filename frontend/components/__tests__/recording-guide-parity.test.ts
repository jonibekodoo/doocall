import { describe, it, expect } from "vitest";
import { GUIDES } from "@/content/recording-guide";
import type { GuideBlock } from "@/content/recording-guide.types";

const shape = (bs: GuideBlock[]): unknown[] =>
  bs.map((b) => {
    if (b.t === "details") return ["details", shape(b.blocks)];
    if (b.t === "steps" || b.t === "list") return [b.t, b.items.length];
    if (b.t === "table") return [b.t, b.head.length, b.rows.length];
    if (b.t === "links") return [b.t, b.items.map((i) => i.href)];
    if (b.t === "video") return [b.t, b.href];
    return [b.t];
  });
const urls = (bs: GuideBlock[]): string[] =>
  JSON.stringify(bs).match(/https?:\/\/[^\s)"\\]+/g) ?? [];
const sec = (l: "uz" | "ru" | "en", id: string) =>
  GUIDES[l].sections.find((s) => s.id === id)!;

describe("recording guide locale parity", () => {
  it("same section ids and block shapes in uz/ru/en", () => {
    for (const l of ["ru", "en"] as const) {
      expect(GUIDES[l].sections.map((s) => s.id)).toEqual(GUIDES.uz.sections.map((s) => s.id));
      GUIDES.uz.sections.forEach((s, i) =>
        expect(shape(GUIDES[l].sections[i].blocks)).toEqual(shape(s.blocks)),
      );
    }
  });
  it("same URLs per section across locales", () => {
    for (const s of GUIDES.uz.sections)
      for (const l of ["ru", "en"] as const)
        expect(urls(sec(l, s.id).blocks).sort()).toEqual(urls(s.blocks).sort());
  });
  it("Xiaomi has ADB video at t=39 and no Telegram-channel leftovers", () => {
    for (const l of ["uz", "ru", "en"] as const) {
      const xi = GUIDES[l].sections.find((s) => s.tone === "xiaomi")!;
      const json = JSON.stringify(xi.blocks);
      expect(json).toContain("youtu.be/JQrMvecOAeE?t=39");
      expect(json).toContain("developer.android.com");
      expect(json).toContain("drive.google.com");
      expect(json).not.toMatch(/t\.me\//);
    }
  });
  it("no empty strings in items/text", () => {
    const walk = (bs: GuideBlock[]) =>
      bs.forEach((b) => {
        if (b.t === "details") { expect(b.summary.trim()).not.toBe(""); walk(b.blocks); }
        else if (b.t === "steps" || b.t === "list") b.items.forEach((x) => expect(x.trim()).not.toBe(""));
        else if ("text" in b) expect(b.text.trim()).not.toBe("");
      });
    for (const l of ["uz", "ru", "en"] as const) GUIDES[l].sections.forEach((s) => walk(s.blocks));
  });
});
