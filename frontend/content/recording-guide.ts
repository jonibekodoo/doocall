import type { GuideContent } from "./recording-guide.types";
import { en } from "./recording-guide.en";
import { ru } from "./recording-guide.ru";
import { uz } from "./recording-guide.uz";

export const GUIDES: Record<"uz" | "ru" | "en", GuideContent> = { uz, ru, en };
