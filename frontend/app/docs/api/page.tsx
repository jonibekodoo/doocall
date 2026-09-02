/** Public API documentation (moizvonki-style guide, Russian). */

export const metadata = {
  title: "DooCall — API для разработчиков",
  description:
    "Документация по API сервиса DooCall: авторизация, список звонков, записи разговоров, webhooks.",
};

function Param({
  name,
  type,
  required,
  children,
}: {
  name: string;
  type: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <tr className="border-t border-border">
      <td className="px-3 py-2 font-mono text-xs">{name}</td>
      <td className="px-3 py-2 text-xs text-fg-muted">{type}</td>
      <td className="px-3 py-2 text-xs">{required ? "да" : "нет"}</td>
      <td className="px-3 py-2 text-sm">{children}</td>
    </tr>
  );
}

function ParamTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-3 overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[560px] text-left">
        <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
          <tr>
            <th className="px-3 py-2">Параметр</th>
            <th className="px-3 py-2">Тип</th>
            <th className="px-3 py-2">Обяз.</th>
            <th className="px-3 py-2">Описание</th>
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

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

const TOC = [
  ["overview", "Обзор"],
  ["auth", "Аутентификация"],
  ["errors", "Формат ответов и ошибки"],
  ["calls-list", "calls.list — список звонков"],
  ["calls-get", "calls.get — один звонок"],
  ["users-list", "users.list — сотрудники"],
  ["account-info", "account.info — аккаунт"],
  ["records", "Записи разговоров"],
  ["webhooks", "Webhooks (события)"],
  ["limits", "Ограничения"],
] as const;

