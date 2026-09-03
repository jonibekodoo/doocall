/** Public API documentation (moizvonki-style guide) — ru/uz/en via the
 * shared `doocall_locale` cookie + header switcher. */

import { getLocale } from "next-intl/server";
import Link from "next/link";

import { PortalLocaleSwitcher } from "@/components/PortalLocaleSwitcher";

export const metadata = {
  title: "DooCall — API",
  description:
    "DooCall API documentation: authentication, calls list, call recordings, webhooks.",
};

interface ParamRow {
  name: string;
  type: string;
  required?: boolean;
  desc: React.ReactNode;
}

interface ErrorRow {
  http: string;
  code: string;
  reason: string;
}

interface Strings {
  pageTitle: string;
  intro: string;
  toc: Record<string, string>;
  thParam: string;
  thType: string;
  thRequired: string;
  thDesc: string;
  yes: string;
  no: string;
  overviewBody1: string;
  overviewBody2: string;
  authRows: ParamRow[];
  errorsBody: string;
  thHttp: string;
  thCode: string;
  thReason: string;
  errorRows: ErrorRow[];
  callsListRows: ParamRow[];
  callsGetRows: ParamRow[];
  callsGetNote: string;
  recordsBody: string;
  webhooksBody1: string;
  webhooksBody2: string;
  limits: string[];
  footer: string;
  responseComment: string;
}

const RU: Strings = {
  pageTitle: "API для разработчиков",
  intro:
    "API сервиса DooCall позволяет сторонним системам (CRM, BI, собственные приложения) получать звонки, записи разговоров и список сотрудников компании, а также принимать события о новых звонках через webhooks.",
  toc: {
    overview: "Обзор",
    auth: "Аутентификация",
    errors: "Формат ответов и ошибки",
    "calls-list": "calls.list — список звонков",
    "calls-get": "calls.get — один звонок",
    "users-list": "users.list — сотрудники",
    "account-info": "account.info — аккаунт",
    records: "Записи разговоров",
    webhooks: "Webhooks (события)",
    limits: "Ограничения",
  },
  thParam: "Параметр",
  thType: "Тип",
  thRequired: "Обяз.",
  thDesc: "Описание",
  yes: "да",
  no: "нет",
  overviewBody1:
    "Все запросы отправляются методом POST на единый адрес вашего аккаунта:",
  overviewBody2:
    "Тело запроса — JSON (заголовок Content-Type: application/json). Выполняемое действие передаётся в поле action, параметры авторизации — в каждом запросе.",
  authRows: [
    {
      name: "user_name",
      type: "string",
      required: true,
      desc: "E-mail пользователя кабинета DooCall.",
    },
    {
      name: "api_key",
      type: "string",
      required: true,
      desc: "Ключ API компании. Находится в кабинете: Настройки → Интеграция → Параметры API. При смене ключа старый перестаёт действовать.",
    },
    {
      name: "action",
      type: "string",
      required: true,
      desc: (
        <>
          Имя действия, например <code>calls.list</code>.
        </>
      ),
    },
  ],
  errorsBody:
    'Успешный ответ всегда содержит "success": true. Ошибка:',
  thHttp: "HTTP",
  thCode: "error_code",
  thReason: "Причина",
  errorRows: [
    {
      http: "400",
      code: "MISSING_FIELD",
      reason: "Не хватает поля или неизвестный action",
    },
    {
      http: "401",
      code: "INVALID_API_KEY",
      reason: "Неверный api_key / user_name, либо чужой домен аккаунта",
    },
    { http: "429", code: "THROTTLED", reason: "Превышен лимит запросов" },
  ],
  callsListRows: [
    {
      name: "from_date",
      type: "int | ISO-8601",
      desc: "Начало периода (unix-время в секундах или ISO-строка).",
    },
    { name: "to_date", type: "int | ISO-8601", desc: "Конец периода." },
    {
      name: "phone",
      type: "string",
      desc: "Фильтр по номеру клиента (подстрока).",
    },
    {
      name: "call_type",
      type: "string",
      desc: (
        <>
          <code>inbound</code> или <code>outbound</code>.
        </>
      ),
    },
    { name: "offset", type: "int", desc: "Смещение (по умолчанию 0)." },
    {
      name: "limit",
      type: "int",
      desc: "Кол-во записей, максимум 200 (по умолчанию 50).",
    },
  ],
  callsGetRows: [
    {
      name: "server_id",
      type: "string",
      desc: (
        <>
          Серверный идентификатор (<code>srv_…</code>).
        </>
      ),
    },
    {
      name: "call_id",
      type: "string",
      desc: "Либо клиентский идентификатор звонка.",
    },
  ],
  callsGetNote:
    "Нужен один из двух параметров. Ответ — объект call в том же формате, что и в calls.list.",
  recordsBody:
    "Поле record_url — постоянная подписанная ссылка. Её можно сохранять в CRM: при открытии она отдаёт 302-редирект на свежий URL аудиофайла. Ссылка действует, пока запись хранится согласно сроку хранения аудио вашего тарифа.",
  webhooksBody1:
    "Укажите URL приёмника в кабинете (Настройки → Интеграция → Webhook). При каждом новом звонке DooCall отправит POST-запрос:",
  webhooksBody2:
    "Секрет подписи выдаётся один раз при первом сохранении URL. Проверяйте заголовок X-Doocall-Signature — это HMAC-SHA256 от «сырого» тела запроса. Ожидается ответ 2xx; при ошибке доставка повторяется до 3 раз с нарастающей задержкой.",
  limits: [
    "До 120 запросов в минуту на аккаунт (HTTP 429 при превышении).",
    "limit в calls.list — не более 200.",
    "Запросы принимаются только на домене вашего аккаунта (<аккаунт>.doocall.uz).",
  ],
  footer: "© DooCall. Вопросы по интеграции: поддержка в вашем кабинете.",
  responseComment: "// Ответ",
};

