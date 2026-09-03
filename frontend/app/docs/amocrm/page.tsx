/** amoCRM/Kommo connection guide (ru/uz/en via doocall_locale cookie). */

import { getLocale } from "next-intl/server";

import {
  DocsList,
  DocsNote,
  DocsSection,
  DocsShell,
} from "@/components/docs-ui";

export const metadata = {
  title: "DooCall — amoCRM integration guide",
  description: "How to connect amoCRM / Kommo to DooCall.",
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
  title: "Интеграция с amoCRM / Kommo",
  intro:
    "После подключения каждый завершённый звонок из мобильного приложения DooCall автоматически появляется в amoCRM: прикрепляется к контакту по номеру телефона (при одной активной сделке — к сделке) со ссылкой на запись разговора. Для незнакомых номеров DooCall сам создаёт контакт.",
  apiDocsLabel: "API документация",
  footer: "© DooCall. Вопросы по интеграции: поддержка в вашем кабинете.",
  sections: [
    {
      step: 1,
      title: "Создайте интеграцию в amoCRM",
      body: (
        <>
          <p>
            Войдите в amoCRM под администратором и откройте раздел
            интеграций:
          </p>
          <DocsList
            items={[
              <>
                Новый интерфейс: <b>amoМаркет</b> (левое меню) → кнопка
                «···» в правом верхнем углу → <b>«Создать интеграцию»</b>.
              </>,
              <>
                Либо прямой адрес:{" "}
                <code>
                  https://&lt;ваш-аккаунт&gt;.amocrm.ru/settings/widgets/
                </code>
              </>,
            ]}
          />
          <p>
            Выберите <b>внешнюю (частную) интеграцию</b> и заполните форму:
            название — например «DooCall»; ссылка для перенаправления —
            любой корректный URL (например <code>https://doocall.uz</code>,
            для долгосрочного токена она не используется); отметьте право{" "}
            <b>«Доступ к данным аккаунта»</b> и сохраните.
          </p>
        </>
      ),
    },
    {
      step: 2,
      title: "Сгенерируйте долгосрочный токен",
      body: (
        <>
          <p>
            Откройте карточку созданной интеграции → вкладка{" "}
            <b>«Ключи и доступы»</b> → блок <b>«Долгосрочный токен»</b> →
            «Сгенерировать». Выберите максимальный срок (до 5 лет).
          </p>
          <DocsNote kind="warning">
            Токен показывается только ОДИН раз — сразу скопируйте его.
            При повторной генерации старый токен перестаёт действовать во
            всех подключённых сервисах.
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
            В кабинете DooCall: <b>Настройки → Интеграция → amoCRM</b>.
            Заполните:
          </p>
          <DocsList
            items={[
              <>
                <b>Адрес аккаунта</b> —{" "}
                <code>https://&lt;ваш-аккаунт&gt;.amocrm.ru</code> (для
                международной версии — <code>kommo.com</code>);
              </>,
              <>
                <b>Токен доступа</b> — долгосрочный токен из шага 2;
              </>,
              <>
                <b>ID пользователя amoCRM</b> (необязательно) — кому
                назначать звонки и созданные контакты.
              </>,
            ]}
          />
          <p>
            Нажмите <b>«Подключить»</b>, затем{" "}
            <b>«Проверить подключение»</b> — при успехе вернётся название
            вашего аккаунта.
          </p>
        </>
      ),
    },
    {
      title: "Как это работает",
      body: (
        <>
          <DocsList
            items={[
              "Каждый завершённый звонок отправляется в amoCRM (API v4 /calls) с направлением, длительностью и постоянной ссылкой на запись.",
              "Статусы: разговор состоялся, не дозвонился, номер занят — отображаются в карточке звонка amoCRM.",
              "Если номер не найден в amoCRM, DooCall сначала создаёт контакт (имя — из каталога контактов DooCall или сам номер), затем прикрепляет звонок.",
              "Статус доставки виден на странице amoCRM в кабинете DooCall («работает» / текст ошибки).",
            ]}
          />
        </>
      ),
    },
    {
      title: "Возможные проблемы",
      body: (
        <DocsList
          items={[
            <>
              <b>HTTP 401</b> — токен неверен, отозван или истёк:
              сгенерируйте новый и обновите его в DooCall;
            </>,
            <>
              <b>Смена адреса аккаунта</b> — обновите поле «Адрес аккаунта»
              и проверьте подключение заново;
            </>,
            <>
              Звонок не появился — проверьте статус на странице amoCRM в
              DooCall и убедитесь, что интеграция включена.
            </>,
          ]}
        />
      ),
    },
  ],
};

