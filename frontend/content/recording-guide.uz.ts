import type { GuideContent } from "./recording-guide.types";

export const uz: GuideContent = {
  metaTitle: "Ichki qo'ng'iroq yozuvini yoqish — dooCall yo'riqnomasi",
  metaDescription:
    "Samsung, Xiaomi va Huawei/Honor telefonlarida ichki (built-in) qo'ng'iroq yozuvini yoqish bo'yicha bosqichma-bosqich yo'riqnoma.",
  heroTitle: "Ichki qo'ng'iroq yozuvini yoqish",
  heroText:
    "Android 9+ da Google ilovalarga qo'ng'iroq ovozini yozishni taqiqlagan. Lekin telefonning o'z yozib olish funksiyasini yoqib olsak — ikkala tomon ovozi toza yoziladi. Quyida buni Samsung, Xiaomi va Huawei/Honor da qanday qilish ko'rsatilgan.",
  tocTitle: "Mundarija",
  backToLanding: "Bosh sahifa",
  supportNote:
    "Savolingiz bormi? Qo'llab-quvvatlash xizmatiga murojaat qiling — telefon **modeli**, **Android versiyasi** va **muammo tavsifi**ni yuboring.",
  legalNote:
    "Bu amallarni o'z mas'uliyatingiz ostida bajarasiz. Mintaqa o'zgartirish va tashqi fayl o'rnatish telefon kafolatiga ta'sir qilishi yoki ma'lumotlar yo'qolishiga olib kelishi mumkin. Qo'ng'iroqni yozib olishda mahalliy qonunchilikka rioya qiling — ko'p mamlakatlarda suhbatdoshni ogohlantirish talab etiladi.",
  sections: [
    {
      id: "why",
      title: "Nega bu kerak?",
      blocks: [
        {
          t: "p",
          text: "Telefonda qo'ng'iroq ikki xil yo'l bilan yozilishi mumkin:",
        },
        {
          t: "table",
          head: ["Yo'l", "Kim yozadi", "Natija"],
          rows: [
            [
              "**Ichki yozuv**",
              "Telefonning **o'zi** (ishlab chiqaruvchi funksiyasi)",
              "**Ikkala tomon ovozi toza**",
            ],
            [
              "**Mikrofon yozuvi**",
              "Bizning ilova (zaxira usul)",
              "O'z ovozingiz aniq, mijoz **past** eshitiladi",
            ],
          ],
        },
        {
          t: "p",
          text: "Ilova ikkalasini ham qiladi va **ichki yozuvni ustun qo'yadi**. Ya'ni ichki yozuvni yoqsangiz — sifat avtomatik ravishda eng yaxshisiga o'tadi, ilovada qo'shimcha hech narsa sozlash **shart emas**.",
        },
        {
          t: "note",
          text: "Ichki yozuv ko'p mamlakatlarda (MDH, Yevropa, AQSh) **zavoddan o'chirilgan**. U Hindiston, Indoneziya, Tailand, Vetnam kabi mintaqalar uchun ochiq. Shuning uchun quyidagi usullar telefonning **mintaqa sozlamasini** o'zgartiradi.",
        },
      ],
    },
    {
      id: "check-first",
      title: "1-qadam: avval tekshiring",
      blocks: [
        {
          t: "p",
          text: "Balki telefoningizda bu funksiya allaqachon bordir. Tekshirish 30 soniya:",
        },
        {
          t: "steps",
          items: [
            "**Telefon** (qo'ng'iroq belgisi) ilovasini oching",
            "**Sozlamalar**ga kiring (yuqori burchakdagi menyu tugmasi)",
            "**«Qo'ng'iroqni yozib olish»** (*Call recording / Record calls*) bandini qidiring",
            "Bor bo'lsa — **«Avtomatik yozib olish»**ni yoqing",
          ],
        },
        {
          t: "table",
          head: ["Natija", "Nima qilish"],
          rows: [
            [
              "Bunday band **bor**",
              "Yoqing — tamom! Boshqa hech narsa kerak emas",
            ],
            [
              "Bunday band **yo'q**",
              "Pastdagi o'z brendingiz bo'yicha yo'riqnomaga o'ting",
            ],
          ],
        },
        {
          t: "tip",
          text: "Avval ilovaning o'z mikrofon yozuvini ham sinab ko'ring — ba'zi telefonlarda u ham yetarlicha yaxshi chiqadi va hech narsa o'zgartirish kerak bo'lmaydi.",
        },
      ],
    },
    {
      id: "samsung",
      title: "Samsung uchun",
      tone: "samsung",
      blocks: [
        {
          t: "p",
          text: "Samsung telefonlarida yozib olish funksiyasi **bor**, lekin mintaqaga qarab o'chirilgan. Uni **SamFW Tool** dasturi orqali yoqamiz.",
        },
        {
          t: "video",
          href: "https://youtu.be/l0N7QM6uCYc?t=85",
          label: "Video yo'riqnomani ochish (1:25 dan boshlanadi)",
        },
        { t: "h3", text: "Nima kerak" },
        {
          t: "list",
          items: [
            "**Windows kompyuter**",
            "**USB kabel** (ma'lumot uzatadigan, faqat quvvatlash uchun emas)",
            "**SamFW Tool** — [samfw.com/blog/samfwtool](https://samfw.com/blog/samfwtool)",
          ],
        },
        {
          t: "warn",
          text: "**Avval telefondagi muhim ma'lumotlarni zaxiralang (backup)!** Ba'zi hollarda mintaqani o'zgartirish telefonni **zavod holatiga qaytaradi** — barcha rasm, kontakt va ilovalar o'chib ketishi mumkin.",
        },
        {
          t: "details",
          summary: "1. Telefonni tayyorlash — Ishlab chiquvchi rejimi",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "**Sozlamalar** → **Telefon haqida** → **Dasturiy ta'minot ma'lumoti**",
                "**«Yig'ish raqami»** (*Build number*) ustiga **7 marta** ketma-ket bosing",
                "«Siz endi ishlab chiquvchisiz» degan xabar chiqadi",
                "**Sozlamalar** → **Ishlab chiquvchi parametrlari**ga kiring",
                "**USB orqali nosozliklarni tuzatish** (*USB debugging*) — **yoqing**",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "2. SamFW Tool ni o'rnatish",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "[samfw.com/blog/samfwtool](https://samfw.com/blog/samfwtool) saytiga kiring",
                "Dasturni yuklab oling va kompyuterga o'rnating",
                "Dasturni **administrator nomidan** ishga tushiring",
                "Telefonni USB kabel bilan ulang",
                "Telefonda **«USB debugging'ga ruxsat berilsinmi?»** so'ralsa — **Ruxsat berish**",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "3. Mintaqani (CSC) o'zgartirish",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "Dasturda **ADB** bo'limiga o'ting",
                "**`Get list supported CSC`** tugmasini bosing",
                "Chiqqan ro'yxatdan **yozib olishga ruxsat beruvchi** mintaqani tanlang (quyidagi jadval)",
                "Tanlangan mintaqani o'rnating va telefonni **qayta ishga tushiring**",
              ],
            },
            {
              t: "table",
              head: ["Kod", "Mintaqa"],
              rows: [
                ["**INS**", "Hindiston"],
                ["**XID**", "Indoneziya"],
                ["**THL**", "Tailand"],
                ["**XXV**", "Vetnam"],
                ["**SEK**, **ILO**", "Boshqa mos mintaqalar"],
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "Agar ro'yxatda bu kodlar chiqmasa",
          blocks: [
            {
              t: "p",
              text: "Demak telefoningiz oddiy usul bilan mintaqani almashtira olmaydi. Variantlar:",
            },
            {
              t: "list",
              items: [
                "**Proshivka (majburiy flash)** — kerakli mintaqa proshivkasini to'liq o'rnatish. Bu murakkabroq va telefon **albatta tozalanadi**",
                "**Mutaxassisga topshirish** — servis markazlar bu xizmatni ko'rsatadi",
                "**Android GO** modellari va ba'zi eski modellarda bu **umuman imkonsiz**",
              ],
            },
          ],
        },
        { t: "h3", text: "Yakuniy qadam" },
        {
          t: "steps",
          items: [
            "**Telefon** ilovasi → **Sozlamalar** → **Qo'ng'iroqni yozib olish**",
            "**«Avtomatik yozib olish»**ni **yoqing**",
            "Bitta sinov qo'ng'irog'i qiling va ilovada tinglab ko'ring",
          ],
        },
      ],
    },
    {
      id: "xiaomi",
      title: "Xiaomi / Redmi / POCO uchun",
      tone: "xiaomi",
      blocks: [
        {
          t: "p",
          text: "Xiaomi da usul **boshqacha** — mintaqani o'zgartirish shart emas. Kompyuter orqali maxsus **Dialer (Telefon) ilovasi** o'rnatiladi va u yozib olishni ochadi.",
        },
        {
          t: "warn",
          text: "Ichki yozuv **barcha** Xiaomi modellarida yo'q. **Mi A1, Mi A2, Mi A3** va **Android GO** modellarida umuman yo'q — ularda faqat mikrofon yozuvi ishlaydi.",
        },
        { t: "h3", text: "Nima kerak" },
        {
          t: "list",
          items: [
            "**Windows kompyuter**",
            "**USB kabel**",
            "**Arxiv fayl** — [yuklab olish](https://t.me/c/3177623007/75)",
          ],
        },
        {
          t: "note",
          text: "Yuklab olish havolasi **yopiq Telegram kanalida**. Ochilmasa — qo'llab-quvvatlash xizmatiga murojaat qiling, fayl yuboriladi.",
        },
        {
          t: "details",
          summary: "1. Ishlab chiquvchi rejimini yoqish",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "**Sozlamalar** → **Telefon haqida**",
                "**«MIUI versiyasi»** (yoki *HyperOS versiyasi*) ustiga **7 marta** bosing",
                "«Siz endi ishlab chiquvchisiz» xabari chiqadi",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "2. Kerakli 2 ta sozlamani yoqish",
          open: true,
          blocks: [
            {
              t: "p",
              text: "**Sozlamalar** → **Qo'shimcha sozlamalar** → **Ishlab chiquvchi parametrlari**:",
            },
            {
              t: "table",
              head: ["Sozlama", "Holati"],
              rows: [
                [
                  "**USB orqali nosozliklarni tuzatish** (*USB debugging*)",
                  "Yoqilsin",
                ],
                [
                  "**USB orqali ilovalarni o'rnatish** (*Install via USB*)",
                  "Yoqilsin",
                ],
              ],
            },
            {
              t: "tip",
              text: "*«Install via USB»*ni yoqishda Mi-akkauntga kirish va SIM-karta talab qilinishi mumkin — bu normal holat, tizim talabi.",
            },
          ],
        },
        {
          t: "details",
          summary: "3. Faylni ishga tushirish",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "Arxivni kompyuterga **yuklab oling**",
                "Arxivni **oching** (*Extract* — WinRAR yoki 7-Zip orqali)",
                "Telefonni USB kabel bilan kompyuterga ulang",
                "Ichidagi **`Install_Xiaomi_Dialer.bat`** faylini **ikki marta bosing**",
                "Qora oyna (buyruqlar oynasi) ochiladi — **yopmang**, tugashini kuting",
                "Telefonda so'rov chiqsa — **Ruxsat berish** / **O'rnatish**ni bosing",
              ],
            },
          ],
        },
        { t: "h3", text: "Yakuniy qadam" },
        {
          t: "steps",
          items: [
            "Telefonni **qayta ishga tushiring**",
            "**Telefon** ilovasi → **menyu** → **Sozlamalar** → **Qo'ng'iroqni yozib olish**",
            "**«Avtomatik yozib olish»**ni **yoqing**",
          ],
        },
      ],
    },
    {
      id: "huawei",
      title: "Huawei / Honor uchun",
      tone: "huawei",
      blocks: [
        {
          t: "p",
          text: "Huawei va Honor telefonlarida (Android 9 dan boshlab) yozib olish moduli **o'chirilgan**, lekin uni **qayta o'rnatib** yoqish mumkin. Kompyuter kerak emas — hammasi telefonning o'zida bajariladi.",
        },
        {
          t: "danger",
          text: "**Faqat o'z versiyangizga mos modulni o'rnating!** Noto'g'ri modul yo **o'rnatilmaydi**, yoki o'rnatiladi-yu — telefon **noto'g'ri ishlay boshlaydi**. Xato o'rnatilgan bo'lsa: avval uni **o'chirib tashlang**, keyin to'g'ri versiyasini o'rnating.",
        },
        { t: "h3", text: "1. Avval versiyangizni aniqlang" },
        {
          t: "p",
          text: "**Sozlamalar** → **Telefon haqida** bo'limidan **ikkita** raqamni yozib oling:",
        },
        {
          t: "table",
          head: ["Nima qidiriladi", "Qayerda"],
          rows: [
            ["**Android versiyasi**", "*Android versiyasi* qatori"],
            [
              "**EMUI** (Huawei) yoki **Magic UI** (Honor) versiyasi",
              "*EMUI versiyasi* / *Magic UI versiyasi* qatori",
            ],
          ],
        },
        {
          t: "tip",
          text: "Huawei da qobiq **EMUI**, Honor da esa **Magic UI** deb ataladi — ular bir-biriga mos keladi (EMUI 11 ≈ Magic UI 4.0).",
        },
        { t: "h3", text: "2. Modulni yuklab oling" },
        {
          t: "table",
          head: ["Versiyangiz", "Yuklab olish"],
          rows: [
            [
              "**EMUI 10 / 10.1** (*Magic UI 3.0–3.1*)",
              "[CallRecording 10.1.0](https://www.mediafire.com/file/jfsfu7gf958a32r/CallRecording_10.1.0.apk)",
            ],
            [
              "**EMUI 11** (*Magic UI 4.0*)",
              "[CallRecorder EMUI 11](https://www.mediafire.com/file/6ijyld7yz2g7koz/Huawei+CallRecorder+EMUI+11.apk)",
            ],
            [
              "**EMUI 12** — 1-variant",
              "[HwCallRecorder 12.0.0.109](https://www.mediafire.com/file/nugzvusdb64s1bb/HwCallRecorder+12.0.0.109_HuaweiAilesi.apk/file)",
            ],
            [
              "**EMUI 12** — 2-variant",
              "[CallRecorder EMUI 12](https://www.mediafire.com/file/44jr1hfb3zwszfc/CallRecorder+EMUI+12.apk/file)",
            ],
            [
              "**EMUI 13 / 14**",
              "[EMUI13 CallRecorder](https://www.mediafire.com/file/c5zlcdpb6mafqen/EMUI13_CallRecorder.apk/file)",
            ],
          ],
        },
        {
          t: "tip",
          text: "**EMUI 12 uchun ikkita variant bor.** Birinchisi o'rnatilmasa yoki ishlamasa — uni o'chirib, **ikkinchisini** sinab ko'ring. **EMUI 14** uchun alohida modul yo'q — EMUI 13 niki sinaladi.",
        },
        {
          t: "note",
          text: "**Android 9**, **Honor Android 12** va **Honor Android 13/14** uchun modullar alohida bo'ladi — ular yuqoridagi ro'yxatda yo'q. Kerak bo'lsa qo'llab-quvvatlash xizmatidan so'rang.",
        },
        {
          t: "details",
          summary: "3. O'rnating",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "Havoladan **APK faylni telefonga** yuklab oling",
                "**Fayllar** ilovasidan yuklangan faylni toping va **bosing**",
                "*«Noma'lum manbalardan o'rnatishga ruxsat berilmagan»* chiqsa — **Sozlamalar**ga o'ting va brauzer/fayl menejeriga **ruxsat bering**",
                "**O'rnatish** tugmasini bosing va tugashini kuting",
              ],
            },
          ],
        },
        { t: "h3", text: "4. Ruxsatlarni bering — bu qadam shart" },
        {
          t: "danger",
          text: "Modul o'rnatilgani bilan **ishlamaydi**, agar unga ruxsatlar berilmasa! Bu eng ko'p o'tkazib yuboriladigan qadam.",
        },
        {
          t: "steps",
          items: [
            "**Sozlamalar** → **Ilovalar** → **Ilovalar** ro'yxati",
            "Ro'yxatdan **`Recorder`** (yoki *Qo'ng'iroqlarni yozib olish*)ni toping",
            "Uni bosing → **Ruxsatlar**",
            "**Berilmagan barcha ruxsatlarni yoqing** (mikrofon, xotira, telefon, kontaktlar)",
          ],
        },
        { t: "h3", text: "5. Yozib olishni yoqing" },
        {
          t: "steps",
          items: [
            "Telefonni **qayta ishga tushiring**",
            "**Telefon** ilovasi → **Sozlamalar** → **Qo'ng'iroqlarni yozib olish**",
            "**«Avtomatik»** rejimini yoqing",
          ],
        },
        {
          t: "details",
          summary: "Honor + Android 13 / 14",
          blocks: [
            {
              t: "p",
              text: "Ishlab chiqaruvchi **avtomatik** yozib olishni cheklab qo'ygan — yozuv har safar **tugma bilan qo'lda** boshlanadi. Modul o'rnatilgach ruxsatlarni berishni **unutmang** (4-qadam). Avtomatik rejimni ochish uchun qo'shimcha amallar kerak bo'ladi — qo'llab-quvvatlashga murojaat qiling.",
            },
          ],
        },
        {
          t: "details",
          summary: "Honor + Android 15 — tavsiya etilmaydi",
          blocks: [
            {
              t: "list",
              items: [
                "Avtomatik yozib olish **cheklangan** — faqat qo'lda tugma orqali",
                "Aylanma yo'llar bor, lekin **barqaror ishlashi kafolatlanmaydi**",
                "Telefon **suhbatdoshni yozuv haqida ogohlantirishi** mumkin va buni **o'chirib bo'lmaydi**",
              ],
            },
            {
              t: "p",
              text: "**Xulosa:** ish uchun Android 15 li Honor telefonini olmaslikni tavsiya qilamiz.",
            },
            {
              t: "tip",
              text: "**Avval tekshiring:** qo'ng'iroq qiling va ekranga qarang — **to'lqin belgisiga o'xshash yozib olish tugmasi** bormi? Bo'lsa, modul allaqachon o'rnatilgan, qayta o'rnatish shart emas.",
            },
          ],
        },
        {
          t: "details",
          summary: "Android GO modellari",
          blocks: [
            {
              t: "p",
              text: "Android GO versiyasidagi Huawei/Honor telefonlari uchun yozib olish moduli **umuman mavjud emas**. Bunday telefonlarda faqat mikrofon yozuvi ishlaydi.",
            },
          ],
        },
      ],
    },
    {
      id: "verify",
      title: "Yoqilganini qanday bilamiz?",
      blocks: [
        {
          t: "steps",
          items: [
            "Istalgan raqamga **sinov qo'ng'irog'i** qiling, **10–15 soniya** gaplashing",
            "Qo'ng'iroqni tugatib, **bir daqiqa kuting** (telefon faylni saqlaydi)",
            "Ilovada o'sha qo'ng'iroqni oching va **yozuvni tinglang**",
          ],
        },
        {
          t: "table",
          head: ["Eshitilayotgani", "Ma'nosi"],
          rows: [
            [
              "**Ikkala ovoz ham toza**",
              "Ichki yozuv ishlayapti — muvaffaqiyat!",
            ],
            [
              "Faqat **o'z ovozingiz** aniq",
              "Mikrofon yozuvi ishlayapti — ichki yozuv hali yoqilmagan",
            ],
            [
              "Ovoz **yo'q**",
              "Ruxsatlarni tekshiring, keyin qo'llab-quvvatlashga yozing",
            ],
          ],
        },
        {
          t: "tip",
          text: "Ilovada alohida «ichki yozuvdan foydalanish» tugmasini bosish **kerak emas** — ilova ichki yozuvni topsa, **o'zi avtomatik** o'shani tanlaydi.",
        },
      ],
    },
    {
      id: "troubleshooting",
      title: "Muammolar va yechimlar",
      blocks: [
        {
          t: "details",
          summary: "Kompyuter telefonni ko'rmayapti",
          blocks: [
            {
              t: "list",
              items: [
                "Kabelni almashtiring — ba'zi kabellar **faqat quvvat** uzatadi",
                "Telefon ekranida USB rejimini **«Fayl uzatish (MTP)»**ga o'zgartiring",
                "USB debugging **yoqilganini** qayta tekshiring",
                "Boshqa USB portga ulang (kompyuterning orqa portlari ishonchliroq)",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "Yozuv bor, lekin ilova uni topmayapti",
          blocks: [
            {
              t: "list",
              items: [
                "Ilovaga **«Barcha fayllarga kirish»** (*All files access*) ruxsati berilganini tekshiring — ichki yozuvni **o'qish uchun shart**",
                "Ilova sozlamalaridan **«Telefon yozuvlari papkasi»**ni qo'lda ko'rsating",
                "Telefonda yozuv haqiqatan saqlanayotganini tekshiring — **Fayllar** ilovasi:",
              ],
            },
            {
              t: "table",
              head: ["Brend", "Papka"],
              rows: [
                ["Samsung", "`Recordings/Call`"],
                ["Xiaomi", "`MIUI/sound_recorder/call_rec`"],
                ["Huawei / Honor", "`Sounds/CallRecord`"],
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "Huawei: modul o'rnatildi, lekin yozib olish ishlamayapti",
          blocks: [
            {
              t: "steps",
              items: [
                "**Ruxsatlarni tekshiring** — 90% hollarda sabab shu: **Sozlamalar** → **Ilovalar** → `Recorder` → **Ruxsatlar** → hammasini yoqing",
                "**Versiya mos kelmagan bo'lishi mumkin** — EMUI versiyangizni qayta tekshiring va boshqa variantni sinang (EMUI 12 uchun 2 ta fayl bor)",
                "Modulni **o'chirib**, telefonni qayta yoqib, **qaytadan** o'rnating",
              ],
            },
          ],
        },
        {
          t: "details",
          summary:
            "Avtomatik yozib olish menyusi bor, lekin ilova yozuvni ololmayapti",
          blocks: [
            {
              t: "p",
              text: "Ba'zi modellarda yozuv telefon xotirasining **yopiq** joyiga saqlanadi va ilovalar u yerga kira olmaydi. Bu holda:",
            },
            {
              t: "list",
              items: [
                "Yozib olish rejimini **«Barcha qo'ng'iroqlar»**ga o'zgartiring",
                "Yordam bermasa — mintaqani o'zgartirish kerak bo'ladi (Samsung bo'limi)",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "Telefon yangilangandan keyin ishlamay qoldi",
          blocks: [
            {
              t: "p",
              text: "Tizim yangilanishi mintaqa sozlamasini **qaytarib yuborishi** mumkin. Yo'riqnomani **qaytadan** bajaring. Ish telefonlarida avtomatik yangilanishni o'chirib qo'yish tavsiya etiladi.",
            },
          ],
        },
      ],
    },
  ],
};
