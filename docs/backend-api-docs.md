# dooCall (CallCloud) — Backend API spetsifikatsiyasi (to'liq, SaaS darajasi)

> Manba: ilovaning HOZIRGI kodi (2026-08-09 holatiga, `uz.hakimbek.doocall`).
> Har bir maydon/qaror tagida qaysi fayldan kelib chiqqani ko'rsatilgan —
> hech narsa "o'zidan" o'ylab topilmagan.
>
> Bu hujjat call-recording SaaS backend uchun **to'liq CDR (Call Detail
> Record) kontrakti**: kirish (login — ilova FAQAT shuni qiladi, alohida
> ro'yxatdan o'tish ekrani yo'q), qo'ng'iroq + audio + joylashuv + kontakt
> ismi yuklash, dedup/ro'yxat, statistika sinxronizatsiyasi, diagnostika
> logi — barchasi BITTA izchil konventsiya ustiga qurilgan (§1).

---

## 0. Ikkita tuzatish — nega qayta ishlandi

### 0.1 `from`/`to` — to'liq raqam, login-ism EMAS

Avvalgi qoralamada operator tomoni uchun raqam o'rniga login-ism
(`user_name`, masalan `"operator1"`) qo'yilgan edi (`RecordUploader.kt:77-81`).
Bu CDR uchun yetarli emas. Hal qilindi: operatorning HAQIQIY raqami
(`operator_number`) endi login-nomdan ALOHIDA maydon, Login so'rovida
(§4) qayd etiladi va har bir yozuvda `from`/`to`ga to'liq E.164 shaklda
qo'yiladi (§5.2). Android o'z SIM raqamini ishonchli avtomatik ololmagani
uchun (faqat `READ_PHONE_STATE` bor — `SimSlotResolver.kt:97-99` faqat SIM
**slot indeksini** biladi, raqamni EMAS) bu raqam qo'lda kiritiladi —
xuddi boshqa call-recording SaaS'lar (CloudTalk, amoCRM telefoniya
integratsiyasi) qiladigani kabi.

### 0.2 `from`/`to` — raqam bilan BIRGA kontakt ismi ham

