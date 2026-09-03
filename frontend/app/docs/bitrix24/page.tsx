/** Bitrix24 connection guide (ru/uz/en via doocall_locale cookie). */

import { getLocale } from "next-intl/server";

import {
  DocsCode,
  DocsList,
  DocsNote,
  DocsSection,
  DocsShell,
} from "@/components/docs-ui";

export const metadata = {
  title: "DooCall — Bitrix24 integration guide",
  description: "How to connect Bitrix24 to DooCall.",
};

interface GuideSection {
  step?: number;
  title: string;
  body: React.ReactNode;
}

interface Guide {
  title: string;
  intro: string;
  apiDocsLabel: string;
  footer: string;
  sections: GuideSection[];
}

const RU: Guide = {
  title: "Интеграция с Bitrix24",
  intro:
    "После подключения каждый завершённый звонок из мобильного приложения DooCall автоматически регистрируется в Битрикс24 как телефонный звонок: для незнакомых номеров Битрикс24 сам создаёт лид, запись разговора прикрепляется к звонку или публикуется в ленте CRM.",
  apiDocsLabel: "API документация",
  footer: "© DooCall. Вопросы по интеграции: поддержка в вашем кабинете.",
  sections: [
    {
      step: 1,
      title: "Создайте входящий вебхук",
      body: (
        <>
          <p>
            В Битрикс24 откройте: <b>Разработчикам</b> (левое меню) →{" "}
            <b>Другое</b> → <b>«Входящий вебхук»</b>. Откроется страница с
            готовой ссылкой вида:
          </p>
          <DocsCode>{`https://ваш-портал.bitrix24.ru/rest/1/xxxxxxxxxxxxxxxx/`}</DocsCode>
        </>
      ),
    },
    {
      step: 2,
      title: "Настройте права (самый важный шаг)",
      body: (
        <>
          <p>
            В блоке <b>«Настройка прав»</b> нажмите «+ выбрать» и добавьте
            ДВА права:
          </p>
          <DocsList
            items={[
              <>
                <b>«Телефония (telephony)»</b> — регистрация звонков;
              </>,
              <>
                <b>«CRM (crm)»</b> — создание лидов и публикация ссылки на
                запись в ленту.
              </>,
            ]}
          />
          <DocsNote kind="warning">
            Не перепутайте: в списке есть похожий пункт «Телефония
            (совершение звонков) <b>(call)</b>» — он НЕ подходит. Нужен
            именно пункт с «<b>(telephony)</b>» в скобках. Затем нажмите
            «Сохранить».
          </DocsNote>
          <DocsNote>
            При изменении прав или нажатии «Перегенерировать» код ссылки
            может измениться — после сохранения сверьте URL и при
            необходимости обновите его в DooCall.
          </DocsNote>
        </>
      ),
    },
    {
      step: 3,
      title: "Подключите в DooCall",
      body: (
        <>
          <p>
            В кабинете DooCall: <b>Настройки → Интеграция → Bitrix24</b>.
            Заполните:
          </p>
          <DocsList
            items={[
              <>
                <b>URL входящего вебхука</b> — ссылка из шага 1 целиком;
              </>,
              <>
                <b>ID пользователя Bitrix24</b> — сотрудник, за которым
                фиксируются звонки (по умолчанию 1 — администратор);
              </>,
              <>
                <b>Адрес аккаунта</b> — для справки, например{" "}
                <code>ваш-портал.bitrix24.ru</code>.
              </>,
            ]}
          />
          <p>
            Нажмите <b>«Подключить»</b>, затем{" "}
            <b>«Проверить подключение»</b>.
          </p>
        </>
      ),
    },
    {
      title: "Как это работает",
      body: (
        <DocsList
          items={[
            "Звонок регистрируется через telephony.externalcall.register и завершается finish — он попадает в статистику телефонии и в карточку CRM.",
            "Незнакомый номер → Битрикс24 автоматически создаёт лид (CRM_CREATE).",
            "Статусы: успешный (200), недозвон (304), занято (486), отклонён (603).",
            "Запись в mp3/wav прикрепляется прямо к звонку; другие форматы (например .ogg с Android) публикуются постоянной ссылкой в ленту лида/контакта.",
            "Повторная отправка того же звонка в течение 30 минут не создаёт дубликатов (EXTERNAL_CALL_ID).",
          ]}
        />
      ),
    },
    {
      title: "Возможные проблемы",
      body: (
        <DocsList
          items={[
            <>
              <b>insufficient_scope</b> — вебхуку не хватает права
              «Телефония (telephony)» (см. шаг 2);
            </>,
            <>
              <b>INVALID_CREDENTIALS</b> — ссылка вебхука изменилась или
              вебхук удалён: скопируйте актуальный URL и обновите его в
              DooCall;
            </>,
            <>
              Звонок не появился — проверьте статус на странице Bitrix24 в
              кабинете DooCall и что интеграция включена.
            </>,
          ]}
        />
      ),
    },
  ],
};