const UZ: Strings = {
  pageTitle: "Dasturchilar uchun API",
  intro:
    "DooCall API tashqi tizimlarga (CRM, BI, o'z ilovalaringiz) kompaniya qo'ng'iroqlarini, suhbat yozuvlarini va xodimlar ro'yxatini olish, shuningdek webhooks orqali yangi qo'ng'iroq hodisalarini qabul qilish imkonini beradi.",
  toc: {
    overview: "Umumiy ma'lumot",
    auth: "Autentifikatsiya",
    errors: "Javob formati va xatolar",
    "calls-list": "calls.list — qo'ng'iroqlar ro'yxati",
    "calls-get": "calls.get — bitta qo'ng'iroq",
    "users-list": "users.list — xodimlar",
    "account-info": "account.info — akkaunt",
    records: "Suhbat yozuvlari",
    webhooks: "Webhooks (hodisalar)",
    limits: "Cheklovlar",
  },
  thParam: "Parametr",
  thType: "Turi",
  thRequired: "Majb.",
  thDesc: "Tavsif",
  yes: "ha",
  no: "yo'q",
  overviewBody1:
    "Barcha so'rovlar POST usulida akkauntingizning yagona manziliga yuboriladi:",
  overviewBody2:
    "So'rov tanasi — JSON (Content-Type: application/json sarlavhasi bilan). Bajariladigan amal action maydonida, avtorizatsiya parametrlari esa har bir so'rovda yuboriladi.",
  authRows: [
    {
      name: "user_name",
      type: "string",
      required: true,
      desc: "DooCall kabineti foydalanuvchisining e-mail manzili.",
    },
    {
      name: "api_key",
      type: "string",
      required: true,
      desc: "Kompaniyaning API kaliti. Kabinetda: Sozlamalar → Integratsiya → API parametrlari. Kalit almashtirilgach eskisi ishlamay qoladi.",
    },
    {
      name: "action",
      type: "string",
      required: true,
      desc: (
        <>
          Amal nomi, masalan <code>calls.list</code>.
        </>
      ),
    },
  ],
  errorsBody:
    'Muvaffaqiyatli javobda doim "success": true bo\'ladi. Xato:',
  thHttp: "HTTP",
  thCode: "error_code",
  thReason: "Sababi",
  errorRows: [
    {
      http: "400",
      code: "MISSING_FIELD",
      reason: "Maydon yetishmayapti yoki noma'lum action",
    },
    {
      http: "401",
      code: "INVALID_API_KEY",
      reason: "Noto'g'ri api_key / user_name yoki begona akkaunt domeni",
    },
    { http: "429", code: "THROTTLED", reason: "So'rovlar limiti oshib ketdi" },
  ],
  callsListRows: [
    {
      name: "from_date",
      type: "int | ISO-8601",
      desc: "Davr boshi (unix-vaqt soniyalarda yoki ISO-satr).",
    },
    { name: "to_date", type: "int | ISO-8601", desc: "Davr oxiri." },
    {
      name: "phone",
      type: "string",
      desc: "Mijoz raqami bo'yicha filtr (qism satr).",
    },
    {
      name: "call_type",
      type: "string",
      desc: (
        <>
          <code>inbound</code> yoki <code>outbound</code>.
        </>
      ),
    },
    { name: "offset", type: "int", desc: "Siljish (odatda 0)." },
    {
      name: "limit",
      type: "int",
      desc: "Yozuvlar soni, ko'pi bilan 200 (odatda 50).",
    },
  ],
  callsGetRows: [
    {
      name: "server_id",
      type: "string",
      desc: (
        <>
          Server identifikatori (<code>srv_…</code>).
        </>
      ),
    },
    {
      name: "call_id",
      type: "string",
      desc: "Yoki qo'ng'iroqning mijoz identifikatori.",
    },
  ],
  callsGetNote:
    "Ikkala parametrdan bittasi kifoya. Javob — calls.list bilan bir xil formatdagi call obyekti.",
  recordsBody:
    "record_url maydoni — doimiy imzolangan havola. Uni CRM'da saqlash mumkin: ochilganda yangi audio fayl URL'iga 302-redirekt qaytaradi. Havola audio saqlash muddati davomida amal qiladi.",
  webhooksBody1:
    "Qabul qiluvchi URL'ni kabinetda ko'rsating (Sozlamalar → Integratsiya → Webhook). Har bir yangi qo'ng'iroqda DooCall POST so'rov yuboradi:",
  webhooksBody2:
    "Imzo siri URL birinchi marta saqlanganda bir marta beriladi. X-Doocall-Signature sarlavhasini tekshiring — bu so'rovning «xom» tanasidan olingan HMAC-SHA256. 2xx javob kutiladi; xatoda yetkazish ortib boruvchi kechikish bilan 3 martagacha takrorlanadi.",
  limits: [
    "Akkaunt uchun daqiqasiga 120 tagacha so'rov (oshsa HTTP 429).",
    "calls.list dagi limit — ko'pi bilan 200.",
    "So'rovlar faqat akkauntingiz domenida qabul qilinadi (<akkaunt>.doocall.uz).",
  ],
  footer:
    "© DooCall. Integratsiya bo'yicha savollar: kabinetingizdagi qo'llab-quvvatlash.",
  responseComment: "// Javob",
};