Ekranda (`CallListAdapter.kt:98-99`, `:335-350`, `:392-406`) har bir
qo'ng'iroq qatorida raqam o'rniga, topilsa, **kontakt ismi** ko'rsatiladi —
`ContactResolver.kt` orqali qurilmaning o'z telefon kitobidan
(`ContactsContract.PhoneLookup`) qidiriladi. Bu ma'lumot hozircha FAQAT
ekranda ko'rsatiladi, serverga umuman yuborilmaydi. Bu ham to'g'ri emas:
suhbatlashilgan odam ismi (telefon kitobida saqlangan bo'lsa) yoki admin
panelning o'z kontakt bazasida (agar backend shunday katalog yuritsa)
qayd etilgan ism — ikkalasi ham CDR yozuvida bo'lishi kerak. Hal qilindi:
`counterparty_name`/`from_name`/`to_name` maydonlari qo'shildi (§5.2) —
qurilma o'zi bilgan ismni yuboradi, backend esa (agar o'z kontakt
katalogi bo'lsa) buni ustidan yozib, javobda (§5.4) yaxshiroq nomni
qaytarishi mumkin.

---

## 1. Umumiy konventsiya (BARCHA endpointlar uchun)

| | |
|---|---|
| Base URL | `{server_url}` — Login paytida foydalanuvchi kiritadi, `CustomFunctions.getServerUrl()`. Har doim `/` bilan tugatiladi (`ApiClient.kt:22-24`, `RecordUploader.kt:166`). |
| Prefiks | `api/call/v1/` — mavjud kodda ikkala endpoint ham shu prefiks bilan (`/api/call/v1/auth`, `/api/call/v1/upload`). Yangi endpointlar ham shunda davom etadi. |
| Metod | **Faqat POST.** Loyihada GET hech qayerda ishlatilmagan — barcha o'qish so'rovlari (ro'yxat, statistika) ham POST + JSON body orqali. |
| Content-Type | `application/json` har doim. |
| Autentifikatsiya | HTTP header EMAS — **`api_key` har doim JSON body ichida**, `user_name` bilan birga (`RecordUploader.kt:84-97`). |
| Vaqt formati | `"yyyy-MM-dd HH:mm:ss"` — qurilma **lokal** vaqt zonasida (UTC emas) — `RecordUploader.kt:83`. |
| Raqam formati | E.164'ga yaqin: `+` bilan boshlansa o'zgarmaydi; 9 xonali bo'lsa boshiga `+998`; 12 xonali bo'lsa boshiga `+` (`RecordUploader.formatPhone()`, `:133-141`). **`from`/`to`/`operator_number`/`counterparty_number` — ISTISNOSIZ shu formatdagi to'liq raqam.** |
| Dedup kaliti | `call_id` — `CallRecordEntity.callId`. Server UNIQUE cheklov qo'yishi shart. |
| Javob konverti | Har bir endpoint kamida `"success": boolean` qaytaradi (`LoginResponse` naqshiga mos). Xatolik — `"message"` + `"error_code"` (§9). |

---

## 2. Ma'lumotlar modeli — `CallRecordEntity`

Room jadvali: `call_records` (`callId` UNIQUE index), `data/CallRecordEntity.kt`.

| Maydon | Tip | Izoh |
|---|---|---|
| `id` | `Long` | Faqat local DB PK. Serverga yuborilmaydi. |
| `callId` | `String` | Barqaror unikal ID — server **dedup kaliti**. |
| `phoneNumber` | `String` | Qarama-qarshi tomon raqami (xom). `formatPhone()` orqali normalizatsiya. |
| `callType` | `String` | `"inbound"` \| `"outbound"` (`"internal"` rejalashtirilgan). |
| `callStatus` | `String` | `"answered"` \| `"no_answer"` (`"busy"`, `"failed"` rejalashtirilgan). |
| `duration` | `Long` | Soniyalarda. |
| `startTime` / `endTime` | `Long` | Unix epoch millisekund. |
| `filePath` | `String` | Telefon xotirasidagi audio — local yo'l, serverga yuborilmaydi. |
| `synced` | `Boolean` | Local UI holati — serverdan o'qilmaydi. |
| `uploadCount` | `Int` | Muvaffaqiyatsiz urinishlar soni. |
| `realtimeFilePath` | `String` | Mikrofon orqali IKKINCHI audio manba. |
| `simSlot` | `Int` | Jismoniy SIM slot (`0`/`1`, `-1`=aniqlanmadi). Operator raqami/ismi shu orqali bog'lanadi (§3). |
| `latitude` / `longitude` | `Double?` | Qo'ng'iroq vaqtidagi joylashuv. |
| `address` | `String` | "Copy location" bosilganda keshlangan manzil. |

**Ekranda ko'rinib, entity'da yo'q (client-side hisoblanadi, API'ga
qo'shilishi shart emas):** yo'nalish ikonkasi/rangi va "declined" belgisi
(`CallStatusVisuals.kt` — to'liq `callType`+`callStatus`dan hisoblanadi),
avatar harfi (ismning birinchi harfi), sana sarlavhasi guruhlash
(`startTime`dan). Bularning barchasi backend uchun ortiqcha — mavjud
maydonlardan client o'zi chiqaradi.

---

## 3. Operator identifikatsiyasi va SIM → raqam/ism bog'lanishi

Uchta tushuncha bor, ular ALOHIDA maydonlarda yuriladi:

| Tushuncha | Nima | Qayerdan keladi |
|---|---|---|
| **Login identifikatori** (`user_name`) | Hisob egasi kim (autentifikatsiya) — TELEFON RAQAMI emas. | `CustomFunctions.getUserName()`. |
| **Operator raqami** (`operator_number`) | Hisobga tegishli HAQIQIY telefon raqami — `from`/`to`da ishlatiladi. | Login paytida qo'lda kiritiladi (§0.1, §4). |
| **Qarshi tomon ismi** (`counterparty_name`) | Suhbatlashilgan odamning ismi, topilsa. | Qurilma telefon kitobi (`ContactResolver`) va/yoki backendning o'z kontakt katalogi (§0.2, §5.4). |

Ikki-SIM qurilmalar uchun operator SIM slot bo'yicha ikkita raqamga ega
bo'lishi mumkin — `CallRecordEntity.simSlot` allaqachon har bir yozuvda
qaysi slot ekanini biladi:

```jsonc
"phone_numbers": [
  { "sim_slot": 0, "number": "+998901234567" },
  { "sim_slot": 1, "number": "+998931234567" }
]
```

Yuklash vaqtida `record.simSlot` shu ro'yxatdagi mos raqamga bog'lanib
`operator_number`ni to'ldiradi. `simSlot == -1` yoki raqam hali
kiritilmagan bo'lsa — ro'yxatdagi yagona/birinchi raqam fallback sifatida
ishlatiladi; u ham bo'lmasa `operator_number: null` + `"operator_number_missing": true`
bayrog'i qo'yiladi — lekin bu holatda ham `from`/`to` login-ism bilan
TO'LDIRILMAYDI (§0.1'dagi eski xato takrorlanmasin uchun).

**Ilova tomonida qo'shilishi kerak bo'lgan qism** (hozircha kodda yo'q):
- Sozlamalarga "Mening raqamlarim" — har bir faol SIM slot uchun bitta
  matn maydoni (mavjud "SIM offset" qatoriga o'xshash UI).
- `CustomFunctions.java`ga `saveOperatorNumber(context, simSlot, number)` /
  `getOperatorNumber(context, simSlot)` — mavjud `saveServerUrl`/
  `getServerUrl` naqshiga mos (`"AppPrefs"`, kalit `"operator_number_sim" + simSlot`).
- `RecordUploader.kt:77-81`dagi `myNumber` — `username` o'rniga
  `CustomFunctions.getOperatorNumber(context, record.simSlot)`dan olinadi.

---

## 4. Kirish (Login) — ilova FAQAT shuni qiladi

Ilovada alohida "ro'yxatdan o'tish" ekrani/oqimi **yo'q va bo'lmaydi** —
faqat bitta autentifikatsiya chaqiruvi bor (`networking/ApiService.kt`).
Shu sabab barcha "onboarding" ma'lumoti (operator raqamlari, qurilma
ma'lumoti) — xuddi messenger ilovalari ulanishda qiladigani kabi — **shu
bitta Login so'rovining o'zi bilan** yuboriladi, alohida `/register`
qadam kerak emas. Backend buni har safar **upsert** sifatida qabul qiladi
(hisob mavjud bo'lsa — yangilaydi; mavjud bo'lmasa — talabga qarab
yaratadi yoki xato qaytaradi, biznes qoidasiga bog'liq).

```
POST {server_url}api/call/v1/auth
Content-Type: application/json
```

```jsonc
// Request — HOZIRGI (kodda bor, LoginRequest) ────────────────────────────
{
  "username": "operator1",
  "password": "••••••••",
  "server":   "https://acme.example.com"
}
```

```jsonc
// Request — TO'LIQ (SaaS uchun tavsiya, bitta chaqiruvda hammasi) ────────
{
  "username": "operator1",
  "password": "••••••••",
  "server":   "https://acme.example.com",

  // §3 — operator raqamlari, SIM slot bo'yicha (kiritilmagan bo'lsa bo'sh array)
  "phone_numbers": [
    { "sim_slot": 0, "number": "+998901234567" },
    { "sim_slot": 1, "number": "+998931234567" }
  ],

  // Profil (ixtiyoriy) — ProfileFragment header uchun
  "full_name": "Jonibek Yorqulov",

  // Qurilma ma'lumoti — messenger ilovalari ulanishda yuboradigan
  // standart to'plam (hozircha kodda YO'Q, YANGI, standart Android API'lari
  // bilan olinadi: Build.MODEL/MANUFACTURER — loyihada allaqachon boshqa
  // maqsadlar uchun ishlatiladi, masalan RecorderHelper.java:87,
  // CallReceiver.kt:539 — shu bilan bir xil manba)
  "device": {
    "device_id":       "a1b2c3d4e5f6...",   // Settings.Secure.ANDROID_ID — qurilmani ID'lash uchun (hozircha kodda ishlatilmaydi, YANGI)
    "model":            "Redmi Note 12",     // Build.MODEL
    "manufacturer":     "Xiaomi",            // Build.MANUFACTURER
    "app_version":      "1.0",               // build.gradle versionName
    "os_version":       "13"                 // Build.VERSION.RELEASE
  }
}
```

```jsonc
// Response — 200 OK
{
  "success": true,
  "api_key": "b7e2f1c9-...."     // doimiy token, keyingi HAR BIR so'rovda yuboriladi
}

// Response — 401
{
  "success": false,
  "api_key": ""
}
```

`api_key` — `CustomFunctions.saveToken()` orqali saqlanadi.

> **Ilova tomonidagi qism (hozircha kodda YO'Q):** login ekrani
> (Activity/Fragment) umuman yo'q — `ApiService.login()` hech qayerdan
> chaqirilmaydi, `saveToken`/`saveServerUrl`/`saveUserName`/`savePassword`/
> `saveLoginState` ham chaqirilmaydi (`CustomFunctions.java:243-298`).
> Backend tayyor bo'lgach: (1) login ekrani qurilishi, (2) shu ekranda
> operator raqamlarini (SIM slot bo'yicha) so'rashi, (3) `LoginRequest`
> yuqoridagi to'liq shaklga kengaytirilishi kerak.

---

## 5. Call yozuvini yuklash (Upload)

Real, ishlab turgan endpoint — `RecordUploader.kt`, `UploadRecordingWorker.kt`
va (backend tayyor bo'lgach) qo'lda "Upload" ekrani orqali chaqiriladi.

### 5.1 So'rov — to'liq CDR

```
POST {server_url}api/call/v1/upload
Content-Type: application/json
```

Har bir yozuv **alohida so'rov** (ketma-ket, 300–500ms oraliq bilan).

```jsonc
{
  // ── Hisob / autentifikatsiya ──────────────────────────────────────────
  "user_name":       "operator1",              // login identifikatori
  "api_key":         "b7e2f1c9-....",          // token, BODY ICHIDA

  // ── Qo'ng'iroq identifikatori ────────────────────────────────────────
  "call_id":         "a1b2c3-...",             // DEDUP KALITI
  "call_type":       "inbound",                // "inbound" | "outbound"
  "call_status":     "answered",               // "answered" | "no_answer"

  // ── Ikkala tomon — TO'LIQ raqam + (topilsa) ism (§0.1, §0.2) ─────────
  "from":                "+998901234567",      // inbound: qarshi tomon | outbound: operator_number
  "from_name":           "Aziz Karimov",        // shu raqamga mos ism, topilmasa null
  "to":                  "+998998887766",      // inbound: operator_number | outbound: qarshi tomon
  "to_name":             "Jonibek Yorqulov",    // shu raqamga mos ism (operator bo'lsa — full_name), topilmasa null
  "operator_number":     "+998998887766",      // §3 — shu qo'ng'iroqda ishlatilgan operator raqami
  "counterparty_number": "+998901234567",      // qarshi tomon raqami — yo'nalishdan mustaqil, filtr/qidiruv uchun
  "counterparty_name":   "Aziz Karimov",        // ContactResolver (qurilma kontaktlari) orqali topilgan ism, topilmasa null
  "sim_slot":            0,                     // CallRecordEntity.simSlot

  // ── Vaqt / davomiylik ─────────────────────────────────────────────────
  "duration":        47,                        // soniya
  "start_time":      "2026-08-09 14:03:11",     // lokal vaqt
  "end_time":        "2026-08-09 14:03:58",

  // ── Audio ────────────────────────────────────────────────────────────
  "audio_filename":  "998901234567_20260809140311.ogg",  // yoki "none"
  "audio_file":      "T2dnUwACAAAAAAAAAAA...==",           // Base64 Opus/OGG, yoki JSON null

  // ── Joylashuv (Settings → "Locationni yoqish") ────────────────────────
  "latitude":        41.311081,                 // Double, yoki null
  "longitude":       69.240562,                 // Double, yoki null
  "address":         ""                         // odatda bo'sh — faqat "Copy location" bosilgach to'ladi
}
```

### 5.2 `from`/`to`/ism — to'liqlik qoidasi

- `callType == "inbound"` → `from` = `counterparty_number`, `from_name` = `counterparty_name`; `to` = `operator_number`, `to_name` = operator `full_name`.
- `callType == "outbound"` → `from` = `operator_number`, `from_name` = operator `full_name`; `to` = `counterparty_number`, `to_name` = `counterparty_name`.
- `from`/`to` — **har doim to'liq E.164 raqam**, hech qachon `user_name` yoki boshqa matn emas (§0.1).
- `counterparty_name` — `ContactResolver.resolveCached()/resolveAsync()` orqali qurilmaning `ContactsContract.PhoneLookup`idan topiladi (`ContactResolver.kt:64-80`, `READ_CONTACTS` ruxsati kerak). Topilmasa — `null` yuboriladi (bo'sh matn emas), backend buni "ism aniqlanmagan" deb talqin qiladi.
- Backendning o'z kontakt katalogi bo'lsa (masalan admin panelda qo'lda qo'shilgan kontaktlar), u qurilmadan kelgan ismni **ustidan yozishi** mumkin — bu holat javobda qaytariladi (§5.4, `resolved_name`), qurilmadan kelgan `counterparty_name`ni ALMASHTIRMAYDI, faqat qo'shimcha ma'lumot sifatida qaytadi (ikkala manbani ham saqlab qolish — audit uchun foydali).
- `operator_number`/`operator_number_missing` — §3'dagi qoidaga bo'ysunadi.

**`counterparty_number` nega alohida:** `from`/`to` yo'nalishga qarab
almashadi (CDR standarti), lekin "qaysi tashqi raqam bilan gaplashildi"
filtr/qidiruv/CRM integratsiyasi uchun doim BITTA barqaror maydonda
bo'lishi qulay.

### 5.3 Audio

- Yuborilishdan oldin **Opus/OGG** ga transkodlanadi (mono, 16kHz,
  ~32kbps, `AudioTranscoder.kt`). Muvaffaqiyatsiz bo'lsa — original fayl
  (`.m4a`/`.amr`/`.3gp`) o'zgarishsiz yuboriladi.
- `audio_filename` orqali backend formatni aniqlaydi (`.ogg` = transkodlangan).
- Fayl topilmasa: `audio_filename="none"`, `audio_file=null`.
- ⚠️ Hozirgi kod faqat `filePath` (telefon xotirasidan topilgan yozuv)ni
  yuboradi; `realtimeFilePath` (mikrofon orqali ikkinchi manba) hali
  kiritilmagan. Tavsiya — ikkinchi juftlik:

```jsonc
  "audio_filename_realtime": "realtime_998901234567_20260809140311.ogg",
  "audio_file_realtime":     "T2dnUwACAAAA...=="   // yoki null
```

### 5.4 Javob

```jsonc
// 200 OK — yangi qabul qilindi
{
  "success":     true,
  "status":      "received",         // "received" | "already_exists" | "processing"
  "call_id":     "a1b2c3-...",
  "server_id":   "srv_9f3e...",
  "received_at": "2026-08-09T14:04:02Z",   // ISO-8601 UTC
  "resolved_name": "Aziz Karimov (Mijoz)",  // backendning o'z kontakt katalogidan topilgan ism, agar qurilma yuborganidan farq qilsa/aniqroq bo'lsa; bo'lmasa null
  "audio": {
    "stored":     true,
    "url":        "https://.../recordings/a1b2c3.ogg",
    "size_bytes": 48213
  }
}

// 409 Conflict — dublikat
{
  "success": false,
  "status":  "already_exists",
  "call_id": "a1b2c3-...",
  "message": "call_id already exists"
}

// 4xx/5xx — xatolik
{
  "success": false,
  "status":  "error",
  "call_id": "a1b2c3-...",
  "message": "invalid api_key"
}
```

`RecordUploader.uploadRecord()` **hozircha** faqat HTTP status + body
matnida `"already exist"`/`"duplicate"`/`"unique constraint"`/`"call_id"`
so'zlarini qidiradi (JSON parse qilmaydi). To'liq javobni ishlatish uchun
ilova tomonida (hozircha yo'q):
1. `RecordUploader` javobni JSON sifatida parse qiladi.
2. `CallRecordEntity`ga `serverId: String?`, `uploadedAt: Long?`,
   `audioUrl: String?`, `resolvedName: String?` ustunlari qo'shiladi
   (yangi Room migration).
3. `CallListAdapter`dagi ism ko'rsatish (`bindDisplayName`,
   `bindExpandedHeader`) — mavjud `ContactResolver` natijasi bilan bir
   qatorda, server `resolved_name` bergan bo'lsa, ustunlik shunga
   beriladi (backend katalogi odatda qurilma telefon kitobidan aniqroq —
   masalan CRM'dagi "Mijoz — Aziz Karimov" kabi kontekst bilan).

### 5.5 Qayta urinish (retry)

| Holat | `synced` | `uploadCount` | Keyingi qadam |
|---|---|---|---|
| Server 2xx | `true` | o'zgarmaydi | Yuklangan |
| "already_exists" | `true` | o'zgarmaydi | Yuklangan deb hisoblanadi |
| Server xato (4xx/5xx) | `false` | **+1** | `uploadCount<3` bo'lguncha avtomatik qayta uriniladi (15 daqiqada bir) |
| Tarmoq xatosi | `false` | o'zgarmaydi | Cheksiz qayta uriniladi |
| `uploadCount>=3` | `false` | — | Faqat qo'lda "Upload" ekranida, cheklovsiz |

Avtomatik worker `WorkManager` orqali har 15 daqiqada (`UploadWorkHelper.kt`)
+ hodisaviy darhol ishga tushirish; bir vaqtda faqat bitta worker (`Mutex`).

---

## 6. Qo'ng'iroqlar ro'yxatini serverdan olish / dedup tekshiruvi

Hozirgi kodda GET/pull umuman yo'q — SaaS uchun professional dedup shart,
`RecordUploader`dagi matn-qidirish orqali "already exists" aniqlash o'rniga
oldindan tekshirish tavsiya etiladi. Loyiha konventsiyasiga mos — POST:

```
POST {server_url}api/call/v1/calls/list
```

```jsonc
// Request
{
  "user_name": "operator1",
  "api_key":   "b7e2f1c9-....",
  "call_ids":  ["a1b2c3-...", "d4e5f6-...", "..."]
}

// Response
{
  "success": true,
  "calls": [
    { "call_id": "a1b2c3-...", "exists": true,  "server_id": "srv_9f3e" },
    { "call_id": "d4e5f6-...", "exists": false }
  ]
}
```

Foydalanish: `UploadRecordingWorker.doUploadWork()` yuklashdan OLDIN shu
so'rovni yuboradi, `exists=true` bo'lganlarni to'g'ridan
`repository.markSynced(...)` qiladi, faqat qolganlarini yuklaydi.

---

## 7. Statistika sinxronizatsiyasi (Total call time)

`TotalCallTimeActivity` (`CallRecordDao.kt:189-204`: `totalDurationAll`,
`totalCountAll`, `totalDurationByType`, `totalCountByType`, `totalMissedCount`)
hozircha FAQAT local DB'dan agregatsiya qiladi. Backend allaqachon har bir
`call_id` yozuvini oladi (§5), shu sabab alohida "statistika yuborish"
endpointi SHART EMAS — backend `duration`/`call_type`/`call_status`dan
o'zi agregatsiya qiladi. Kerak bo'lishi mumkin bo'lgan yagona narsa —
operator o'z serverdagi umumiy statistikasini so'rab olishi (ko'p
qurilmali holat yoki qayta o'rnatilgandan keyin local DB tozalangan bo'lsa):

```
POST {server_url}api/call/v1/stats/summary
{
  "user_name": "operator1",
  "api_key":   "b7e2f1c9-...."
}

// Response
{
  "success": true,
  "total_duration_sec": 184230,
  "total_count":         412,
  "inbound_count":       260,
  "outbound_count":      152,
  "missed_count":        34
}
```

---

## 8. Ilova diagnostika logini yuborish — "Send application log"

Bu **call log emas** — ilovaning texnik/diagnostika logi. Settings →
Security → **"Send application log"** qatori bor (`strings.xml:44`,
`send_log_title`), `LogViewerActivity` ochadi, lekin kod ANIQ belgilaydi:

> `SecurityPreferenceFragment.java:90-92`: *"Send application log" — oxirgi
> 24 soatlik loglarni ko'rsatadi. **HALI HECH NARSA JO'NATILMAYDI** — real
> "send" xatti-harakati keyinroq aniqlanadi (foydalanuvchi so'ragan).*

Manba — `AppLogger.kt`: kunlik fayllar (`app-YYYY-MM-DD.log`,
`filesDir/app_logs/`, 3 kun saqlanadi), logcat uslubidagi matn qatorlari:

```
2026-08-09 14:03:11.482  D/CallReceiver: onCallStateChanged: OFFHOOK
2026-08-09 14:03:58.117  I/UploadWorker: ✅ Muvaffaqiyatli yuklandi: a1b2c3-...
```

```
POST {server_url}api/call/v1/log
```

```jsonc
// Request
{
  "user_name": "operator1",
  "api_key":   "b7e2f1c9-....",
  "hours":     24,
  "log_text":  "2026-08-09 14:03:11.482  D/CallReceiver: onCallStateChanged: OFFHOOK\n..."
                 // AppLogger.getRecentLogs(context, 24).joinToString("\n")
}

// Response
{ "success": true }
```

Ilova tomonida: `LogViewerActivity`ga "Yuborish" tugmasi qo'shilib,
`AppLogger.getRecentLogs()` natijasini shu endpointga POST qiladi (xuddi
`RecordUploader.uploadRecord()`dagi OkHttp naqshi bilan).

---

## 9. Standart javob konverti va xatolik taksonomiyasi

Barcha endpointlar (§4–§8) bitta izchil konvert ishlatadi:

```jsonc
// Muvaffaqiyat
{ "success": true, /* ...endpointga xos maydonlar... */ }

// Xatolik
{ "success": false, "message": "inson-o'qiydigan sabab", "error_code": "INVALID_API_KEY" }
```

| `error_code` | HTTP status | Ma'no |
|---|---|---|
| `INVALID_CREDENTIALS` | 401 | Login/parol noto'g'ri (`/auth`) |
| `INVALID_API_KEY` | 401 | `api_key` yaroqsiz/muddati o'tgan |
| `DUPLICATE_CALL_ID` | 409 | `call_id` serverda mavjud (`/upload`) |
| `MISSING_FIELD` | 400 | Majburiy maydon yo'q/bo'sh |
| `AUDIO_TOO_LARGE` | 413 | Audio hajmi limitdan katta (limitni backend belgilaydi) |
| `SERVER_ERROR` | 500 | Kutilmagan server xatosi |

Ilova tomoni (`RecordUploader.kt:108-118`) hozircha faqat HTTP status +
matn-qidirishga tayanadi; `error_code` maydoni qo'shilgach, ilova buni
to'g'ridan parse qilib ishonchliroq boshqarishi mumkin bo'ladi.

---

## 10. Xavfsizlik va versiyalash — qo'shimcha tavsiyalar

- `api_key` hozircha JSON body ichida yuriladi (header emas). Ishlaydi,
  lekin **tavsiya**: uzoq muddatda `Authorization: Bearer <api_key>`
  headerga ko'chirish (ilova tomonida kichik refaktor, backend ikkalasini
  ham vaqtincha qabul qilishi mumkin).
- Audio hajmi — backend `AUDIO_TOO_LARGE` (413) uchun aniq limit e'lon
  qilishi kerak (masalan 20MB/yozuv).
- `READ_CONTACTS` ruxsati bo'lmasa `counterparty_name` doim `null` keladi
  — bu normal holat, backend `null`ni "ism aniqlanmagan" deb qabul
  qilishi, xato deb hisoblamasligi kerak.
- `server` maydoni (`/auth`) — agar bitta backend bir nechta tashkilotga
  (multi-tenant) xizmat qilsa, tashkilot identifikatori sifatida talqin
  qilinishi mumkin.
- Versiyalash — prefiks allaqachon `v1` (`/api/call/v1/...`), kelajakda
  buzuvchi o'zgarish bo'lsa `v2` prefiksi bilan parallel yuritiladi.

---

## 11. Xulosa — to'liq checklist

**Kirish**
- [ ] `POST /api/call/v1/auth` — §4, bitta chaqiruvda: login/parol/server + operator raqamlari (`phone_numbers`, SIM slot bo'yicha) + qurilma ma'lumoti. Alohida `/register` YO'Q — ilova faqat login qiladi.

**Call yuklash**
- [ ] `POST /api/call/v1/upload` — §5.1'dagi TO'LIQ CDR JSON: audio + joylashuv + operator/counterparty raqamlari VA ismlari + sim_slot.
- [ ] `from`/`to`/`operator_number`/`counterparty_number` — ISTISNOSIZ to'liq E.164 raqam, login-ism EMAS (§0.1).
- [ ] `from_name`/`to_name`/`counterparty_name` — qurilma kontaktidan (topilsa), topilmasa `null` (§0.2, §5.2).
- [ ] `call_id` bo'yicha serverda UNIQUE cheklov (dedup).
- [ ] `audio_file` — Base64 Opus/OGG (yoki fallback original) qabul qilib saqlash; ixtiyoriy — `audio_file_realtime`.
- [ ] §5.4'dagi to'liq JSON javob (`status`, `server_id`, `audio.url`, `resolved_name`) — UI'da messenger darajasidagi holat/ism ko'rsatish uchun.

**Sinxronizatsiya / qo'shimcha**
- [ ] `POST /api/call/v1/calls/list` — §6, dedup/pre-check.
- [ ] `POST /api/call/v1/stats/summary` — §7, operator statistikasi.
- [ ] `POST /api/call/v1/log` — §8, ilova diagnostika logi.

**Sifat**
- [ ] §9'dagi standart javob konverti va `error_code` taksonomiyasi barcha endpointlarda bir xil qo'llanilsin.
- [ ] §10'dagi xavfsizlik tavsiyalari (audio limiti, `Authorization` header) ko'rib chiqilsin.