const UZ: Guide = {
  title: "Bitrix24 bilan integratsiya",
  intro:
    "Ulangandan so'ng DooCall mobil ilovasidagi har bir tugagan qo'ng'iroq Bitrix24'da telefon qo'ng'irog'i sifatida avtomatik ro'yxatga olinadi: notanish raqamlar uchun Bitrix24 o'zi lid yaratadi, audio yozuv qo'ng'iroqqa biriktiriladi yoki CRM lentasiga joylanadi.",
  apiDocsLabel: "API hujjatlari",
  footer: "© DooCall. Integratsiya bo'yicha savollar: kabinetingizdagi qo'llab-quvvatlash.",
  sections: [
    {
      step: 1,
      title: "Kiruvchi vebhuk yarating",
      body: (
        <>
          <p>
            Bitrix24'da oching: <b>Разработчикам</b> (chap menyu) →{" "}
            <b>Другое</b> → <b>«Входящий вебхук»</b>. Quyidagi ko'rinishdagi
            tayyor havolali sahifa ochiladi:
          </p>
          <DocsCode>{`https://portalingiz.bitrix24.ru/rest/1/xxxxxxxxxxxxxxxx/`}</DocsCode>
        </>
      ),
    },
    {
      step: 2,
      title: "Huquqlarni sozlang (eng muhim qadam)",
      body: (
        <>
          <p>
            <b>«Настройка прав»</b> blokida «+ выбрать»ni bosib IKKITA
            huquqni qo'shing:
          </p>
          <DocsList
            items={[
              <>
                <b>«Телефония (telephony)»</b> — qo'ng'iroqlarni ro'yxatga
                olish;
              </>,
              <>
                <b>«CRM (crm)»</b> — lid yaratish va yozuv havolasini
                lentaga joylash.
              </>,
            ]}
          />
          <DocsNote kind="warning">
            Adashtirmang: ro'yxatda o'xshash «Телефония (совершение звонков){" "}
            <b>(call)</b>» bandi ham bor — u TO'G'RI KELMAYDI. Qavsida
            aynan «<b>(telephony)</b>» yozilgani kerak. So'ng
            «Сохранить»ni bosing.
          </DocsNote>
          <DocsNote>
            Huquqlar o'zgartirilganda yoki «Перегенерировать» bosilganda
            havola kodi o'zgarishi mumkin — saqlagach URL'ni solishtiring
            va kerak bo'lsa DooCall'da yangilang.
          </DocsNote>
        </>
      ),
    },
    {
      step: 3,
      title: "DooCall'da ulang",
      body: (
        <>
          <p>
            DooCall kabinetida: <b>Sozlamalar → Integratsiya → Bitrix24</b>.
            To'ldiring:
          </p>
          <DocsList
            items={[
              <>
                <b>Kiruvchi vebhuk URL</b> — 1-qadamdagi havola to'liq
                holda;
              </>,
              <>
                <b>Bitrix24 foydalanuvchi ID</b> — qo'ng'iroqlar kim nomidan
                yozilishi (odatda 1 — administrator);
              </>,
              <>
                <b>Akkaunt manzili</b> — ma'lumot uchun, masalan{" "}
                <code>portalingiz.bitrix24.ru</code>.
              </>,
            ]}
          />
          <p>
            <b>«Ulash»</b>ni, so'ng <b>«Ulanishni tekshirish»</b>ni bosing.
          </p>
        </>
      ),
    },
    {
      title: "Qanday ishlaydi",
      body: (
        <DocsList
          items={[
            "Qo'ng'iroq telephony.externalcall.register orqali ro'yxatga olinib, finish bilan yakunlanadi — telefoniya statistikasi va CRM kartochkasiga tushadi.",
            "Notanish raqam → Bitrix24 avtomatik lid yaratadi (CRM_CREATE).",
            "Statuslar: muvaffaqiyatli (200), javob berilmadi (304), band (486), rad etildi (603).",
            "mp3/wav yozuvlar to'g'ridan-to'g'ri qo'ng'iroqqa biriktiriladi; boshqa formatlar (masalan Android'dagi .ogg) doimiy havola sifatida lid/kontakt lentasiga joylanadi.",
            "Ayni qo'ng'iroq 30 daqiqa ichida qayta yuborilsa dublikat hosil bo'lmaydi (EXTERNAL_CALL_ID).",
          ]}
        />
      ),
    },
    {
      title: "Yuzaga kelishi mumkin bo'lgan muammolar",
      body: (
        <DocsList
          items={[
            <>
              <b>insufficient_scope</b> — vebhukda «Телефония (telephony)»
              huquqi yetishmayapti (2-qadamga qarang);
            </>,
            <>
              <b>INVALID_CREDENTIALS</b> — vebhuk havolasi o'zgargan yoki
              o'chirilgan: amaldagi URL'ni nusxalab DooCall'da yangilang;
            </>,
            <>
              Qo'ng'iroq tushmadi — DooCall kabinetidagi Bitrix24
              sahifasida statusni va integratsiya yoqilganini tekshiring.
            </>,
          ]}
        />
      ),
    },
  ],
};