const UZ: Guide = {
  title: "amoCRM / Kommo bilan integratsiya",
  intro:
    "Ulangandan so'ng DooCall mobil ilovasidagi har bir tugagan qo'ng'iroq avtomatik amoCRM'da paydo bo'ladi: telefon raqami bo'yicha kontaktga (bitta faol bitim bo'lsa — bitimga) audio yozuv havolasi bilan biriktiriladi. Notanish raqamlar uchun DooCall kontaktni o'zi yaratadi.",
  apiDocsLabel: "API hujjatlari",
  footer: "© DooCall. Integratsiya bo'yicha savollar: kabinetingizdagi qo'llab-quvvatlash.",
  sections: [
    {
      step: 1,
      title: "amoCRM'da integratsiya yarating",
      body: (
        <>
          <p>
            amoCRM'ga administrator sifatida kirib, integratsiyalar
            bo'limini oching:
          </p>
          <DocsList
            items={[
              <>
                Yangi interfeys: <b>amoМаркет</b> (chap menyu) → o'ng yuqori
                burchakdagi «···» tugmasi → <b>«Создать интеграцию»</b>.
              </>,
              <>
                Yoki to'g'ridan-to'g'ri manzil:{" "}
                <code>
                  https://&lt;akkauntingiz&gt;.amocrm.ru/settings/widgets/
                </code>
              </>,
            ]}
          />
          <p>
            <b>Tashqi (xususiy) integratsiya</b>ni tanlab formani to'ldiring:
            nomi — masalan «DooCall»; redirect havola — istalgan haqiqiy URL
            (masalan <code>https://doocall.uz</code>, uzoq muddatli token
            uchun ishlatilmaydi); <b>«Доступ к данным аккаунта»</b>{" "}
            huquqini belgilab saqlang.
          </p>
        </>
      ),
    },
    {
      step: 2,
      title: "Uzoq muddatli token yarating",
      body: (
        <>
          <p>
            Yaratilgan integratsiya kartochkasini oching →{" "}
            <b>«Ключи и доступы»</b> bo'limi → <b>«Долгосрочный токен»</b> →
            «Сгенерировать». Muddatni maksimal (5 yilgacha) tanlang.
          </p>
          <DocsNote kind="warning">
            Token faqat BIR marta ko'rsatiladi — darhol nusxalab oling.
            Qayta generatsiya qilinsa, eski token barcha ulangan
            xizmatlarda ishlamay qoladi.
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
            DooCall kabinetida: <b>Sozlamalar → Integratsiya → amoCRM</b>.
            To'ldiring:
          </p>
          <DocsList
            items={[
              <>
                <b>Akkaunt manzili</b> —{" "}
                <code>https://&lt;akkauntingiz&gt;.amocrm.ru</code>{" "}
                (xalqaro versiya uchun — <code>kommo.com</code>);
              </>,
              <>
                <b>Kirish tokeni</b> — 2-qadamdagi uzoq muddatli token;
              </>,
              <>
                <b>amoCRM foydalanuvchi ID</b> (ixtiyoriy) — qo'ng'iroqlar
                va yangi kontaktlar kimga biriktirilishi.
              </>,
            ]}
          />
          <p>
            <b>«Ulash»</b>ni, so'ng <b>«Ulanishni tekshirish»</b>ni bosing —
            muvaffaqiyatda akkauntingiz nomi qaytadi.
          </p>
        </>
      ),
    },
    {
      title: "Qanday ishlaydi",
      body: (
        <DocsList
          items={[
            "Har bir tugagan qo'ng'iroq amoCRM'ga yuboriladi (API v4 /calls): yo'nalish, davomiylik va yozuvning doimiy havolasi bilan.",
            "Statuslar: suhbat bo'ldi, javob berilmadi, band — amoCRM qo'ng'iroq kartochkasida ko'rinadi.",
            "Raqam amoCRM'da topilmasa, DooCall avval kontakt yaratadi (ism — DooCall kontaktlar katalogidan yoki raqamning o'zi), keyin qo'ng'iroqni biriktiradi.",
            "Yetkazish holati DooCall kabinetidagi amoCRM sahifasida ko'rinadi («ishlayapti» / xato matni).",
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
              <b>HTTP 401</b> — token noto'g'ri, bekor qilingan yoki muddati
              tugagan: yangisini yaratib DooCall'da yangilang;
            </>,
            <>
              <b>Akkaunt manzili o'zgardi</b> — «Akkaunt manzili» maydonini
              yangilab, ulanishni qayta tekshiring;
            </>,
            <>
              Qo'ng'iroq tushmadi — DooCall'dagi amoCRM sahifasida statusni
              ko'ring va integratsiya yoqilganiga ishonch hosil qiling.
            </>,
          ]}
        />
      ),
    },
  ],
};