export default function ApiDocsPage() {
  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <p className="font-[family-name:var(--font-display)] text-xl font-semibold">
            dooCall <span className="text-fg-muted">· API</span>
          </p>
          <a href="/" className="text-sm text-accent hover:underline">
            doocall.uz
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-8 px-4 py-8">
        <div>
          <h1 className="text-2xl font-bold">API для разработчиков</h1>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">
            API сервиса DooCall позволяет сторонним системам (CRM, BI,
            собственные приложения) получать звонки, записи разговоров и
            список сотрудников компании, а также принимать события о новых
            звонках через webhooks.
          </p>
          <ul className="mt-4 grid gap-1 text-sm sm:grid-cols-2">
            {TOC.map(([anchor, label]) => (
              <li key={anchor}>
                <a href={`#${anchor}`} className="text-accent hover:underline">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <Section id="overview" title="Обзор">
          <p className="text-sm leading-relaxed">
            Все запросы отправляются методом <b>POST</b> на единый адрес
            вашего аккаунта:
          </p>
          <Code>{`https://<ваш-аккаунт>.doocall.uz/api/v1`}</Code>
          <p className="text-sm leading-relaxed">
            Тело запроса — JSON (заголовок{" "}
            <code className="rounded bg-surface-2 px-1">
              Content-Type: application/json
            </code>
            ). Выполняемое действие передаётся в поле{" "}
            <code className="rounded bg-surface-2 px-1">action</code>,
            параметры авторизации — в каждом запросе.
          </p>
        </Section>

        <Section id="auth" title="Аутентификация">
          <ParamTable>
            <Param name="user_name" type="string" required>
              E-mail пользователя кабинета DooCall.
            </Param>
            <Param name="api_key" type="string" required>
              Ключ API компании. Находится в кабинете: Настройки → Интеграция
              → Параметры API. При смене ключа старый перестаёт действовать.
            </Param>
            <Param name="action" type="string" required>
              Имя действия, например <code>calls.list</code>.
            </Param>
          </ParamTable>
          <Code>{`POST https://mycompany.doocall.uz/api/v1
Content-Type: application/json

{
  "user_name": "admin@mycompany.uz",
  "api_key": "1f3c9a4b8d2e4f6a9c1b3d5e7f9a0b2c",
  "action": "calls.list",
  "limit": 20
}`}</Code>
        </Section>

        <Section id="errors" title="Формат ответов и ошибки">
          <p className="text-sm leading-relaxed">
            Успешный ответ всегда содержит{" "}
            <code className="rounded bg-surface-2 px-1">
              &quot;success&quot;: true
            </code>
            . Ошибка:
          </p>
          <Code>{`{
  "success": false,
  "message": "invalid api_key",
  "error_code": "INVALID_API_KEY"
}`}</Code>
          <div className="my-3 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-left text-sm">
              <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
                <tr>
                  <th className="px-3 py-2">HTTP</th>
                  <th className="px-3 py-2">error_code</th>
                  <th className="px-3 py-2">Причина</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-border">
                  <td className="px-3 py-2">400</td>
                  <td className="px-3 py-2 font-mono text-xs">MISSING_FIELD</td>
                  <td className="px-3 py-2">
                    Не хватает поля или неизвестный action
                  </td>
                </tr>
                <tr className="border-t border-border">
                  <td className="px-3 py-2">401</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    INVALID_API_KEY
                  </td>
                  <td className="px-3 py-2">
                    Неверный api_key / user_name, либо чужой домен аккаунта
                  </td>
                </tr>
                <tr className="border-t border-border">
                  <td className="px-3 py-2">429</td>
                  <td className="px-3 py-2 font-mono text-xs">THROTTLED</td>
                  <td className="px-3 py-2">Превышен лимит запросов</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Section>

        <Section id="calls-list" title="calls.list — список звонков">
          <ParamTable>
            <Param name="from_date" type="int | ISO-8601">
              Начало периода (unix-время в секундах или ISO-строка).
            </Param>
            <Param name="to_date" type="int | ISO-8601">
              Конец периода.
            </Param>
            <Param name="phone" type="string">
              Фильтр по номеру клиента (подстрока).
            </Param>
            <Param name="call_type" type="string">
              <code>inbound</code> или <code>outbound</code>.
            </Param>
            <Param name="offset" type="int">
              Смещение (по умолчанию 0).
            </Param>
            <Param name="limit" type="int">
              Кол-во записей, максимум 200 (по умолчанию 50).
            </Param>
          </ParamTable>
          <Code>{`// Ответ
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

        <Section id="calls-get" title="calls.get — один звонок">
          <ParamTable>
            <Param name="server_id" type="string">
              Серверный идентификатор (<code>srv_…</code>).
            </Param>
            <Param name="call_id" type="string">
              Либо клиентский идентификатор звонка.
            </Param>
          </ParamTable>
          <p className="text-sm text-fg-muted">
            Нужен один из двух параметров. Ответ — объект{" "}
            <code className="rounded bg-surface-2 px-1">call</code> в том же
            формате, что и в <code>calls.list</code>.
          </p>
        </Section>

        <Section id="users-list" title="users.list — сотрудники">
          <Code>{`{
  "success": true,
  "users": [
    { "user_name": "operator1", "full_name": "Alisher N.", "is_active": true,
      "phones": ["+998712005050"] }
  ]
}`}</Code>
        </Section>

        <Section id="account-info" title="account.info — аккаунт">
          <Code>{`{
  "success": true,
  "account": { "name": "My Company", "slug": "mycompany",
               "status": "active", "operators": 12 }
}`}</Code>
        </Section>

        <Section id="records" title="Записи разговоров">
          <p className="text-sm leading-relaxed">
            Поле <code className="rounded bg-surface-2 px-1">record_url</code>{" "}
            — постоянная подписанная ссылка. Её можно сохранять в CRM: при
            открытии она отдаёт 302-редирект на свежий URL аудиофайла.
            Ссылка действует, пока запись хранится согласно сроку хранения
            аудио вашего тарифа.
          </p>
        </Section>

        <Section id="webhooks" title="Webhooks (события)">
          <p className="text-sm leading-relaxed">
            Укажите URL приёмника в кабинете (Настройки → Интеграция →
            Webhook). При каждом новом звонке DooCall отправит POST-запрос:
          </p>
          <Code>{`POST <ваш URL>
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
          <p className="text-sm leading-relaxed">
            Секрет подписи выдаётся один раз при первом сохранении URL.
            Проверяйте заголовок{" "}
            <code className="rounded bg-surface-2 px-1">
              X-Doocall-Signature
            </code>{" "}
            — это HMAC-SHA256 от «сырого» тела запроса. Ожидается ответ 2xx;
            при ошибке доставка повторяется до 3 раз с нарастающей задержкой.
          </p>
        </Section>

        <Section id="limits" title="Ограничения">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>До 120 запросов в минуту на аккаунт (HTTP 429 при превышении).</li>
            <li>
              <code className="rounded bg-surface-2 px-1">limit</code> в{" "}
              <code className="rounded bg-surface-2 px-1">calls.list</code> —
              не более 200.
            </li>
            <li>
              Запросы принимаются только на домене вашего аккаунта{" "}
              (<code className="rounded bg-surface-2 px-1">
                &lt;аккаунт&gt;.doocall.uz
              </code>
              ).
            </li>
          </ul>
        </Section>

        <footer className="border-t border-border pt-6 text-xs text-fg-faint">
          © DooCall. Вопросы по интеграции: поддержка в вашем кабинете.
        </footer>
      </main>
    </div>
  );
}