const EN: Strings = {
  pageTitle: "API for developers",
  intro:
    "The DooCall API lets third-party systems (CRMs, BI, your own apps) fetch the company's calls, call recordings and staff list, and receive new-call events via webhooks.",
  toc: {
    overview: "Overview",
    auth: "Authentication",
    errors: "Response format & errors",
    "calls-list": "calls.list — calls",
    "calls-get": "calls.get — single call",
    "users-list": "users.list — staff",
    "account-info": "account.info — account",
    records: "Call recordings",
    webhooks: "Webhooks (events)",
    limits: "Limits",
  },
  thParam: "Parameter",
  thType: "Type",
  thRequired: "Req.",
  thDesc: "Description",
  yes: "yes",
  no: "no",
  overviewBody1:
    "All requests are sent with POST to your account's single endpoint:",
  overviewBody2:
    "The request body is JSON (Content-Type: application/json). The action to perform goes in the action field; auth parameters ride in every request.",
  authRows: [
    {
      name: "user_name",
      type: "string",
      required: true,
      desc: "E-mail of a DooCall cabinet user.",
    },
    {
      name: "api_key",
      type: "string",
      required: true,
      desc: "The company API key. Found in the cabinet: Settings → Integration → API parameters. After rotation the old key stops working.",
    },
    {
      name: "action",
      type: "string",
      required: true,
      desc: (
        <>
          Action name, e.g. <code>calls.list</code>.
        </>
      ),
    },
  ],
  errorsBody:
    'A successful response always contains "success": true. An error:',
  thHttp: "HTTP",
  thCode: "error_code",
  thReason: "Reason",
  errorRows: [
    {
      http: "400",
      code: "MISSING_FIELD",
      reason: "A field is missing or the action is unknown",
    },
    {
      http: "401",
      code: "INVALID_API_KEY",
      reason: "Wrong api_key / user_name, or a foreign account domain",
    },
    { http: "429", code: "THROTTLED", reason: "Rate limit exceeded" },
  ],
  callsListRows: [
    {
      name: "from_date",
      type: "int | ISO-8601",
      desc: "Period start (unix seconds or an ISO string).",
    },
    { name: "to_date", type: "int | ISO-8601", desc: "Period end." },
    {
      name: "phone",
      type: "string",
      desc: "Filter by client number (substring).",
    },
    {
      name: "call_type",
      type: "string",
      desc: (
        <>
          <code>inbound</code> or <code>outbound</code>.
        </>
      ),
    },
    { name: "offset", type: "int", desc: "Offset (default 0)." },
    {
      name: "limit",
      type: "int",
      desc: "Number of rows, max 200 (default 50).",
    },
  ],
  callsGetRows: [
    {
      name: "server_id",
      type: "string",
      desc: (
        <>
          Server identifier (<code>srv_…</code>).
        </>
      ),
    },
    { name: "call_id", type: "string", desc: "Or the client-side call id." },
  ],
  callsGetNote:
    "One of the two parameters is required. The response is a call object in the same format as calls.list.",
  recordsBody:
    "The record_url field is a permanent signed link. It is safe to store in a CRM: opening it returns a 302 redirect to a fresh audio URL. The link works for as long as the recording is kept under your plan's audio retention.",
  webhooksBody1:
    "Set the receiver URL in the cabinet (Settings → Integration → Webhook). On every new call DooCall sends a POST request:",
  webhooksBody2:
    "The signing secret is shown once when the URL is first saved. Verify the X-Doocall-Signature header — an HMAC-SHA256 of the raw request body. A 2xx response is expected; on failure delivery retries up to 3 times with backoff.",
  limits: [
    "Up to 120 requests per minute per account (HTTP 429 above that).",
    "limit in calls.list — at most 200.",
    "Requests are accepted only on your account domain (<account>.doocall.uz).",
  ],
  footer: "© DooCall. Integration questions: support in your cabinet.",
  responseComment: "// Response",
};

