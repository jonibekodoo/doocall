import type { GuideContent } from "./recording-guide.types";

export const en: GuideContent = {
  metaTitle: "How to enable built-in call recording — dooCall guide",
  metaDescription:
    "Step-by-step guide to enabling built-in call recording on Samsung, Xiaomi and Huawei/Honor phones.",
  heroTitle: "How to enable built-in call recording",
  heroText:
    "Since Android 9, Google has blocked apps from recording call audio. But if you enable the phone's own recording feature, both sides of the call are recorded clearly. Below is how to do it on Samsung, Xiaomi and Huawei/Honor.",
  tocTitle: "Contents",
  backToLanding: "Back to home",
  supportNote:
    "Have questions? Contact support — send your phone **model**, **Android version** and a **description of the issue**.",
  legalNote:
    "You perform these steps at your own risk. Changing the region or installing third-party files may affect your phone's warranty or lead to data loss. When recording calls, comply with local law — many countries require you to notify the other party.",
  sections: [
    {
      id: "why",
      title: "Why does this matter?",
      blocks: [
        {
          t: "p",
          text: "A call can be recorded on a phone in two different ways:",
        },
        {
          t: "table",
          head: ["Method", "Who records", "Result"],
          rows: [
            [
              "**Built-in recording**",
              "The **phone itself** (manufacturer feature)",
              "**Both voices recorded clearly**",
            ],
            [
              "**Microphone recording**",
              "Our app (fallback method)",
              "Your voice is clear, the customer sounds **quiet**",
            ],
          ],
        },
        {
          t: "p",
          text: "The app does both and **prefers built-in recording**. So once you enable built-in recording, quality automatically switches to the best option — there is **nothing extra** to configure in the app.",
        },
        {
          t: "note",
          text: "In many countries (CIS, Europe, US) built-in recording is **disabled from the factory**. It is available in regions such as India, Indonesia, Thailand and Vietnam. That is why the methods below change the phone's **region setting**.",
        },
      ],
    },
    {
      id: "check-first",
      title: "Step 1: check first",
      blocks: [
        {
          t: "p",
          text: "Your phone may already have this feature. Checking takes 30 seconds:",
        },
        {
          t: "steps",
          items: [
            "Open the **Phone** app (the call icon)",
            "Go to **Settings** (the menu button in the top corner)",
            "Look for a **Call recording** (or *Record calls*) option",
            "If it is there — turn on **Auto record calls**",
          ],
        },
        {
          t: "table",
          head: ["Result", "What to do"],
          rows: [
            [
              "The option **exists**",
              "Turn it on — done! Nothing else is needed",
            ],
            [
              "The option is **missing**",
              "Follow the guide for your brand below",
            ],
          ],
        },
        {
          t: "tip",
          text: "Also try the app's own microphone recording first — on some phones it turns out good enough, and you won't need to change anything.",
        },
      ],
    },
    {
      id: "samsung",
      title: "For Samsung",
      tone: "samsung",
      blocks: [
        {
          t: "p",
          text: "Samsung phones **do have** the recording feature, but it is disabled depending on the region. We will enable it using the **SamFW Tool** program.",
        },
        {
          t: "video",
          href: "https://youtu.be/l0N7QM6uCYc?t=85",
          label: "Open the video guide (starts at 1:25)",
        },
        { t: "h3", text: "What you need" },
        {
          t: "list",
          items: [
            "A **Windows computer**",
            "A **USB cable** (one that transfers data, not charge-only)",
            "**SamFW Tool** — [samfw.com/blog/samfwtool](https://samfw.com/blog/samfwtool)",
          ],
        },
        {
          t: "warn",
          text: "**Back up the important data on your phone first!** In some cases changing the region **factory-resets the phone** — all photos, contacts and apps may be erased.",
        },
        {
          t: "details",
          summary: "1. Prepare the phone — Developer mode",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "**Settings** → **About phone** → **Software information**",
                "Tap **Build number** **7 times** in a row",
                'You will see the message "You are now a developer"',
                "Go to **Settings** → **Developer options**",
                "**Turn on** **USB debugging**",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "2. Install SamFW Tool",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "Go to [samfw.com/blog/samfwtool](https://samfw.com/blog/samfwtool)",
                "Download the program and install it on your computer",
                "Run the program **as administrator**",
                "Connect the phone with the USB cable",
                'If the phone asks **"Allow USB debugging?"** — tap **Allow**',
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "3. Change the region (CSC)",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "In the program, go to the **ADB** section",
                "Click the **`Get list supported CSC`** button",
                "From the list, pick a region that **allows recording** (table below)",
                "Apply the selected region and **restart** the phone",
              ],
            },
            {
              t: "table",
              head: ["Code", "Region"],
              rows: [
                ["**INS**", "India"],
                ["**XID**", "Indonesia"],
                ["**THL**", "Thailand"],
                ["**XXV**", "Vietnam"],
                ["**SEK**, **ILO**", "Other suitable regions"],
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "If these codes are not in the list",
          blocks: [
            {
              t: "p",
              text: "That means your phone cannot change its region the simple way. Options:",
            },
            {
              t: "list",
              items: [
                "**Firmware flashing (forced flash)** — fully installing the firmware for the needed region. This is more advanced and the phone **will definitely be wiped**",
                "**Hand it to a specialist** — service centers offer this service",
                "On **Android GO** models and some older models this is **not possible at all**",
              ],
            },
          ],
        },
        { t: "h3", text: "Final step" },
        {
          t: "steps",
          items: [
            "**Phone** app → **Settings** → **Call recording**",
            "**Turn on** **Auto record calls**",
            "Make one test call and listen to it in the app",
          ],
        },
      ],
    },
    {
      id: "xiaomi",
      title: "For Xiaomi / Redmi / POCO",
      tone: "xiaomi",
      blocks: [
        {
          t: "p",
          text: "On Xiaomi the method is **different** — there is no need to change the region. A special **Dialer (Phone) app** is installed via a computer, and it unlocks recording.",
        },
        {
          t: "warn",
          text: "Built-in recording is not available on **all** Xiaomi models. **Mi A1, Mi A2, Mi A3** and **Android GO** models don't have it at all — only microphone recording works on them.",
        },
        { t: "h3", text: "What you need" },
        {
          t: "list",
          items: [
            "A **Windows computer**",
            "A **USB cable**",
            "The **archive file** — [download](https://t.me/c/3177623007/75)",
          ],
        },
        {
          t: "note",
          text: "The download link points to a **private Telegram channel**. If it doesn't open — contact support and the file will be sent to you.",
        },
        {
          t: "details",
          summary: "1. Enable developer mode",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "**Settings** → **About phone**",
                "Tap **MIUI version** (or *HyperOS version*) **7 times**",
                'You will see the message "You are now a developer"',
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "2. Enable the 2 required settings",
          open: true,
          blocks: [
            {
              t: "p",
              text: "**Settings** → **Additional settings** → **Developer options**:",
            },
            {
              t: "table",
              head: ["Setting", "State"],
              rows: [
                ["**USB debugging**", "Enable"],
                ["**Install via USB**", "Enable"],
              ],
            },
            {
              t: "tip",
              text: "Enabling *Install via USB* may require signing in to a Mi account and having a SIM card — this is normal, it's a system requirement.",
            },
          ],
        },
        {
          t: "details",
          summary: "3. Run the file",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "**Download** the archive to your computer",
                "**Extract** the archive (using WinRAR or 7-Zip)",
                "Connect the phone to the computer with the USB cable",
                "**Double-click** the **`Install_Xiaomi_Dialer.bat`** file inside",
                "A black window (command prompt) will open — **don't close it**, wait for it to finish",
                "If a prompt appears on the phone — tap **Allow** / **Install**",
              ],
            },
          ],
        },
        { t: "h3", text: "Final step" },
        {
          t: "steps",
          items: [
            "**Restart** the phone",
            "**Phone** app → **menu** → **Settings** → **Call recording**",
            "**Turn on** **Auto record calls**",
          ],
        },
      ],
    },
    {
      id: "huawei",
      title: "For Huawei / Honor",
      tone: "huawei",
      blocks: [
        {
          t: "p",
          text: "On Huawei and Honor phones (starting from Android 9) the recording module is **disabled**, but it can be **reinstalled** and enabled. No computer needed — everything is done on the phone itself.",
        },
        {
          t: "danger",
          text: "**Install only the module that matches your version!** A wrong module either **won't install**, or it will — and the phone will **start misbehaving**. If you installed the wrong one: **uninstall it** first, then install the correct version.",
        },
        { t: "h3", text: "1. Identify your version first" },
        {
          t: "p",
          text: "In **Settings** → **About phone**, write down **two** values:",
        },
        {
          t: "table",
          head: ["What to look for", "Where"],
          rows: [
            ["**Android version**", "The *Android version* line"],
            [
              "**EMUI** (Huawei) or **Magic UI** (Honor) version",
              "The *EMUI version* / *Magic UI version* line",
            ],
          ],
        },
        {
          t: "tip",
          text: "On Huawei the skin is called **EMUI**, on Honor it's **Magic UI** — they correspond to each other (EMUI 11 ≈ Magic UI 4.0).",
        },
        { t: "h3", text: "2. Download the module" },
        {
          t: "table",
          head: ["Your version", "Download"],
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
              "**EMUI 12** — option 1",
              "[HwCallRecorder 12.0.0.109](https://www.mediafire.com/file/nugzvusdb64s1bb/HwCallRecorder+12.0.0.109_HuaweiAilesi.apk/file)",
            ],
            [
              "**EMUI 12** — option 2",
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
          text: "**There are two options for EMUI 12.** If the first one won't install or doesn't work — uninstall it and try the **second one**. There is no separate module for **EMUI 14** — try the EMUI 13 one.",
        },
        {
          t: "note",
          text: "The modules for **Android 9**, **Honor on Android 12** and **Honor on Android 13/14** are separate — they are not in the list above. Ask support if you need them.",
        },
        {
          t: "details",
          summary: "3. Install",
          open: true,
          blocks: [
            {
              t: "steps",
              items: [
                "Download the **APK file to the phone** from the link",
                "Find the downloaded file in the **Files** app and **tap** it",
                'If *"Installation from unknown sources is not allowed"* appears — go to **Settings** and **grant permission** to the browser/file manager',
                "Tap the **Install** button and wait for it to finish",
              ],
            },
          ],
        },
        { t: "h3", text: "4. Grant permissions — this step is required" },
        {
          t: "danger",
          text: "Even after installation the module **won't work** unless it is granted permissions! This is the most commonly skipped step.",
        },
        {
          t: "steps",
          items: [
            "**Settings** → **Apps** → the **Apps** list",
            "Find **`Recorder`** (or *Call recording*) in the list",
            "Tap it → **Permissions**",
            "**Enable every permission that isn't granted** (microphone, storage, phone, contacts)",
          ],
        },
        { t: "h3", text: "5. Enable recording" },
        {
          t: "steps",
          items: [
            "**Restart** the phone",
            "**Phone** app → **Settings** → **Call recording**",
            "Turn on the **Automatic** mode",
          ],
        },
        {
          t: "details",
          summary: "Honor + Android 13 / 14",
          blocks: [
            {
              t: "p",
              text: "The manufacturer has restricted **automatic** recording — recording has to be started **manually with a button** each time. After installing the module, **don't forget** to grant the permissions (step 4). Unlocking the automatic mode requires extra steps — contact support.",
            },
          ],
        },
        {
          t: "details",
          summary: "Honor + Android 15 — not recommended",
          blocks: [
            {
              t: "list",
              items: [
                "Automatic recording is **restricted** — manual button only",
                "Workarounds exist, but **stable operation is not guaranteed**",
                "The phone may **notify the other party about the recording**, and this **cannot be turned off**",
              ],
            },
            {
              t: "p",
              text: "**Bottom line:** we recommend not buying an Honor phone with Android 15 for work.",
            },
            {
              t: "tip",
              text: "**Check first:** make a call and look at the screen — is there a **recording button that looks like a waveform icon**? If so, the module is already installed and there's no need to reinstall it.",
            },
          ],
        },
        {
          t: "details",
          summary: "Android GO models",
          blocks: [
            {
              t: "p",
              text: "For Huawei/Honor phones running Android GO, a recording module **does not exist at all**. Only microphone recording works on such phones.",
            },
          ],
        },
      ],
    },
    {
      id: "verify",
      title: "How do we know it worked?",
      blocks: [
        {
          t: "steps",
          items: [
            "Make a **test call** to any number and talk for **10–15 seconds**",
            "End the call and **wait a minute** (the phone saves the file)",
            "Open that call in the app and **listen to the recording**",
          ],
        },
        {
          t: "table",
          head: ["What you hear", "What it means"],
          rows: [
            [
              "**Both voices are clear**",
              "Built-in recording is working — success!",
            ],
            [
              "Only **your voice** is clear",
              "Microphone recording is working — built-in recording isn't enabled yet",
            ],
            ["**No** sound", "Check the permissions, then contact support"],
          ],
        },
        {
          t: "tip",
          text: 'You do **not** need to press any separate "use built-in recording" button in the app — if the app finds a built-in recording, it **picks it automatically**.',
        },
      ],
    },
    {
      id: "troubleshooting",
      title: "Troubleshooting",
      blocks: [
        {
          t: "details",
          summary: "The computer doesn't see the phone",
          blocks: [
            {
              t: "list",
              items: [
                "Swap the cable — some cables carry **power only**",
                "On the phone screen, switch the USB mode to **File transfer (MTP)**",
                "Double-check that USB debugging is **enabled**",
                "Try another USB port (the rear ports of a computer are more reliable)",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "The recording exists, but the app can't find it",
          blocks: [
            {
              t: "list",
              items: [
                "Check that the app has the **All files access** permission — it is **required to read** the built-in recording",
                "In the app settings, set the **phone recordings folder** manually",
                "Verify the recording is actually being saved on the phone — the **Files** app:",
              ],
            },
            {
              t: "table",
              head: ["Brand", "Folder"],
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
          summary:
            "Huawei: the module is installed, but recording doesn't work",
          blocks: [
            {
              t: "steps",
              items: [
                "**Check the permissions** — this is the cause in 90% of cases: **Settings** → **Apps** → `Recorder` → **Permissions** → enable everything",
                "**The version may not match** — double-check your EMUI version and try the other option (there are 2 files for EMUI 12)",
                "**Uninstall** the module, restart the phone, and install it **again**",
              ],
            },
          ],
        },
        {
          t: "details",
          summary:
            "The auto-recording menu is there, but the app can't get the recording",
          blocks: [
            {
              t: "p",
              text: "On some models the recording is saved to a **protected** area of the phone's storage that apps cannot access. In that case:",
            },
            {
              t: "list",
              items: [
                "Switch the recording mode to **All calls**",
                "If that doesn't help — you'll need to change the region (see the Samsung section)",
              ],
            },
          ],
        },
        {
          t: "details",
          summary: "It stopped working after a phone update",
          blocks: [
            {
              t: "p",
              text: "A system update can **revert** the region setting. Go through the guide **again**. On work phones we recommend disabling automatic updates.",
            },
          ],
        },
      ],
    },
  ],
};