const EN: Guide = {
  title: "Bitrix24 integration",
  intro:
    "Once connected, every finished call from the DooCall mobile app is registered in Bitrix24 as a telephony call: for unknown numbers Bitrix24 creates a lead itself, and the recording is attached to the call or posted to the CRM timeline.",
  apiDocsLabel: "API docs",
  footer: "© DooCall. Integration questions: support in your cabinet.",
  sections: [
    {
      step: 1,
      title: "Create an inbound webhook",
      body: (
        <>
          <p>
            In Bitrix24 open: <b>Developer resources</b> (left menu) →{" "}
            <b>Other</b> → <b>“Inbound webhook”</b>. A page opens with a
            ready link like:
          </p>
          <DocsCode>{`https://your-portal.bitrix24.ru/rest/1/xxxxxxxxxxxxxxxx/`}</DocsCode>
        </>
      ),
    },
    {
      step: 2,
      title: "Set permissions (the crucial step)",
      body: (
        <>
          <p>
            In the <b>“Permission settings”</b> block press “+ select” and
            add TWO scopes:
          </p>
          <DocsList
            items={[
              <>
                <b>“Telephony (telephony)”</b> — registering calls;
              </>,
              <>
                <b>“CRM (crm)”</b> — creating leads and posting the
                recording link to the timeline.
              </>,
            ]}
          />
          <DocsNote kind="warning">
            Don't confuse it with the similar “Telephony (making calls){" "}
            <b>(call)</b>” item — it will NOT work. You need the one with
            “<b>(telephony)</b>” in parentheses. Then press Save.
          </DocsNote>
          <DocsNote>
            Changing permissions or pressing “Regenerate” may change the
            webhook code — after saving, compare the URL and update it in
            DooCall if needed.
          </DocsNote>
        </>
      ),
    },
    {
      step: 3,
      title: "Connect in DooCall",
      body: (
        <>
          <p>
            In the DooCall cabinet: <b>Settings → Integration → Bitrix24</b>.
            Fill in:
          </p>
          <DocsList
            items={[
              <>
                <b>Inbound webhook URL</b> — the full link from step 1;
              </>,
              <>
                <b>Bitrix24 user ID</b> — the employee calls are logged
                under (default 1 — the administrator);
              </>,
              <>
                <b>Account address</b> — informational, e.g.{" "}
                <code>your-portal.bitrix24.ru</code>.
              </>,
            ]}
          />
          <p>
            Press <b>Connect</b>, then <b>Test connection</b>.
          </p>
        </>
      ),
    },
    {
      title: "How it works",
      body: (
        <DocsList
          items={[
            "A call is registered via telephony.externalcall.register and completed with finish — it lands in telephony statistics and on the CRM card.",
            "Unknown number → Bitrix24 automatically creates a lead (CRM_CREATE).",
            "Statuses: successful (200), missed (304), busy (486), declined (603).",
            "mp3/wav recordings attach directly to the call; other formats (e.g. Android .ogg) are posted as a permanent link to the lead/contact timeline.",
            "Re-sending the same call within 30 minutes creates no duplicates (EXTERNAL_CALL_ID).",
          ]}
        />
      ),
    },
    {
      title: "Troubleshooting",
      body: (
        <DocsList
          items={[
            <>
              <b>insufficient_scope</b> — the webhook lacks the “Telephony
              (telephony)” scope (see step 2);
            </>,
            <>
              <b>INVALID_CREDENTIALS</b> — the webhook link changed or the
              webhook was deleted: copy the current URL and update it in
              DooCall;
            </>,
            <>
              A call did not show up — check the status on the Bitrix24
              page in the DooCall cabinet and that the integration is
              enabled.
            </>,
          ]}
        />
      ),
    },
  ],
};

const CONTENT: Record<string, Guide> = { ru: RU, uz: UZ, en: EN };

export default async function Bitrix24GuidePage() {
  const locale = await getLocale();
  const guide = CONTENT[locale] ?? RU;
  return (
    <DocsShell
      title={guide.title}
      intro={guide.intro}
      apiDocsLabel={guide.apiDocsLabel}
      footer={guide.footer}
    >
      {guide.sections.map((section) => (
        <DocsSection key={section.title} step={section.step} title={section.title}>
          {section.body}
        </DocsSection>
      ))}
    </DocsShell>
  );
}
