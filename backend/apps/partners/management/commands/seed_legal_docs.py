"""Load the bundled legal texts (apps/partners/legal_seed/*.html) into the
admin-editable documents: the partner public offer + privacy / terms / refund,
each in uz / ru / en.

    manage.py seed_legal_docs                       # fill only empty documents
    manage.py seed_legal_docs --force               # overwrite existing text
    manage.py seed_legal_docs --company "…" --tin … --address "…" \\
        --bank "…" --email legal@example.uz         # substitute requisites

Requisite tokens ({{COMPANY_NAME}} …) left without a value are rendered as a
visible "[to be filled]" marker in the document's own language, so nothing
looks final by accident. Bodies go through the same sanitiser as the editor.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from apps.core.sanitize import sanitize_html
from apps.partners.models import (
    DOC_LANGS,
    LEGAL_KINDS,
    doc_field,
    get_legal_document,
    get_offer_document,
)

SEED_DIR = Path(__file__).resolve().parents[2] / "legal_seed"
DOCS = ("offer", *sorted(LEGAL_KINDS))
MISSING = {"uz": "[to'ldiriladi]", "ru": "[будет заполнено]", "en": "[to be filled]"}
MONTHS = {
    "uz": ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
           "sentabr", "oktabr", "noyabr", "dekabr"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}


def _date_text(day: date, lang: str) -> str:
    month = MONTHS[lang][day.month - 1]
    if lang == "uz":
        return f"{day.year}-yil {day.day}-{month}"
    if lang == "ru":
        return f"{day.day} {month} {day.year} г."
    return f"{month} {day.day}, {day.year}"


class Command(BaseCommand):
    help = "Seed the public offer and legal pages (uz/ru/en) from bundled HTML."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--force", action="store_true", help="overwrite non-empty documents")
        parser.add_argument("--only", choices=DOCS, help="seed a single document")
        parser.add_argument("--company", default="")
        parser.add_argument("--tin", default="")
        parser.add_argument("--address", default="")
        parser.add_argument("--bank", default="")
        parser.add_argument("--email", default="")
        parser.add_argument("--date", default="", help="effective date, YYYY-MM-DD (default: today)")

    def handle(self, *args: Any, **opts: Any) -> None:
        effective = date.fromisoformat(opts["date"]) if opts["date"] else date.today()
        tokens = {
            "COMPANY_NAME": opts["company"],
            "TIN": opts["tin"],
            "ADDRESS": opts["address"],
            "BANK_DETAILS": opts["bank"],
            "EMAIL": opts["email"],
        }
        for name in [opts["only"]] if opts["only"] else DOCS:
            doc = get_offer_document() if name == "offer" else get_legal_document(name)
            changed = []
            for lang in DOC_LANGS:
                path = SEED_DIR / f"{name}.{lang}.html"
                if not path.exists():
                    self.stderr.write(f"  missing seed file: {path.name}")
                    continue
                current = getattr(doc, doc_field(lang))
                # "Test uchun"-style stubs count as empty.
                if current and len(current) > 200 and not opts["force"]:
                    continue
                body = path.read_text(encoding="utf-8")
                if not tokens["EMAIL"]:
                    # No address yet → plain marker instead of a dead mailto: link.
                    body = re.sub(
                        r'<a href="mailto:\{\{EMAIL\}\}"[^>]*>(.*?)</a>', r"\1", body, flags=re.S
                    )
                for token, value in tokens.items():
                    body = body.replace("{{" + token + "}}", value or MISSING[lang])
                body = body.replace("{{EFFECTIVE_DATE}}", _date_text(effective, lang))
                # The sanitiser keeps only absolute links — anchor site-relative ones.
                body = body.replace('href="/', 'href="https://doocall.uz/')
                clean = sanitize_html(body)
                if clean != current:
                    setattr(doc, doc_field(lang), clean)
                    changed.append(lang)
            if changed:
                doc.version += 1
                doc.save()
            self.stdout.write(
                f"{name}: {'updated ' + ','.join(changed) + f' → v{doc.version}' if changed else 'unchanged'}"
            )