const EN: Guide = {
  title: "amoCRM / Kommo integration",
  intro:
    "Once connected, every finished call from the DooCall mobile app appears in amoCRM automatically: attached to the contact by phone number (or to the deal when there is a single active one) with a link to the call recording. For unknown numbers DooCall creates the contact itself.",
  apiDocsLabel: "API docs",
  footer: "© DooCall. Integration questions: support in your cabinet.",
  sections: [
    {
      step: 1,
      title: "Create an integration in amoCRM",
      body: (
        <>
          <p>
            Log into amoCRM as an administrator and open the integrations
            section:
          </p>
          <DocsList
            items={[
              <>
                New interface: <b>amoМаркет</b> (left menu) → the «···»
                button in the top-right corner → <b>“Create integration”</b>.
              </>,
              <>
                Or the direct address:{" "}
                <code>
                  https://&lt;your-account&gt;.amocrm.ru/settings/widgets/
                </code>
              </>,
            ]}
          />
          <p>
            Choose an <b>external (private) integration</b> and fill the
            form: name — e.g. “DooCall”; redirect URL — any valid URL (e.g.{" "}
            <code>https://doocall.uz</code>; it is unused for long-lived
            tokens); tick <b>“Access to account data”</b> and save.
          </p>
        </>
      ),
    },
    {
      step: 2,
      title: "Generate a long-lived token",
      body: (
        <>
          <p>
            Open the integration card → the <b>“Keys and access”</b> tab →{" "}
            <b>“Long-lived token”</b> → Generate. Pick the maximum validity
            (up to 5 years).
          </p>
          <DocsNote kind="warning">
            The token is shown only ONCE — copy it immediately.
            Regenerating invalidates the old token everywhere it is used.
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
            In the DooCall cabinet: <b>Settings → Integration → amoCRM</b>.
            Fill in:
          </p>
          <DocsList
            items={[
              <>
                <b>Account address</b> —{" "}
                <code>https://&lt;your-account&gt;.amocrm.ru</code> (or{" "}
                <code>kommo.com</code> for the international version);
              </>,
              <>
                <b>Access token</b> — the long-lived token from step 2;
              </>,
              <>
                <b>amoCRM user ID</b> (optional) — who calls and created
                contacts get assigned to.
              </>,
            ]}
          />
          <p>
            Press <b>Connect</b>, then <b>Test connection</b> — on success
            your account name is returned.
          </p>
        </>
      ),
    },
    {
      title: "How it works",
      body: (
        <DocsList
          items={[
            "Every finished call is sent to amoCRM (API v4 /calls) with direction, duration and a permanent recording link.",
            "Statuses: conversation completed, no answer, busy — shown on the amoCRM call card.",
            "If the phone is unknown to amoCRM, DooCall first creates the contact (name from the DooCall contact catalog or the number itself), then attaches the call.",
            "Delivery status is visible on the amoCRM page in the DooCall cabinet (“working” / an error text).",
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
              <b>HTTP 401</b> — the token is wrong, revoked or expired:
              generate a new one and update it in DooCall;
            </>,
            <>
              <b>Account address changed</b> — update the “Account address”
              field and re-test the connection;
            </>,
            <>
              A call did not show up — check the status on the amoCRM page
              in DooCall and make sure the integration is enabled.
            </>,
          ]}
        />
      ),
    },
  ],
};

const CONTENT: Record<string, Guide> = { ru: RU, uz: UZ, en: EN };

export default async function AmoCrmGuidePage() {
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
