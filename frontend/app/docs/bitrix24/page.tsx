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
  /** Anchor for deep links (e.g. /docs/bitrix24#click-to-call). */
  id?: string;
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
    {
      id: "click-to-call",
      title: "Звонок в один клик из Bitrix24 (click-to-call)",
      body: (
        <>
          <p>
            Сотрудник нажимает на номер в карточке Bitrix24 — DooCall отправляет
            команду в приложение на телефоне сопоставленного оператора, оператор
            подтверждает, и телефон набирает номер. Итог звонка записывается в
            Bitrix24 как обычно.
          </p>
          <p>Что нужно заранее:</p>
          <DocsList
            items={[
              "Приложение DooCall 1.16.3 или новее на телефоне оператора, в приложении включён «Удалённый звонок» и выданы разрешения на звонки.",
              "Интеграция с Bitrix24 подключена (шаги 1–3 выше).",
              "Операторы DooCall сопоставлены с пользователями Bitrix24 (Настройки → Интеграция → Bitrix24).",
            ]}
          />
        </>
      ),
    },
    {
      title: "Настройка click-to-call",
      body: (
        <>
          <DocsList
            items={[
              <>
                <b>DooCall:</b> Настройки → Интеграция → Bitrix24 → блок{" "}
                <b>«Звонок в один клик»</b>: скопируйте адрес обработчика. Если
                адреса ещё нет — один раз нажмите <b>«Подключить»</b>.
              </>,
              <>
                <b>Bitrix24:</b> Разработчикам → Другое →{" "}
                <b>«Исходящий вебхук»</b>. В поле URL обработчика вставьте
                скопированный адрес, событие — <code>ONEXTERNALCALLSTART</code>.
                Сохраните.
              </>,
              <>
                На странице исходящего вебхука скопируйте{" "}
                <b>«Токен приложения» (application_token)</b>, вставьте его в
                DooCall в поле application_token и нажмите «Подключить».
              </>,
              <>
                Только теперь включите <b>«Звонок в один клик»</b> и снова
                нажмите «Подключить». Без сохранённого application_token опцию
                включить нельзя.
              </>,
              <>
                Проверьте сопоставление операторов с пользователями Bitrix24 —
                по сотруднику, нажавшему на номер, DooCall выбирает телефон
                оператора.
              </>,
              <>
                <b>Bitrix24:</b> Телефония → Настройки → номер по умолчанию для
                исходящих звонков — выберите линию <b>DooCall</b>.
              </>,
            ]}
          />
          <DocsNote>
            В кабинете DooCall видно, сохранён ли application_token и
            зарегистрирована ли линия DooCall в телефонии Bitrix24.
          </DocsNote>
        </>
      ),
    },
    {
      title: "Как работает click-to-call",
      body: (
        <DocsList
          items={[
            "Клик по номеру → Bitrix24 отправляет событие ONEXTERNALCALLSTART (сотрудник и номер) на адрес обработчика DooCall.",
            "DooCall проверяет application_token, находит сопоставленного оператора и его телефон онлайн.",
            "Телефон просит оператора подтвердить звонок (до 30 секунд), затем набирает номер.",
            "После звонка запись загружается с телефона, и звонок регистрируется в Bitrix24, как и остальные звонки.",
          ]}
        />
      ),
    },
    {
      title: "Проблемы с click-to-call",
      body: (
        <DocsList
          items={[
            "По клику ничего не происходит — проверьте, что линия DooCall выбрана по умолчанию для исходящих и в исходящем вебхуке указано событие ONEXTERNALCALLSTART.",
            "Линия DooCall не зарегистрирована — сохраните интеграцию ещё раз и проверьте право «Телефония (telephony)» у входящего вебхука.",
            "application_token не задан или не совпадает — скопируйте токен заново со страницы исходящего вебхука.",
            "Сотрудник Bitrix24 не сопоставлен с оператором — сопоставьте его в DooCall.",
            "Телефон оператора не в сети — откройте приложение DooCall и проверьте интернет.",
            "Оператор не подтвердил звонок за 30 секунд или отклонил его — повторите клик.",
          ]}
        />
      ),
    },
  ],
};