const CONTENT: Record<string, Strings> = { ru: RU, uz: UZ, en: EN };

function Code({ children }: { children: string }) {
  return (
    <pre className="my-3 overflow-x-auto rounded-lg bg-[#14181a] p-4 text-xs leading-relaxed text-[#d7e0e4]">
      <code>{children}</code>
    </pre>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20 border-t border-border pt-8">
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function ParamTable({ l, rows }: { l: Strings; rows: ParamRow[] }) {
  return (
    <div className="my-3 overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[560px] text-left">
        <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
          <tr>
            <th className="px-3 py-2">{l.thParam}</th>
            <th className="px-3 py-2">{l.thType}</th>
            <th className="px-3 py-2">{l.thRequired}</th>
            <th className="px-3 py-2">{l.thDesc}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className="border-t border-border">
              <td className="px-3 py-2 font-mono text-xs">{row.name}</td>
              <td className="px-3 py-2 text-xs text-fg-muted">{row.type}</td>
              <td className="px-3 py-2 text-xs">{row.required ? l.yes : l.no}</td>
              <td className="px-3 py-2 text-sm">{row.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function ApiDocsPage() {
  const locale = await getLocale();
  const l = CONTENT[locale] ?? RU;
  const tocIds = Object.keys(l.toc);

  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-4">
          <p className="font-[family-name:var(--font-display)] text-xl font-semibold">
            dooCall <span className="text-fg-muted">· API</span>
          </p>
          <div className="flex items-center gap-4">
            <PortalLocaleSwitcher />
            <Link href="/" className="text-sm text-accent hover:underline">
              doocall.uz
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-8 px-4 py-8">
        <div>
          <h1 className="text-2xl font-bold">{l.pageTitle}</h1>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">{l.intro}</p>
          <ul className="mt-4 grid gap-1 text-sm sm:grid-cols-2">
            {tocIds.map((anchor) => (
              <li key={anchor}>
                <a href={`#${anchor}`} className="text-accent hover:underline">
                  {l.toc[anchor]}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <Section id="overview" title={l.toc.overview}>
          <p className="text-sm leading-relaxed">{l.overviewBody1}</p>
          <Code>{`https://<account>.doocall.uz/api/v1`}</Code>
          <p className="text-sm leading-relaxed">{l.overviewBody2}</p>
        </Section>

        <Section id="auth" title={l.toc.auth}>
          <ParamTable l={l} rows={l.authRows} />
          <Code>{`POST https://mycompany.doocall.uz/api/v1
Content-Type: application/json

{
  "user_name": "admin@mycompany.uz",
  "api_key": "1f3c9a4b8d2e4f6a9c1b3d5e7f9a0b2c",
  "action": "calls.list",
  "limit": 20
}`}</Code>
        </Section>

        <Section id="errors" title={l.toc.errors}>
          <p className="text-sm leading-relaxed">{l.errorsBody}</p>
          <Code>{`{
  "success": false,
  "message": "invalid api_key",
  "error_code": "INVALID_API_KEY"
}`}</Code>
          <div className="my-3 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-left text-sm">
              <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
                <tr>
                  <th className="px-3 py-2">{l.thHttp}</th>
                  <th className="px-3 py-2">{l.thCode}</th>
                  <th className="px-3 py-2">{l.thReason}</th>
                </tr>
              </thead>
              <tbody>
                {l.errorRows.map((row) => (
                  <tr key={row.code} className="border-t border-border">
                    <td className="px-3 py-2">{row.http}</td>
                    <td className="px-3 py-2 font-mono text-xs">{row.code}</td>
                    <td className="px-3 py-2">{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section id="calls-list" title={l.toc["calls-list"]}>
          <ParamTable l={l} rows={l.callsListRows} />
          <Code>{`${l.responseComment}
{
  "success": true,
  "total": 1342,
  "offset": 0,
  "limit": 20,
  "calls": [
    {
      "server_id": "srv_9f1c2b3a4d5e6f708192a3b4c5d6e7f8",
      "call_id": "1724495961-998901234567",
      "call_type": "inbound",
      "call_status": "answered",
      "from": "+998901234567",
      "to": "+998712005050",
      "counterparty_number": "+998901234567",
      "counterparty_name": "Aziz Karimov",
      "operator": "operator1",
      "operator_number": "+998712005050",
      "duration": 214,
      "start_time": "2026-09-01T12:39:21+00:00",
      "received_at": "2026-09-01T12:43:02+00:00",
      "record_url": "https://mycompany.doocall.uz/api/public/rec/9f1c…?sig=…"
    }
  ]
}`}</Code>
        </Section>

        <Section id="calls-get" title={l.toc["calls-get"]}>
          <ParamTable l={l} rows={l.callsGetRows} />
          <p className="text-sm text-fg-muted">{l.callsGetNote}</p>
        </Section>

        <Section id="users-list" title={l.toc["users-list"]}>
          <Code>{`{
  "success": true,
  "users": [
    { "user_name": "operator1", "full_name": "Alisher N.", "is_active": true,
      "phones": ["+998712005050"] }
  ]
}`}</Code>
        </Section>

        <Section id="account-info" title={l.toc["account-info"]}>
          <Code>{`{
  "success": true,
  "account": { "name": "My Company", "slug": "mycompany",
               "status": "active", "operators": 12 }
}`}</Code>
        </Section>

        <Section id="records" title={l.toc.records}>
          <p className="text-sm leading-relaxed">{l.recordsBody}</p>
        </Section>

        <Section id="webhooks" title={l.toc.webhooks}>
          <p className="text-sm leading-relaxed">{l.webhooksBody1}</p>
          <Code>{`POST <your URL>
Content-Type: application/json
X-Doocall-Signature: hmac_sha256(secret, raw_body)   // hex

{
  "event": "call.received",
  "call_id": "1724495961-998901234567",
  "server_id": "srv_9f1c2b3a4d5e6f708192a3b4c5d6e7f8",
  "call_type": "inbound",
  "call_status": "answered",
  "from": "+998901234567",
  "to": "+998712005050",
  "counterparty_number": "+998901234567",
  "counterparty_name": "Aziz Karimov",
  "duration": 214,
  "start_time": "2026-09-01T12:39:21+00:00",
  "received_at": "2026-09-01T12:43:02+00:00"
}`}</Code>
          <p className="text-sm leading-relaxed">{l.webhooksBody2}</p>
        </Section>

        <Section id="limits" title={l.toc.limits}>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {l.limits.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Section>

        <footer className="border-t border-border pt-6 text-xs text-fg-faint">
          {l.footer}
        </footer>
      </main>
    </div>
  );
}