const UZ: Guide = {
  title: "Bitrix24 bilan integratsiya",
  intro:
    "Ulangandan so’ng DooCall mobil ilovasidagi har bir tugagan qo’ng’iroq Bitrix24’da telefon qo’ng’irog’i sifatida avtomatik ro’yxatga olinadi: notanish raqamlar uchun Bitrix24 o’zi lid yaratadi, audio yozuv qo’ng’iroqqa biriktiriladi yoki CRM lentasiga joylanadi.",
  apiDocsLabel: "API hujjatlari",
  footer: "© DooCall. Integratsiya bo’yicha savollar: kabinetingizdagi qo’llab-quvvatlash.",
  sections: [
    {
      step: 1,
      title: "Kiruvchi vebhuk yarating",
      body: (
        <>
          <p>
            Bitrix24’da oching: <b>Разработчикам</b> (chap menyu) →{" "}
            <b>Другое</b> → <b>«Входящий вебхук»</b>. Quyidagi ko’rinishdagi
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
            huquqni qo’shing:
          </p>
          <DocsList
            items={[
              <>
                <b>«Телефония (telephony)»</b> — qo’ng’iroqlarni ro’yxatga
                olish;
              </>,
              <>
                <b>«CRM (crm)»</b> — lid yaratish va yozuv havolasini
                lentaga joylash.
              </>,
            ]}
          />
          <DocsNote kind="warning">
            Adashtirmang: ro’yxatda o’xshash «Телефония (совершение звонков){" "}
            <b>(call)</b>» bandi ham bor — u TO’G’RI KELMAYDI. Qavsida
            aynan «<b>(telephony)</b>» yozilgani kerak. So’ng
            «Сохранить»ni bosing.
          </DocsNote>
          <DocsNote>
            Huquqlar o’zgartirilganda yoki «Перегенерировать» bosilganda
            havola kodi o’zgarishi mumkin — saqlagach URL’ni solishtiring
            va kerak bo’lsa DooCall’da yangilang.
          </DocsNote>
        </>
      ),
    },
    {
      step: 3,
      title: "DooCall’da ulang",
      body: (
        <>
          <p>
            DooCall kabinetida: <b>Sozlamalar → Integratsiya → Bitrix24</b>.
            To’ldiring:
          </p>
          <DocsList
            items={[
              <>
                <b>Kiruvchi vebhuk URL</b> — 1-qadamdagi havola to’liq
                holda;
              </>,
              <>
                <b>Bitrix24 foydalanuvchi ID</b> — qo’ng’iroqlar kim nomidan
                yozilishi (odatda 1 — administrator);
              </>,
              <>
                <b>Akkaunt manzili</b> — ma’lumot uchun, masalan{" "}
                <code>portalingiz.bitrix24.ru</code>.
              </>,
            ]}
          />
          <p>
            <b>«Ulash»</b>ni, so’ng <b>«Ulanishni tekshirish»</b>ni bosing.
          </p>
        </>
      ),
    },
    {
      title: "Qanday ishlaydi",
      body: (
        <DocsList
          items={[
            "Qo’ng’iroq telephony.externalcall.register orqali ro’yxatga olinib, finish bilan yakunlanadi — telefoniya statistikasi va CRM kartochkasiga tushadi.",
            "Notanish raqam → Bitrix24 avtomatik lid yaratadi (CRM_CREATE).",
            "Statuslar: muvaffaqiyatli (200), javob berilmadi (304), band (486), rad etildi (603).",
            "mp3/wav yozuvlar to’g’ridan-to’g’ri qo’ng’iroqqa biriktiriladi; boshqa formatlar (masalan Android’dagi .ogg) doimiy havola sifatida lid/kontakt lentasiga joylanadi.",
            "Ayni qo’ng’iroq 30 daqiqa ichida qayta yuborilsa dublikat hosil bo’lmaydi (EXTERNAL_CALL_ID).",
          ]}
        />
      ),
    },
    {
      title: "Yuzaga kelishi mumkin bo’lgan muammolar",
      body: (
        <DocsList
          items={[
            <>
              <b>insufficient_scope</b> — vebhukda «Телефония (telephony)»
              huquqi yetishmayapti (2-qadamga qarang);
            </>,
            <>
              <b>INVALID_CREDENTIALS</b> — vebhuk havolasi o’zgargan yoki
              o’chirilgan: amaldagi URL’ni nusxalab DooCall’da yangilang;
            </>,
            <>
              Qo’ng’iroq tushmadi — DooCall kabinetidagi Bitrix24
              sahifasida statusni va integratsiya yoqilganini tekshiring.
            </>,
          ]}
        />
      ),
    },
    {
      id: "click-to-call",
      title: "Bitrix24’dan bir bosishda qo’ng’iroq (click-to-call)",
      body: (
        <>
          <p>
            Xodim Bitrix24 kartochkasidagi raqamni bosadi — DooCall moslangan
            operator telefonidagi ilovaga buyruq yuboradi, operator tasdiqlaydi
            va telefon raqamni teradi. Qo’ng’iroq natijasi Bitrix24’ga
            odatdagidek yoziladi.
          </p>
          <p>Oldindan nima kerak:</p>
          <DocsList
            items={[
              "Operator telefonida DooCall ilovasi 1.16.3 yoki yangiroq, ilovada «Masofaviy qo’ng’iroq» yoqilgan va qo’ng’iroq ruxsatlari berilgan.",
              "Bitrix24 integratsiyasi ulangan (yuqoridagi 1–3-qadamlar).",
              "DooCall operatorlari Bitrix24 foydalanuvchilariga moslangan (Sozlamalar → Integratsiya → Bitrix24).",
            ]}
          />
        </>
      ),
    },
    {
      title: "Click-to-call’ni sozlash",
      body: (
        <>
          <DocsList
            items={[
              <>
                <b>DooCall:</b> Sozlamalar → Integratsiya → Bitrix24 →{" "}
                <b>«Bir bosishda qo’ng’iroq»</b> bloki: ishlov beruvchi
                manzilini nusxalang. Manzil hali bo’lmasa — bir marta{" "}
                <b>«Ulash»</b> tugmasini bosing.
              </>,
              <>
                <b>Bitrix24:</b> Dasturchilar uchun → Boshqa →{" "}
                <b>«Chiquvchi vebhuk»</b>. Ishlov beruvchi URL maydoniga
                nusxalangan manzilni qo’ying, hodisa —{" "}
                <code>ONEXTERNALCALLSTART</code>. Saqlang.
              </>,
              <>
                Chiquvchi vebhuk sahifasidan{" "}
                <b>«Ilova tokeni» (application_token)</b>ni nusxalang, uni
                DooCall’dagi application_token maydoniga qo’ying va «Ulash»ni
                bosing.
              </>,
              <>
                Faqat shundan keyin <b>«Bir bosishda qo’ng’iroq»</b>ni yoqing va
                yana «Ulash»ni bosing. Saqlangan application_token’siz uni yoqib
                bo’lmaydi.
              </>,
              <>
                Operatorlar Bitrix24 foydalanuvchilariga moslanganini tekshiring
                — raqamni bosgan xodimga qarab DooCall operator telefonini
                tanlaydi.
              </>,
              <>
                <b>Bitrix24:</b> Telefoniya → Sozlamalar → chiquvchi
                qo’ng’iroqlar uchun standart raqam — <b>DooCall</b> liniyasini
                tanlang.
              </>,
            ]}
          />
          <DocsNote>
            DooCall kabinetida application_token saqlangani va DooCall liniyasi
            Bitrix24 telefoniyasida ro’yxatdan o’tgani ko’rinadi.
          </DocsNote>
        </>
      ),
    },
    {
      title: "Click-to-call qanday ishlaydi",
      body: (
        <DocsList
          items={[
            "Raqam bosiladi → Bitrix24 ONEXTERNALCALLSTART hodisasini (xodim va raqam) DooCall ishlov beruvchi manziliga yuboradi.",
            "DooCall application_token’ni tekshiradi, moslangan operatorni va uning onlayn telefonini topadi.",
            "Telefon operatordan qo’ng’iroqni tasdiqlashni so’raydi (30 soniyagacha), so’ng raqamni teradi.",
            "Qo’ng’iroqdan keyin yozuv telefondan yuklanadi va qo’ng’iroq Bitrix24’da boshqa qo’ng’iroqlar kabi ro’yxatga olinadi.",
          ]}
        />
      ),
    },
    {
      title: "Click-to-call muammolari",
      body: (
        <DocsList
          items={[
            "Bosilganda hech narsa bo’lmaydi — chiquvchi qo’ng’iroqlar uchun DooCall liniyasi standart qilib tanlanganini va chiquvchi vebhukda ONEXTERNALCALLSTART hodisasi ko’rsatilganini tekshiring.",
            "DooCall liniyasi ro’yxatdan o’tmagan — integratsiyani qayta saqlang va kiruvchi vebhukda «Telefoniya (telephony)» huquqi borligini tekshiring.",
            "application_token kiritilmagan yoki mos emas — tokenni chiquvchi vebhuk sahifasidan qayta nusxalang.",
            "Bitrix24 xodimi operatorga moslanmagan — uni DooCall’da moslang.",
            "Operator telefoni onlayn emas — DooCall ilovasini oching va internetni tekshiring.",
            "Operator 30 soniya ichida tasdiqlamadi yoki rad etdi — qayta bosing.",
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
            Don’t confuse it with the similar “Telephony (making calls){" "}
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
    {
      id: "click-to-call",
      title: "Click-to-call from Bitrix24",
      body: (
        <>
          <p>
            An employee clicks a number in a Bitrix24 card — DooCall sends a
            command to the app on the mapped operator’s phone, the operator
            confirms and the phone dials. The call result is recorded in
            Bitrix24 as usual.
          </p>
          <p>Prerequisites:</p>
          <DocsList
            items={[
              "DooCall app 1.16.3 or newer on the operator's phone, with “Remote call” enabled and call permissions granted.",
              "The Bitrix24 integration is connected (steps 1–3 above).",
              "DooCall operators are mapped to Bitrix24 users (Settings → Integration → Bitrix24).",
            ]}
          />
        </>
      ),
    },
    {
      title: "Setting up click-to-call",
      body: (
        <>
          <DocsList
            items={[
              <>
                <b>DooCall:</b> Settings → Integration → Bitrix24 →{" "}
                <b>“Click-to-call”</b> block: copy the handler URL. If there is
                no URL yet, press <b>“Connect”</b> once.
              </>,
              <>
                <b>Bitrix24:</b> Developer resources → Other →{" "}
                <b>“Outgoing webhook”</b>. Paste the copied URL as the handler
                URL and choose the event <code>ONEXTERNALCALLSTART</code>. Save.
              </>,
              <>
                On the outgoing webhook page copy the{" "}
                <b>“Application token” (application_token)</b>, paste it into
                the application_token field in DooCall and press “Connect”.
              </>,
              <>
                Only now turn <b>“Click-to-call”</b> on and press “Connect”
                again. It can’t be enabled without a saved application_token.
              </>,
              <>
                Check that operators are mapped to Bitrix24 users — DooCall
                picks the operator’s phone by the employee who clicked.
              </>,
              <>
                <b>Bitrix24:</b> Telephony → Settings → default number for
                outgoing calls — choose the <b>DooCall</b> line.
              </>,
            ]}
          />
          <DocsNote>
            The DooCall cabinet shows whether the application_token is saved and
            whether the DooCall line is registered in Bitrix24 telephony.
          </DocsNote>
        </>
      ),
    },
    {
      title: "How click-to-call works",
      body: (
        <DocsList
          items={[
            "A number is clicked → Bitrix24 sends the ONEXTERNALCALLSTART event (employee and number) to DooCall's handler URL.",
            "DooCall checks the application_token and finds the mapped operator and their online phone.",
            "The phone asks the operator to confirm (up to 30 seconds), then dials.",
            "After the call the recording is uploaded from the phone and the call is registered in Bitrix24 like any other call.",
          ]}
        />
      ),
    },
    {
      title: "Click-to-call troubleshooting",
      body: (
        <DocsList
          items={[
            "Nothing happens on click — check that the DooCall line is the default for outgoing calls and that the outgoing webhook uses the ONEXTERNALCALLSTART event.",
            "The DooCall line isn't registered — save the integration again and check the inbound webhook has the “Telephony (telephony)” permission.",
            "application_token missing or wrong — copy the token again from the outgoing webhook page.",
            "The Bitrix24 employee isn't mapped to an operator — map them in DooCall.",
            "The operator's phone is offline — open the DooCall app and check the internet connection.",
            "The operator didn't confirm within 30 seconds or declined — click again.",
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
        <div key={section.title} id={section.id} className="scroll-mt-20">
          <DocsSection step={section.step} title={section.title}>
            {section.body}
          </DocsSection>
        </div>
      ))}
    </DocsShell>
  );
}
