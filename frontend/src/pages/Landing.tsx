import { ArrowRight, BellRing, BookOpen, Check, Cpu, ExternalLink, Mail, ScanEye, Video } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { LogoMark, PRODUCT_NAME } from "../components/Brand";
import { CameraFrame } from "../components/CameraFrame";
import {
  AutoVideo,
  Chapter,
  ChapterIndex,
  DenseList,
  Flourish,
  Photo,
  PillLink,
  ROMAN,
  splitInitial,
  useScrollState,
  type ChapterInfo,
} from "../components/edition";
import { useAuth } from "../lib/auth";
import { bilingual, LanguageSwitch, useLang, useText } from "../lib/i18n";
import { CONSOLE_URL, IS_STATIC_SITE, useDemoStatus, type DemoStatus } from "../lib/site";

const P = PRODUCT_NAME;
type Pair = [string, string];
type Severity = "CRITICAL" | "HIGH" | "MEDIUM";
type TourKey = "signin" | "overview" | "cameras" | "incident" | "analytics" | "rules";
const TOUR_KEYS: TourKey[] = ["signin", "overview", "cameras", "incident", "analytics", "rules"];

// All of the page's text, English then Arabic (same shape; see lib/i18n.tsx).
const TEXT = bilingual(
  {
    docTitle: `${P} · Edge AI construction safety monitoring`,
    chapters: [
      { id: "ppe", title: "PPE" },
      { id: "smoking", title: "Smoking" },
      { id: "zones", title: "Zones" },
      { id: "alerts", title: "Alerts" },
      { id: "rules", title: "Your rules" },
      { id: "console", title: "Console" },
      { id: "edge", title: "On the edge" },
      { id: "regs", title: "The rulebook" },
    ] as ChapterInfo[],
    chaptersLabel: "Chapters",
    signIn: "Sign in",
    openConsole: "Open console",
    signInConsole: "Sign in to the console",
    demo: {
      checking: "Checking live demo…",
      online: "Live demo online",
      offline: "Live demo offline right now",
    } as Record<DemoStatus, string>,
    demoOfflineHint: "The console runs on the on-site device, which is switched off at the moment",
    tagline: "Construction safety",
    nav: { faq: "FAQ", team: "Team", tryIt: "Try it", regs: "Ask the regulations", results: "Results" },
    severity: { CRITICAL: "CRITICAL", HIGH: "HIGH", MEDIUM: "MEDIUM" } as Record<Severity, string>,
    hero: {
      line1: "Every risk on site,",
      emphasis: "caught",
      line2: " as it happens.",
      lead: `${P} turns your site cameras into a safety officer that never looks away. Eight chapters, one safer site.`,
    },
    ppe: {
      title: "Hard hats & vests",
      kicker: "The basics, checked on every frame, by every camera.",
      leadTitle: "Nothing missed, nothing nagged",
      lead:
        "The detector finds every worker and checks for a hard hat and a high-visibility vest. An alert only fires once " +
        "something has been missing for a few seconds, so a hat lifted to wipe a brow doesn't page the supervisor.",
      cardTitle: "What the camera sees",
      card: "A stylised frame: each person, hard hat, vest and machine is boxed, and a worker without a hard hat is flagged in red.",
      stats: [
        ["2 rules", "Hard hat and vest are separate, so a site that doesn't need vests can switch just that one off."],
        ["~12 m", "Hard hats are reliably seen up to about 12 metres from the reference camera."],
      ] as Pair[],
      list: [
        ["Missing, not just absent", "A NO-Hardhat detection or no hard hat at all over the head both count, so it works in either case."],
        ["Grace for dropouts", "A detector blink shorter than a second doesn't restart the timer."],
        ["Zone-only PPE", "A PPE rule can apply to one zone only, such as the scaffold."],
        ["Who was missing what", "Each incident records which item was missing, and Analytics shows the most-missed item."],
      ] as Pair[],
    },
    smoking: {
      title: "Smoking",
      kicker: "Clear air around the fuel store and the gate.",
      leadTitle: "It watches the act, not the cigarette",
      lead:
        `A cigarette is too small to find reliably from across a site, so ${P} looks at each person instead: their head ` +
        "and upper body. A second model decides whether they are smoking (a cigarette, vape, pipe or shisha at the mouth, " +
        "or smoke coming out), only holding one, or neither. Only smoking raises an alert.",
      stats: [
        ["88.5%", "Of smokers found in held-out test photos."],
        ["98%", "Of its \"smoking\" answers are right."],
        ["0.6%", "Of non-smokers flagged by mistake. Construction workers in the test: none."],
      ] as Pair[],
      list: [
        ["Holding isn't smoking", "It was trained to tell a cigarette in the hand from one at the mouth, and on look-alikes such as drinking or a phone call."],
        ["Two seconds, not one frame", "Smoking has to be seen for two seconds before an alert fires."],
        ["Separate switch", "Smoking is its own rule. Sites that allow it switch it off in one click."],
        ["Approved actions", "The report suggests putting it out, checking for nearby fuel, and a toolbox-talk reminder."],
      ] as Pair[],
    },
    zones: {
      title: "Zones & machinery",
      kicker: "Keep out means keep out.",
      leadTitle: "Lines on the ground the camera can see",
      lead:
        `Draw zones around an excavation, under a crane or on a scaffold. ${P} knows where each person is standing ` +
        "and raises an alert on entry, on loitering, or when too many people are inside, and whenever someone gets too close to working machinery.",
      cases: [
        ["Restricted entry", "Anyone stepping into the excavation edge, straight away.", "HIGH"],
        ["Loitering", "Staying under the crane swing area for 30 seconds.", "MEDIUM"],
        ["Over capacity", "More than three workers on scaffold level 1.", "MEDIUM"],
        ["Machinery proximity", "A worker within half a body-height of a machine.", "CRITICAL"],
      ] as [string, string, Severity][],
      list: [
        ["Feet, not boxes", "A person is inside a zone when their feet are, so leaning over a barrier isn't entry."],
        ["Distance that scales", "Proximity is measured against the person's size in the image, so it works near and far."],
        ["Per camera", "Each zone belongs to one camera's view."],
        ["Your numbers", "Durations, capacity and severity can be changed per site in the console."],
      ] as Pair[],
    },
    alerts: {
      title: "Alerts & reports",
      kicker: "Seconds from the camera to the supervisor's phone.",
      leadTitle: "The report writes itself",
      lead:
        "When a rule fires, the incident appears on the console straight away, the supervisor gets an email with a snapshot " +
        "and a short clip, and a formal report is written by AI (Google Gemini) from the recorded facts only, with the regulation it breaks, ready for the safety record.",
      videoLabel: "The console overview as new incidents arrive",
      cardTitle: "Live, with no refresh",
      cardLink: "How alerts work",
      card: "The control room tells you the site's state in one sentence; new incidents slide into the live feed and the numbers count up.",
      reportLabel: "Incident report",
      reportTitle: "Person near machinery",
      summaryLabel: "Summary.",
      summary: "A person was detected within the exclusion distance of operating machinery for 2.1 seconds.",
      actions: [
        "Stop the machine and separate the worker from it immediately.",
        "Re-establish the exclusion zone around operating machinery.",
      ],
      emailed: "Emailed to the site supervisor · snapshot and clip attached",
      factualTitle: "Factual by design",
      factual: [
        "Uses only the facts recorded for the incident",
        "Recommends actions from the site's approved list",
        "Falls back to a fixed template if the AI is unavailable",
      ],
      list: [
        ["Evidence attached", "A snapshot of the moment the rule fired and a clip around it, saved with every incident."],
        ["No alert storms", "The same rule on the same camera isn't emailed again within a few minutes."],
        ["Desktop and sound", "High and critical incidents can pop up and chime on the supervisor's computer."],
        ["I'm on it, Done", "One tap says who is dealing with an incident and another closes it, so nothing is handled twice or forgotten."],
      ] as Pair[],
    },
    rules: {
      title: "Your site, your rules",
      kicker: "Every site is different. The rules should be too.",
      leadTitle: "Switch it off, or tune it",
      lead:
        "The site manager decides which rules apply. Switch off what doesn't matter on your site, change how serious a " +
        "violation is and how long it must last, and limit a rule to your working hours. Changes apply within seconds, with no restart.",
      videoLabel: "Switching the smoking rule off and on, then setting its working hours",
      cardTitle: "Safety rules page",
      cardLink: "Can we turn off rules?",
      card: "Switching smoking off and back on, then limiting it to Sunday to Thursday, 07:00 to 17:00. Changes apply within seconds.",
      stats: [
        ["6 controls", "On or off, severity, alert delay, repeat interval, capacity for crowded zones and working hours."],
        ["Sun–Thu", "Working hours in site time, including night shifts that run past midnight."],
      ] as Pair[],
      list: [
        ["Who changed what", "Each rule shows who last changed it and when."],
        ["Back to defaults", "One click returns a rule to the plugin's values."],
        ["Coming soon, shown honestly", "Rules that aren't ready yet are listed separately and can't be switched on."],
        ["Read-only viewers", "Viewers see the rules but can't change them."],
      ] as Pair[],
    },
    console: {
      title: "The console",
      kicker: "One place to see, act on and learn from every incident.",
      leadTitle: "Open it from any browser",
      lead:
        "Supervisors sign in from the site office or their phone. Roles keep it simple: managers run the site's rules and users, supervisors handle " +
        "incidents, and viewers can look but not change anything. Everyone picks which alerts reach their own inbox.",
      tabsLabel: "Console screens",
      tour: {
        signin: ["Sign in", "Each person signs in with their own account; roles decide what they can change."],
        overview: ["Overview", "The site's state in one sentence, the live camera, and what to handle first, each with its next step and one-tap buttons."],
        cameras: ["Live cameras", "Watch every camera live, and see where on site incidents happen most."],
        incident: ["Incident", "Each incident starts with what to do now and who is on it, then the snapshot, the clip and the AI report."],
        analytics: ["Analytics", "Patterns in plain sentences first, then the charts: the busiest hours, the riskiest zones, the gear most often missing."],
        rules: ["Safety rules", "Switch rules on and off, and set when each one applies and how serious it is."],
      } as Record<TourKey, Pair>,
      screenAlt: (label: string) => `${P} console: ${label}`,
      screensNote: "Screens from the running system, with test-mode data.",
    },
    edge: {
      title: "On the edge",
      kicker: "The video never has to leave the site.",
      leadTitle: "Built where the cameras are",
      lead:
        "Detection, rules and the console all run on a small computer on site. Only the text facts of an incident go to the AI " +
        "that writes the report, never images.",
      step: "Step",
      facts: ["1080p camera, 30 frames a second", "YOLO + TensorRT on an NVIDIA Jetson", "Zones, distances, time and working hours", "Photo, video clip and written report"],
      steps: [
        ["See", "A camera on site streams to an NVIDIA Jetson edge device, which analyses the video right there."],
        ["Detect", "YOLO models optimised with TensorRT find people, PPE and machinery in every frame, and check each person for smoking."],
        ["Decide", "The rule engine checks zones, distances, durations and working hours, so glimpses don't raise alarms."],
        ["Respond", "The incident is stored, the report is written and the supervisor is alerted with the evidence."],
      ] as Pair[],
      plugins: [
        ["Construction safety", "Available", "Hard hats, vests, restricted zones, scaffold capacity, crane swing areas, machinery proximity and smoking. Fall detection is next.", true],
        ["Healthcare", "In development", "The same platform with a plugin for hospital and care settings.", false],
      ] as [string, string, string, boolean][],
      list: [
        ["Plugins", "Each site type is one config file: its models, classes, zones, rules and report style."],
        ["Works offline", "Detection, rules and the local console keep working without internet; email and AI wait."],
        ["Standard cameras", "Any USB camera works. The reference setup is a 12 MP Arducam with a 6 mm lens."],
        ["The stack", "Jetson Orin Nano, YOLO11 + TensorRT, Redis Streams, FastAPI + PostgreSQL, Gemini or Claude, React."],
      ] as Pair[],
    },
    regs: {
      title: "The rulebook",
      kicker: "Every alert says which rule it breaks.",
      leadTitle: "Cited, word for word",
      lead:
        "Each incident report quotes the clause of the official code of practice that the safety rule enforces, with the " +
        "document, the clause number, the page and a link to the official PDF. The same clause is shown on the incident's page " +
        "in the console, and on each rule in Safety rules.",
      excerptLabel: "From an incident report",
      excerptTitle: "Worker without a hard hat",
      excerptHeading: "Regulation",
      excerptWhere: "OSHJ-CoP-02, clause 5.13 “Personal Protective Equipment”, page 16",
      excerptQuote:
        "The client shall ensure that the principal contractor provides adequate personal protective equipment to their employees. " +
        "… The minimum requirements include: … Safety helmets – Provide head protection from dropped objects which cannot be adequately controlled;",
      excerptPdf: "Official PDF",
      excerptCaptionTitle: "Added by the system, not the AI",
      excerptCaption:
        "The clause is put into the report by code after it is written, and the AI is told not to cite regulations itself, so a clause can't be made up.",
      stats: [
        ["10 / 11", "Construction rules that quote their clause. The eleventh, sleeping on site, has none, so it cites none."],
        ["2 codes", "Sharjah Prevention and Safety Authority codes of practice: construction management, and working at height."],
      ] as Pair[],
      companionKicker: "Companion project",
      companionTitle: "SiteSentry Regs",
      companionText:
        "Our assistant for construction-safety regulations. Ask in Arabic or English, for example “How high must a guard rail be?”, " +
        "and it answers from the official codes, citing the exact clause. It is where SiteSentry's citations come from.",
      companionStats: [
        ["95%", "of questions find the clause with the answer in the top 3 results"],
        ["42 / 43", "answers cite a clause that contains the answer"],
      ] as Pair[],
      companionButton: "Ask the regulations",
      companionCode: "Source code",
      list: [
        ["Checked by hand", "Each rule's clause was found with SiteSentry Regs, then read in full; only clauses that really cover the rule were kept."],
        ["In Arabic", "Arabic reports and the Arabic console use the code's Arabic headings, and say when the wording is quoted in English."],
        ["Offline", "The clauses are stored with the rules on site, so reports cite them even without internet."],
        ["In the console", "Safety rules shows each rule's clause; the exact wording and the official PDF are one click away."],
      ] as Pair[],
    },
    results: {
      title: "Measured, not promised",
      lead: "What the system does on its own test sets and on the Jetson on site. Each figure comes from a measurement written up in the project's documentation.",
      items: [
        ["0.85", "mAP50 of the hard hat and vest model on 82 held-out test images (0.84 after TensorRT on the Jetson)."],
        ["30 fps", "Live detection on the Jetson Orin Nano: 28 to 32 frames a second from a 30 fps camera, in 25 W mode."],
        ["98%", "Of the smoking model's “smoking” answers are right; it finds 88.5% of smokers, and flags 0.6% of non-smokers."],
        ["99%+", "Faces named right in a 40-person test, with no stranger named, down to faces 28 pixels wide."],
        ["0.1–0.3 s", "From the camera to the live view in a browser over the internet, at up to 20 pictures a second."],
        ["10 / 11", "Rules whose reports quote the official clause they enforce, word for word."],
      ] as Pair[],
      note: "The test sets are small and were made by the team, so these are checks of this system, not benchmark claims.",
    },
    faq: {
      title: "Questions, answered",
      lead: "The things site managers and safety officers ask first.",
      items: [
        ["Do I need special cameras?", "No. Any standard USB camera works, and the detector can also read a video file. The reference setup uses a 12 MP Arducam with a 6 mm lens, which reliably sees hard hats up to about 12 m away."],
        ["Does video leave the site?", "Video is analysed on the edge device on site. For each incident, a snapshot and a short clip are stored on site and attached to the supervisor's email. The AI that writes the report only receives the text facts of the incident, never images."],
        ["How do you avoid false alarms?", "Rules have minimum durations and grace periods: a hard hat has to be missing for several seconds, not one frame, before an alert fires. Repeats of the same rule on the same camera are held back for a few minutes."],
        ["Can we turn off rules we don't need?", "Yes. The site manager can switch any rule off or back on from the console, with no restart, for example if smoking is allowed on your site. Each rule can also be limited to working hours, given a different severity, or set to wait longer before alerting. The console shows who changed what and when."],
        ["How far away can it spot smoking?", "It looks at each person rather than at the cigarette, so what matters is how large the person appears: the closer and clearer, the better. It's best on a camera covering a no-smoking area, such as a fuel store or a site entrance. We are measuring the exact range on site."],
        ["Can the AI report make things up?", "It's instructed to use only the fields recorded for the incident, never to invent causes or names, and to write NOT SPECIFIED when something is missing. Recommended actions come from the site's own approved list. If the AI is unavailable, a fixed template is used instead."],
        ["Which regulations does it cite?", "The Sharjah Prevention and Safety Authority's codes of practice for construction management (OSHJ-CoP-02) and working at height (OSHJ-CoP-04). Each rule's clause was found with our companion assistant, SiteSentry Regs, and checked by hand. A site that follows other regulations changes the clauses in its plugin."],
        ["Does it recognise who it is?", "Only if the site wants it to. A manager adds a few photos of each person on the console's People page; the cameras then name those people, and everyone else stays “unknown”. The photos are kept on the device on site, and a name is shown as an automatic identification to confirm, not as a fact."],
        ["Can it watch several cameras?", "Yes. One edge device watches several cameras with the same models, and each camera has its own zones. The console shows them side by side, and each incident says which camera saw it."],
        ["What happens if the internet goes down?", "Detection, the rules and the local console keep working, because they all run on site. Alert emails wait and are sent automatically once the connection is back (retried for up to a day), so none are lost. Without the AI, reports fall back to the template."],
        ["How does a supervisor deal with an incident?", "The console's front page lists what to handle first, each with the next step from the site's approved list. One tap on “I'm on it” tells everyone who is dealing with it, and “Done” closes it. Repeats of the same thing are grouped, so they can be closed together."],
        ["Is it only for construction?", "No. Each type of site is a plugin with its own model, zones, rules and report style. Construction is the first plugin; healthcare is in development."],
        ["Who can see the console?", "Only people with an account. Managers add users and choose their role: manager (rules and users), supervisor (handles incidents) or viewer (read-only)."],
      ] as Pair[],
    },
    team: {
      title: "A graduation project, built like a product",
      lead: (university: string) =>
        `${P} is a fifth-year computer engineering capstone at ${university}: real-time edge AI safety monitoring with ` +
        "configurable plugin rules and generative incident reporting, built over two semesters.",
      supervisedBy: "Supervised by",
      theTeam: "The team",
      university: "Misr University for Science & Technology",
      supervisor: "Dr. Mahmoud Sayed Kamel Hassan",
      members: [
        { name: "Albaraa Waheed Farag", role: "Team lead" },
        { name: "Youssef Hazem Mohammed" },
        { name: "Youssef Mohammed Nofal" },
        { name: "Omar Ahmed Abdelnabi" },
        { name: "Abdullah Mohammed Attia" },
        { name: "Ebtsam Mohamed Hassan" },
        { name: "Hassan Salah Eldien Hassan" },
      ] as { name: string; role?: string }[],
    },
    closing: { line: "See your site ", emphasis: "live." },
    companionFooter: "Companion project: SiteSentry Regs, construction-safety regulations with cited clauses",
    credits: (names: string) =>
      `Photos from Unsplash by ${names}. Console screens and recordings are from the running system in test mode.`,
  },
  {
    docTitle: `${P} · مراقبة سلامة مواقع البناء بالذكاء الاصطناعي في الموقع`,
    chapters: [
      { id: "ppe", title: "معدات الوقاية" },
      { id: "smoking", title: "التدخين" },
      { id: "zones", title: "المناطق" },
      { id: "alerts", title: "التنبيهات" },
      { id: "rules", title: "قواعدك" },
      { id: "console", title: "لوحة التحكم" },
      { id: "edge", title: "في الموقع" },
      { id: "regs", title: "اللوائح" },
    ],
    chaptersLabel: "الفصول",
    signIn: "تسجيل الدخول",
    openConsole: "فتح لوحة التحكم",
    signInConsole: "الدخول إلى لوحة التحكم",
    demo: {
      checking: "جارٍ التحقق من العرض المباشر…",
      online: "العرض المباشر متاح",
      offline: "العرض المباشر غير متاح الآن",
    },
    demoOfflineHint: "تعمل لوحة التحكم على جهاز الموقع، وهو مطفأ حاليًا",
    tagline: "سلامة مواقع البناء",
    nav: { faq: "الأسئلة الشائعة", team: "الفريق", tryIt: "جرّبه", regs: "اسأل اللوائح", results: "النتائج" },
    severity: { CRITICAL: "حرج", HIGH: "مرتفع", MEDIUM: "متوسط" },
    hero: {
      line1: "كل خطر في الموقع،",
      emphasis: "يُرصد",
      line2: " لحظة حدوثه.",
      lead: `يحوّل ${P} كاميرات موقعك إلى مسؤول سلامة لا يغفل لحظة. ثمانية فصول، وموقع أكثر أمانًا.`,
    },
    ppe: {
      title: "الخوذات والسترات",
      kicker: "الأساسيات، تُفحص في كل إطار وبكل كاميرا.",
      leadTitle: "لا شيء يفوت، ولا إزعاج بلا داعٍ",
      lead:
        "يتعرّف النظام على كل عامل ويتحقق من ارتدائه الخوذة والسترة العاكسة. ولا يُطلق التنبيه إلا إذا استمر غياب " +
        "أحدهما بضع ثوانٍ، فرفعُ الخوذة لمسح العرق لا يستدعي المشرف.",
      cardTitle: "ما تراه الكاميرا",
      card: "إطار توضيحي: يُحاط كل شخص وخوذة وسترة وآلة بمربع، ويُميَّز العامل الذي لا يرتدي خوذة باللون الأحمر.",
      stats: [
        ["قاعدتان", "الخوذة والسترة قاعدتان منفصلتان، فيمكن للموقع الذي لا يحتاج إلى السترات إيقاف قاعدتها وحدها."],
        ["~12 م", "تُرصد الخوذات بثقة حتى نحو 12 مترًا من الكاميرا المرجعية."],
      ],
      list: [
        ["الغياب بأي شكل", "يُحتسب رصدُ رأسٍ بلا خوذة، أو عدمُ وجود خوذة فوق الرأس أصلًا، فيعمل في الحالتين."],
        ["مهلة للانقطاعات", "انقطاع الرصد لأقل من ثانية لا يُعيد العدّاد من البداية."],
        ["قاعدة لمنطقة بعينها", "يمكن قصر قاعدة معدات الوقاية على منطقة واحدة، كالسقالة."],
        ["ما الذي كان ناقصًا", "تسجّل كل حادثة العنصر الناقص، وتعرض صفحة التحليلات أكثر العناصر غيابًا."],
      ],
    },
    smoking: {
      title: "التدخين",
      kicker: "هواء نقي حول مخزن الوقود والبوابة.",
      leadTitle: "يراقب فعل التدخين لا السيجارة",
      lead:
        `السيجارة أصغر من أن تُرصد بدقة من بعيد، لذلك ينظر ${P} إلى كل شخص بدلًا منها: رأسه والجزء العلوي من جسمه. ` +
        "ويحدّد نموذج ثانٍ هل يدخّن (سيجارة أو سيجارة إلكترونية أو غليون أو شيشة عند الفم، أو دخان يخرج منه)، " +
        "أم يحملها فقط، أم لا هذا ولا ذاك. ولا يُطلق التنبيه إلا عند التدخين.",
      stats: [
        ["88.5%", "من المدخنين رُصدوا في صور اختبار لم تُستخدم في التدريب."],
        ["98%", "من إجاباته «يدخّن» صحيحة."],
        ["0.6%", "من غير المدخنين يُنبَّه عليهم خطأً. ولم يُنبَّه على أي عامل بناء في الاختبار."],
      ],
      list: [
        ["الحمل ليس تدخينًا", "دُرّب على التمييز بين سيجارة في اليد وأخرى عند الفم، وعلى حالات مشابهة مثل الشرب أو مكالمة هاتفية."],
        ["ثانيتان لا إطار واحد", "يجب أن يُرى التدخين ثانيتين قبل إطلاق التنبيه."],
        ["مفتاح مستقل", "التدخين قاعدة مستقلة، ويمكن للمواقع التي تسمح به إيقافها بنقرة واحدة."],
        ["إجراءات معتمدة", "يقترح التقرير إطفاءها، والتحقق من عدم وجود وقود قريب، والتذكير بالأمر في اجتماع السلامة."],
      ],
    },
    zones: {
      title: "المناطق والآليات",
      kicker: "ممنوع الدخول يعني ممنوع الدخول.",
      leadTitle: "خطوط على الأرض تراها الكاميرا",
      lead:
        `حدّد مناطق حول حفرة أو تحت رافعة أو على سقالة. يعرف ${P} أين يقف كل شخص، ويُطلق تنبيهًا عند الدخول ` +
        "أو البقاء طويلًا أو تجاوز العدد المسموح، وكلما اقترب أحد أكثر من اللازم من آلة تعمل.",
      cases: [
        ["دخول منطقة محظورة", "أي شخص يدخل حافة الحفرة، فورًا.", "HIGH"],
        ["البقاء طويلًا", "البقاء تحت نطاق دوران الرافعة 30 ثانية.", "MEDIUM"],
        ["تجاوز العدد المسموح", "أكثر من ثلاثة عمال على المستوى الأول من السقالة.", "MEDIUM"],
        ["الاقتراب من الآليات", "عامل على مسافة أقل من نصف طول جسمه من آلة.", "CRITICAL"],
      ],
      list: [
        ["القدمان لا المربع", "يُعد الشخص داخل المنطقة إذا كانت قدماه داخلها، فالانحناء فوق الحاجز لا يُعد دخولًا."],
        ["مسافة تتناسب مع الحجم", "تُقاس المسافة نسبةً إلى حجم الشخص في الصورة، فتعمل القاعدة قريبًا وبعيدًا."],
        ["لكل كاميرا مناطقها", "تتبع كل منطقة مجال رؤية كاميرا واحدة."],
        ["أرقامك أنت", "يمكن تغيير المدد والسعة ودرجة الخطورة لكل موقع من لوحة التحكم."],
      ],
    },
    alerts: {
      title: "التنبيهات والتقارير",
      kicker: "ثوانٍ من الكاميرا إلى هاتف المشرف.",
      leadTitle: "التقرير يكتب نفسه",
      lead:
        "عند تحقق قاعدة، تظهر الحادثة فورًا في لوحة التحكم، ويتلقى المشرف بريدًا إلكترونيًا فيه لقطة ومقطع قصير، " +
        "ويكتب الذكاء الاصطناعي (Google Gemini) تقريرًا رسميًا من الوقائع المسجلة فقط، مع اللائحة المخالَفة، جاهزًا لسجل السلامة.",
      videoLabel: "لوحة التحكم مع وصول حوادث جديدة",
      cardTitle: "مباشر، دون تحديث الصفحة",
      cardLink: "كيف تعمل التنبيهات",
      card: "تلخّص غرفة التحكم حالة الموقع في جملة واحدة، وتنزلق الحوادث الجديدة إلى البث المباشر وتتصاعد الأرقام.",
      reportLabel: "تقرير حادثة",
      reportTitle: "شخص قرب آلة",
      summaryLabel: "الملخص.",
      summary: "رُصد شخص داخل مسافة الحظر حول آلة تعمل لمدة 2.1 ثانية.",
      actions: ["أوقف الآلة وأبعد العامل عنها فورًا.", "أعد تحديد منطقة الحظر حول الآلات العاملة."],
      emailed: "أُرسل إلى مشرف الموقع بالبريد · مع اللقطة والمقطع",
      factualTitle: "وقائع فقط، عن قصد",
      factual: [
        "يستخدم الوقائع المسجلة للحادثة فقط",
        "يوصي بإجراءات من القائمة المعتمدة للموقع",
        "يلجأ إلى نموذج ثابت إذا تعذّر الوصول إلى الذكاء الاصطناعي",
      ],
      list: [
        ["الأدلة مرفقة", "لقطة للحظة تحقق القاعدة ومقطع حولها، محفوظان مع كل حادثة."],
        ["لا سيل من التنبيهات", "لا يُرسل بريد عن القاعدة نفسها على الكاميرا نفسها مرة أخرى خلال بضع دقائق."],
        ["إشعار وصوت", "يمكن أن تظهر الحوادث المرتفعة والحرجة إشعارًا مع صوت على حاسوب المشرف."],
        ["أتولّى الأمر، تم", "ضغطة تُعلم الجميع بمن يتعامل مع الحادثة وأخرى تغلقها، فلا يُعالج شيء مرتين ولا يُنسى."],
      ],
    },
    rules: {
      title: "موقعك، قواعدك",
      kicker: "كل موقع مختلف، وكذلك ينبغي أن تكون قواعده.",
      leadTitle: "أوقفها أو اضبطها",
      lead:
        "يقرر مدير الموقع القواعد المطبَّقة. أوقف ما لا يهم موقعك، وغيّر درجة خطورة المخالفة والمدة التي يجب أن " +
        "تستمرها، وقصّر القاعدة على ساعات العمل. تُطبَّق التغييرات خلال ثوانٍ، دون إعادة تشغيل.",
      videoLabel: "إيقاف قاعدة التدخين وتشغيلها، ثم ضبط ساعات عملها",
      cardTitle: "صفحة قواعد السلامة",
      cardLink: "هل يمكن إيقاف القواعد؟",
      card: "إيقاف قاعدة التدخين ثم إعادة تشغيلها، ثم قصرها على الأحد إلى الخميس من 07:00 إلى 17:00. تُطبَّق التغييرات خلال ثوانٍ.",
      stats: [
        ["6 إعدادات", "التشغيل والإيقاف، ودرجة الخطورة، ومهلة التنبيه، وفترة التكرار، وسعة المناطق المزدحمة، وساعات العمل."],
        ["الأحد–الخميس", "ساعات العمل بتوقيت الموقع، بما فيها الورديات الليلية التي تمتد بعد منتصف الليل."],
      ],
      list: [
        ["من غيّر ماذا", "تعرض كل قاعدة آخر من غيّرها ومتى."],
        ["العودة إلى الافتراضي", "نقرة واحدة تُعيد القاعدة إلى قيمها الأصلية في الإضافة."],
        ["«قريبًا» بوضوح", "القواعد غير الجاهزة بعدُ تظهر منفصلة ولا يمكن تشغيلها."],
        ["مشاهدون للقراءة فقط", "يرى المشاهدون القواعد لكن لا يمكنهم تغييرها."],
      ],
    },
    console: {
      title: "لوحة التحكم",
      kicker: "مكان واحد لرؤية كل حادثة والتصرف حيالها والتعلم منها.",
      leadTitle: "افتحها من أي متصفح",
      lead:
        "يدخل المشرفون من مكتب الموقع أو من هواتفهم. والأدوار بسيطة: المديرون يديرون قواعد الموقع ومستخدميه، والمشرفون يتعاملون " +
        "مع الحوادث، والمشاهدون يطّلعون دون تغيير أي شيء. ويختار كلٌّ منهم التنبيهات التي تصل إلى بريده.",
      tabsLabel: "شاشات لوحة التحكم",
      tour: {
        signin: ["تسجيل الدخول", "يدخل كل شخص بحسابه الخاص، وتحدد الأدوار ما يمكنه تغييره."],
        overview: ["نظرة عامة", "حالة الموقع في جملة واحدة، والكاميرا المباشرة، وما يجب البدء به مع الخطوة التالية وأزرار بضغطة واحدة."],
        cameras: ["الكاميرات المباشرة", "شاهد كل كاميرا مباشرةً، واعرف أين تقع الحوادث أكثر في الموقع."],
        incident: ["الحادثة", "تبدأ كل حادثة بما يجب عمله الآن ومن يتولّاها، ثم اللقطة والمقطع وتقرير الذكاء الاصطناعي."],
        analytics: ["التحليلات", "الأنماط بجمل واضحة أولًا ثم الرسوم: أكثر الساعات ازدحامًا، وأخطر المناطق، والمعدات الأكثر نقصًا."],
        rules: ["قواعد السلامة", "شغّل القواعد وأوقفها، وحدد متى تُطبَّق كل قاعدة ومدى خطورتها."],
      },
      screenAlt: (label: string) => `لوحة تحكم ${P}: ${label}`,
      screensNote: "الشاشات من النظام أثناء تشغيله، ببيانات وضع الاختبار.",
    },
    edge: {
      title: "في الموقع",
      kicker: "لا حاجة لأن يغادر الفيديو الموقع أبدًا.",
      leadTitle: "مبني حيث توجد الكاميرات",
      lead:
        "يعمل الرصد والقواعد ولوحة التحكم كلها على حاسوب صغير في الموقع. ولا يُرسل إلى الذكاء الاصطناعي الذي يكتب " +
        "التقرير إلا الوقائع النصية للحادثة، ولا صور أبدًا.",
      step: "الخطوة",
      facts: ["كاميرا 1080p بمعدل 30 إطارًا في الثانية", "YOLO وTensorRT على NVIDIA Jetson", "المناطق والمسافات والوقت وساعات العمل", "صورة ومقطع فيديو وتقرير مكتوب"],
      steps: [
        ["الرؤية", "تبث كاميرا في الموقع إلى جهاز طرفي من NVIDIA Jetson يحلل الفيديو في مكانه."],
        ["الرصد", "نماذج YOLO مُسرَّعة بـ TensorRT تجد الأشخاص ومعدات الوقاية والآليات في كل إطار، وتتحقق من كل شخص هل يدخّن."],
        ["القرار", "يفحص محرك القواعد المناطق والمسافات والمدد وساعات العمل، فلا تُطلق اللمحات العابرة إنذارات."],
        ["الاستجابة", "تُحفظ الحادثة ويُكتب التقرير ويُنبَّه المشرف مع الأدلة."],
      ],
      plugins: [
        ["سلامة مواقع البناء", "متاح", "الخوذات والسترات والمناطق المحظورة وسعة السقالات ونطاق دوران الرافعات والاقتراب من الآليات والتدخين. ورصد السقوط هو التالي.", true],
        ["الرعاية الصحية", "قيد التطوير", "المنصة نفسها مع إضافة للمستشفيات ومراكز الرعاية.", false],
      ],
      list: [
        ["الإضافات", "كل نوع من المواقع ملف إعدادات واحد: نماذجه وفئاته ومناطقه وقواعده وأسلوب تقاريره."],
        ["يعمل دون إنترنت", "يستمر الرصد والقواعد ولوحة التحكم المحلية دون إنترنت، وينتظر البريد والذكاء الاصطناعي عودته."],
        ["كاميرات عادية", "تعمل أي كاميرا USB. والإعداد المرجعي كاميرا Arducam بدقة 12 ميجابكسل وعدسة 6 مم."],
        ["التقنيات", "Jetson Orin Nano، وYOLO11 + TensorRT، وRedis Streams، وFastAPI + PostgreSQL، وGemini أو Claude، وReact."],
      ],
    },
    regs: {
      title: "اللوائح",
      kicker: "كل تنبيه يذكر القاعدة التي خالفها.",
      leadTitle: "مُقتبسة بنصّها الحرفي",
      lead:
        "يقتبس كل تقرير حادثة البند الذي تطبّقه قاعدة السلامة من دليل الممارسة الرسمي، مع اسم الوثيقة ورقم البند والصفحة " +
        "ورابط الملف الرسمي. ويظهر البند نفسه في صفحة الحادثة في لوحة التحكم، وعلى كل قاعدة في صفحة قواعد السلامة.",
      excerptLabel: "من تقرير حادثة",
      excerptTitle: "عامل بدون خوذة",
      excerptHeading: "اللائحة",
      excerptWhere: "OSHJ-CoP-02، البند 5.13 «Personal Protective Equipment»، صفحة 16",
      excerptQuote:
        "The client shall ensure that the principal contractor provides adequate personal protective equipment to their employees. " +
        "… The minimum requirements include: … Safety helmets – Provide head protection from dropped objects which cannot be adequately controlled;",
      excerptPdf: "الملف الرسمي",
      excerptCaptionTitle: "يضيفه النظام لا الذكاء الاصطناعي",
      excerptCaption:
        "يُضاف البند إلى التقرير برمجيًا بعد كتابته، ويُطلب من الذكاء الاصطناعي ألا يذكر اللوائح بنفسه، فلا يمكن اختلاق بند. النص الأصلي بالإنجليزية.",
      stats: [
        ["10 / 11", "من قواعد البناء تقتبس بندها. أما الحادية عشرة، النوم في الموقع، فلا بند لها، فلا تقتبس شيئًا."],
        ["دليلان", "دليلا ممارسة من هيئة الوقاية والسلامة بالشارقة: إدارة السلامة في البناء، والعمل في الأماكن المرتفعة."],
      ] as Pair[],
      companionKicker: "مشروع مرافق",
      companionTitle: "SiteSentry Regs",
      companionText:
        "مساعدنا للوائح السلامة في البناء. اسأل بالعربية أو الإنجليزية، مثل «ما الارتفاع المطلوب لدرابزين الحماية؟»، " +
        "فيجيب من الأدلة الرسمية ويذكر البند بدقة. ومنه تأتي البنود التي يقتبسها SiteSentry.",
      companionStats: [
        ["95%", "من الأسئلة يجد البند الذي فيه الإجابة ضمن أول 3 نتائج"],
        ["42 / 43", "إجابة تذكر بندًا يحتوي على الإجابة"],
      ] as Pair[],
      companionButton: "اسأل اللوائح",
      companionCode: "الشيفرة المصدرية",
      list: [
        ["مُراجَعة يدويًا", "وُجد بند كل قاعدة باستخدام SiteSentry Regs ثم قُرئ كاملًا، ولم يُحتفظ إلا بالبنود التي تغطي القاعدة فعلًا."],
        ["بالعربية", "تستخدم التقارير ولوحة التحكم بالعربية عناوين الدليل العربية، وتوضّح متى يكون النص مقتبسًا بالإنجليزية."],
        ["دون إنترنت", "البنود محفوظة مع القواعد في الموقع، فتقتبسها التقارير حتى دون اتصال."],
        ["في لوحة التحكم", "تعرض صفحة قواعد السلامة بند كل قاعدة، والنص الحرفي والملف الرسمي على بُعد نقرة."],
      ] as Pair[],
    },
    results: {
      title: "نتائج مقيسة لا وعود",
      lead: "ما يحققه النظام على مجموعات الاختبار الخاصة به وعلى جهاز Jetson في الموقع. كل رقم من قياس موثّق في وثائق المشروع.",
      items: [
        ["0.85", "دقة mAP50 لنموذج الخوذة والسترة على 82 صورة اختبار لم تُستخدم في التدريب (0.84 بعد TensorRT على Jetson)."],
        ["30 fps", "رصد مباشر على Jetson Orin Nano: من 28 إلى 32 إطارًا في الثانية من كاميرا بمعدل 30، في وضع 25 واط."],
        ["98%", "من إجابات نموذج التدخين «يدخّن» صحيحة، ويرصد 88.5% من المدخنين، وينبّه خطأً على 0.6% من غير المدخنين."],
        ["99%+", "من الوجوه سُمّيت صحيحًا في اختبار من 40 شخصًا، دون تسمية أي غريب، حتى وجوه بعرض 28 بكسل."],
        ["0.1–0.3 ث", "من الكاميرا إلى البث المباشر في المتصفح عبر الإنترنت، بمعدل يصل إلى 20 صورة في الثانية."],
        ["10 / 11", "قاعدة تقتبس تقاريرها بند اللائحة الرسمي الذي تطبّقه، بنصّه الحرفي."],
      ] as Pair[],
      note: "مجموعات الاختبار صغيرة وأعدّها الفريق، فهذه فحوص لهذا النظام لا ادعاءات مقارنة معيارية.",
    },
    faq: {
      title: "أسئلة وإجابات",
      lead: "أول ما يسأل عنه مديرو المواقع ومسؤولو السلامة.",
      items: [
        ["هل أحتاج إلى كاميرات خاصة؟", "لا. تعمل أي كاميرا USB عادية، ويمكن للنظام أيضًا قراءة ملف فيديو. يستخدم الإعداد المرجعي كاميرا Arducam بدقة 12 ميجابكسل وعدسة 6 مم، ترصد الخوذات بثقة حتى نحو 12 مترًا."],
        ["هل يغادر الفيديو الموقع؟", "يُحلَّل الفيديو على الجهاز الطرفي في الموقع. ولكل حادثة تُحفظ لقطة ومقطع قصير في الموقع ويُرفقان ببريد المشرف. أما الذكاء الاصطناعي الذي يكتب التقرير فلا يتلقى إلا الوقائع النصية للحادثة، ولا صور أبدًا."],
        ["كيف تتجنبون الإنذارات الكاذبة؟", "للقواعد مدد دنيا وفترات سماح: يجب أن تغيب الخوذة عدة ثوانٍ، لا إطارًا واحدًا، قبل إطلاق التنبيه. وتُؤجَّل تكرارات القاعدة نفسها على الكاميرا نفسها بضع دقائق."],
        ["هل يمكننا إيقاف القواعد التي لا نحتاج إليها؟", "نعم. يستطيع مدير الموقع إيقاف أي قاعدة أو إعادة تشغيلها من لوحة التحكم دون إعادة تشغيل النظام، مثلًا إذا كان التدخين مسموحًا في موقعكم. ويمكن أيضًا قصر كل قاعدة على ساعات العمل، أو تغيير درجة خطورتها، أو جعلها تنتظر مدة أطول قبل التنبيه. وتعرض لوحة التحكم من غيّر ماذا ومتى."],
        ["من أي مسافة يمكنه رصد التدخين؟", "ينظر إلى كل شخص لا إلى السيجارة، لذلك المهم هو حجم الشخص في الصورة: كلما كان أقرب وأوضح كان أفضل. ويكون أفضل على كاميرا تغطي منطقة يُمنع فيها التدخين، مثل مخزن وقود أو مدخل الموقع. ونقيس المدى الدقيق حاليًا في الموقع."],
        ["هل يمكن أن يختلق تقرير الذكاء الاصطناعي معلومات؟", "يُطلب منه استخدام الحقول المسجلة للحادثة فقط، وعدم اختلاق أسباب أو أسماء أبدًا، وكتابة «غير محدد» عند غياب معلومة. وتأتي الإجراءات الموصى بها من القائمة المعتمدة للموقع. وإذا تعذّر الوصول إلى الذكاء الاصطناعي يُستخدم نموذج ثابت بدلًا منه."],
        ["ما اللوائح التي يقتبسها؟", "أدلة الممارسة الصادرة عن هيئة الوقاية والسلامة بالشارقة لإدارة السلامة في البناء (OSHJ-CoP-02) والعمل في الأماكن المرتفعة (OSHJ-CoP-04). وُجد بند كل قاعدة باستخدام مساعدنا المرافق SiteSentry Regs ثم رُوجع يدويًا. والموقع الذي يتبع لوائح أخرى يغيّر البنود في ملف الإضافة الخاص به."],
        ["هل يتعرّف على الأشخاص؟", "فقط إذا أراد الموقع ذلك. يضيف المدير بضع صور لكل شخص من صفحة الأشخاص في لوحة التحكم، فتسمّي الكاميرات هؤلاء الأشخاص ويبقى غيرهم «غير معروف». وتُحفظ الصور على الجهاز في الموقع، ويُعرض الاسم تعرّفًا تلقائيًا يحتاج إلى تأكيد لا حقيقة مؤكدة."],
        ["هل يراقب عدة كاميرات؟", "نعم. يراقب جهاز واحد في الموقع عدة كاميرات بالنماذج نفسها، ولكل كاميرا مناطقها. وتعرضها لوحة التحكم جنبًا إلى جنب، وتذكر كل حادثة الكاميرا التي رصدتها."],
        ["ماذا يحدث إذا انقطع الإنترنت؟", "يستمر الرصد والقواعد ولوحة التحكم المحلية في العمل، لأنها كلها تعمل في الموقع. وتنتظر رسائل التنبيه ثم تُرسل تلقائيًا فور عودة الاتصال (مع إعادة المحاولة لمدة تصل إلى يوم)، فلا يضيع منها شيء. ودون الذكاء الاصطناعي تُكتب التقارير بالنموذج الثابت."],
        ["كيف يتعامل المشرف مع الحادثة؟", "تعرض الصفحة الأولى في لوحة التحكم ما يجب البدء به، ومع كل حادثة الخطوة التالية من قائمة الموقع المعتمدة. ضغطة واحدة على «أتولّى الأمر» تُعلم الجميع بمن يتعامل معها، و«تم» تغلقها. وتُجمع الحوادث المتكررة معًا ليمكن إغلاقها دفعة واحدة."],
        ["هل هو لمواقع البناء فقط؟", "لا. كل نوع من المواقع إضافة لها نموذجها ومناطقها وقواعدها وأسلوب تقاريرها. مواقع البناء هي الإضافة الأولى، والرعاية الصحية قيد التطوير."],
        ["من يمكنه رؤية لوحة التحكم؟", "أصحاب الحسابات فقط. يضيف المديرون المستخدمين ويختارون أدوارهم: مدير (القواعد والمستخدمون)، أو مشرف (يتعامل مع الحوادث)، أو مشاهد (للقراءة فقط)."],
      ],
    },
    team: {
      title: "مشروع تخرج بُني كمنتج",
      lead: (university: string) =>
        `${P} مشروع تخرج للسنة الخامسة في هندسة الحاسبات في ${university}: مراقبة فورية للسلامة بالذكاء الاصطناعي ` +
        "على جهاز طرفي، بقواعد قابلة للضبط عبر الإضافات وتقارير حوادث يكتبها الذكاء الاصطناعي، أُنجز على مدى فصلين دراسيين.",
      supervisedBy: "بإشراف",
      theTeam: "الفريق",
      university: "جامعة مصر للعلوم والتكنولوجيا",
      supervisor: "د. محمود سيد كامل حسن",
      members: [
        { name: "البراء وحيد فرج", role: "قائد الفريق" },
        { name: "يوسف حازم محمد" },
        { name: "يوسف محمد نوفل" },
        { name: "عمر أحمد عبد النبي" },
        { name: "عبد الله محمد عطية" },
        { name: "ابتسام محمد حسن" },
        { name: "حسن صلاح الدين حسن" },
      ],
    },
    closing: { line: "شاهد موقعك ", emphasis: "مباشرةً." },
    companionFooter: "مشروع مرافق: SiteSentry Regs، لوائح السلامة في البناء مع ذكر البنود",
    credits: (names: string) =>
      `الصور من Unsplash بعدسة ${names}. شاشات لوحة التحكم وتسجيلاتها من النظام أثناء تشغيله في وضع الاختبار.`,
  },
);

function ConsoleButton({ className = "", children }: { className?: string; children?: ReactNode }) {
  const { user } = useAuth();
  const t = useText(TEXT);
  const classes = `inline-flex items-center justify-center gap-2 rounded-full font-semibold transition ${className}`;
  // the static product page links out to the console's own address
  if (IS_STATIC_SITE) {
    return (
      <a href={`${CONSOLE_URL}/login`} className={classes}>
        {children ?? t.signIn}
      </a>
    );
  }
  return (
    <Link to={user ? "/app" : "/login"} className={classes}>
      {children ?? (user ? t.openConsole : t.signIn)}
    </Link>
  );
}

const DEMO_DOT: Record<DemoStatus, string> = {
  checking: "bg-slate-400",
  online: "bg-emerald-400",
  offline: "bg-slate-500",
};

function DemoBadge({ dark = true }: { dark?: boolean }) {
  const status = useDemoStatus();
  const t = useText(TEXT);
  const dot = DEMO_DOT[status];
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 ${
        dark ? "bg-black/30 text-paper ring-white/15 backdrop-blur" : "bg-white/60 text-ink/70 ring-ink/10"
      }`}
      title={status === "offline" ? t.demoOfflineHint : undefined}
    >
      <span className="relative flex h-2 w-2">
        {status === "online" && <span className={`absolute h-2 w-2 animate-ping rounded-full ${dot} opacity-60`} />}
        <span className={`relative h-2 w-2 rounded-full ${dot}`} />
      </span>
      {t.demo[status]}
    </span>
  );
}

/** "Forward" arrow: points left in Arabic. */
function ForwardArrow() {
  return <ArrowRight className="flip-rtl h-4 w-4" />;
}

function TopBar({ surface }: { surface: "dark" | "light" }) {
  const onDark = surface === "dark";
  const t = useText(TEXT);
  return (
    <header data-overlay className="fixed inset-x-0 top-0 z-40">
      <div
        className={`flex h-16 items-center gap-6 px-5 transition-colors duration-300 sm:px-6 ${
          onDark ? "text-paper" : "bg-paper/80 text-ink backdrop-blur-md"
        }`}
      >
        <Link
          to="/"
          className="flex items-center gap-2.5"
          onClick={(e) => {
            // already on this page, so the link alone does nothing: go back to the start
            e.preventDefault();
            if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
            const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
          }}
        >
          <LogoMark className="h-7 w-7" />
          <span className="font-display text-[15px] font-semibold tracking-tight">{P}</span>
          <span className={`hidden font-display text-[15px] sm:inline ${onDark ? "text-paper/55" : "text-ink/45"}`}>
            {t.tagline}
          </span>
        </Link>
        <nav className="ms-auto hidden items-center gap-6 font-display text-sm md:flex">
          <a href="#try" className="opacity-80 hover:opacity-100">
            {t.nav.tryIt}
          </a>
          <a href="#results" className="opacity-80 hover:opacity-100">
            {t.nav.results}
          </a>
          <OutLink href={REGS_URL} className="inline-flex items-center gap-1 opacity-80 hover:opacity-100">
            {t.nav.regs} <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </OutLink>
          <a href="#faq" className="opacity-80 hover:opacity-100">
            {t.nav.faq}
          </a>
          <a href="#team" className="opacity-80 hover:opacity-100">
            {t.nav.team}
          </a>
        </nav>
        <div className="ms-auto flex items-center gap-2 md:ms-0">
          <LanguageSwitch
            className={onDark ? "text-paper/85 ring-1 ring-paper/30 hover:bg-white/10" : "text-ink/75 ring-1 ring-ink/15 hover:bg-ink/5"}
          />
          <ConsoleButton
            className={`px-4 py-2 text-sm ${onDark ? "bg-paper text-ink hover:bg-white" : "bg-ink text-paper hover:bg-black"}`}
          />
        </div>
      </div>
    </header>
  );
}

function Hero() {
  const t = useText(TEXT);
  return (
    <section className="relative h-[100svh] min-h-[640px] overflow-hidden bg-ink" data-surface="dark">
      <Photo name="hero" eager className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/50 via-black/10 to-black/60" aria-hidden />
      <div className="relative flex h-full items-center justify-center px-5 pt-16">
        {/* framed contents, like the title page of a printed edition */}
        <div className="w-full max-w-md border border-paper/50 bg-black/25 p-6 text-paper backdrop-blur-[2px] sm:p-8">
          <h1 className="font-display text-4xl leading-[0.95] font-semibold tracking-[-0.03em] sm:text-5xl">
            {t.hero.line1}
            <br />
            <span className="font-serif font-normal italic">{t.hero.emphasis}</span>
            {t.hero.line2}
          </h1>
          <p className="mt-8 font-serif text-xl leading-snug text-paper/90">{t.hero.lead}</p>
          <ol className="mt-6 space-y-0.5">
            {t.chapters.map((c, i) => (
              <li key={c.id}>
                <a href={`#${c.id}`} className="group flex items-baseline gap-2 font-display text-lg leading-tight font-semibold">
                  <span className="group-hover:text-amber-300">{c.title}</span>
                  <span className="mb-1 flex-1 border-b border-dotted border-transparent group-hover:border-paper/60" />
                  <span className="font-serif text-sm font-normal text-paper/70">{ROMAN[i]}</span>
                </a>
              </li>
            ))}
          </ol>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <ConsoleButton className="bg-amber-400 px-5 py-2.5 text-sm text-ink hover:bg-amber-300">
              {t.signInConsole} <ForwardArrow />
            </ConsoleButton>
            <a href="#try" className="rounded-full px-4 py-2.5 text-sm font-semibold text-paper ring-1 ring-paper/40 hover:bg-white/10">
              {t.nav.tryIt}
            </a>
            <DemoBadge />
          </div>
        </div>
      </div>
    </section>
  );
}

/** Text block that opens a chapter's content: serif initial headline, then a lead paragraph. */
function Lead({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="reveal max-w-3xl">
      <Flourish text={title} />
      <p className="mt-6 max-w-2xl text-lg leading-8 text-ink/70">{children}</p>
    </div>
  );
}

/** A card: media on top, a bold name and a short muted description under it. */
function Card({ media, title, children, link, className = "", bare = false }: {
  media: ReactNode;
  title: string;
  children: ReactNode;
  link?: [string, string];
  className?: string;
  bare?: boolean; // media draws its own frame (and may overflow it)
}) {
  return (
    <figure className={`reveal ${className}`}>
      {bare ? media : <div className="overflow-hidden rounded-md bg-ink/5 ring-1 ring-ink/10">{media}</div>}
      <figcaption className="mt-3">
        <p className="font-display font-semibold">{title}</p>
        <p className="mt-0.5 max-w-md text-[15px] leading-6 text-ink/60">{children}</p>
        {link && <PillLink href={link[1]}>{link[0]}</PillLink>}
      </figcaption>
    </figure>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="reveal border-t border-ink/20 pt-4">
      {/* figures read left to right in Arabic too, or "42 / 43" turns into "43 / 42" */}
      <p className="font-display text-5xl font-semibold tracking-tight sm:text-6xl">
        <bdi dir="ltr">{value}</bdi>
      </p>
      <p className="mt-2 max-w-[16rem] text-sm leading-6 text-ink/60">{label}</p>
    </div>
  );
}

function Stats({ items, className }: { items: Pair[]; className: string }) {
  return (
    <div className={className}>
      {items.map(([value, label]) => (
        <Stat key={value} value={value} label={label} />
      ))}
    </div>
  );
}

function PpeChapter() {
  const t = useText(TEXT).ppe;
  return (
    <Chapter id="ppe" n={1} title={t.title} kicker={t.kicker} photo="ppe">
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      <div className="mt-16 grid gap-10 xl:grid-cols-[1.4fr_1fr] xl:items-start">
        <Card media={<div className="px-4 pt-8 pb-10 sm:px-10"><CameraFrame /></div>} bare title={t.cardTitle}>
          {t.card}
        </Card>
        <Stats items={t.stats} className="grid gap-10 sm:grid-cols-2 xl:grid-cols-1" />
      </div>
      <DenseList items={t.list} />
    </Chapter>
  );
}

function SmokingChapter() {
  const t = useText(TEXT).smoking;
  return (
    <Chapter id="smoking" n={2} title={t.title} kicker={t.kicker} photo="smoking" focus="80% 50%">
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      <Stats items={t.stats} className="mt-16 grid gap-10 sm:grid-cols-3" />
      <DenseList items={t.list} />
    </Chapter>
  );
}

function ZonesChapter() {
  const all = useText(TEXT);
  const t = all.zones;
  return (
    <Chapter id="zones" n={3} title={t.title} kicker={t.kicker} photo="zones">
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      <div className="mt-16 grid gap-x-8 gap-y-12 md:grid-cols-2 xl:grid-cols-4">
        {t.cases.map(([title, text, severity]) => (
          <div key={title} className="reveal border-t border-ink/20 pt-4">
            <p className="font-display text-xs font-semibold tracking-widest text-amber-700">{all.severity[severity]}</p>
            <p className="mt-2 font-display text-2xl font-semibold tracking-tight">{title}</p>
            <p className="mt-2 text-[15px] leading-6 text-ink/60">{text}</p>
          </div>
        ))}
      </div>
      <DenseList items={t.list} />
    </Chapter>
  );
}

function AlertsChapter() {
  const all = useText(TEXT);
  const t = all.alerts;
  return (
    <Chapter id="alerts" n={4} title={t.title} kicker={t.kicker} photo="alerts">
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      <div className="mt-16 grid gap-10 xl:grid-cols-[1.35fr_1fr] xl:items-start">
        <Card media={<AutoVideo name="overview" label={t.videoLabel} />} title={t.cardTitle} link={[t.cardLink, "#faq"]}>
          {t.card}
        </Card>
        <figure className="reveal">
          <article className="rounded-md bg-white p-6 shadow-sm ring-1 ring-ink/10">
            <div className="flex items-center justify-between border-b border-ink/10 pb-4">
              <div>
                <p className="text-xs font-semibold tracking-wide text-ink/40 uppercase">{t.reportLabel}</p>
                <p className="mt-1 font-display font-semibold">{t.reportTitle}</p>
              </div>
              <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700">{all.severity.CRITICAL}</span>
            </div>
            <div className="space-y-3 pt-4 text-sm leading-6 text-ink/70">
              <p>
                <span className="font-semibold text-ink">{t.summaryLabel}</span> {t.summary}
              </p>
              <ol className="list-decimal space-y-1 ps-5">
                {t.actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ol>
            </div>
            <p className="mt-5 flex items-center gap-2 rounded bg-paper px-3 py-2 text-xs text-ink/60">
              <Mail className="h-4 w-4" /> {t.emailed}
            </p>
          </article>
          <figcaption className="mt-3">
            <p className="font-display font-semibold">{t.factualTitle}</p>
            <ul className="mt-2 space-y-1.5 text-[15px] leading-6 text-ink/60">
              {t.factual.map((line) => (
                <li key={line} className="flex gap-2">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-amber-700" /> {line}
                </li>
              ))}
            </ul>
          </figcaption>
        </figure>
      </div>
      <DenseList items={t.list} />
    </Chapter>
  );
}

function RulesChapter() {
  const t = useText(TEXT).rules;
  return (
    <Chapter id="rules" n={5} title={t.title} kicker={t.kicker} photo="rules">
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      <div className="mt-16 grid gap-10 xl:grid-cols-[1.35fr_1fr] xl:items-start">
        <Card media={<AutoVideo name="rules" label={t.videoLabel} />} title={t.cardTitle} link={[t.cardLink, "#faq"]}>
          {t.card}
        </Card>
        <Stats items={t.stats} className="grid gap-10 sm:grid-cols-2 xl:grid-cols-1" />
      </div>
      <DenseList items={t.list} />
    </Chapter>
  );
}

function ConsoleChapter() {
  const t = useText(TEXT).console;
  const { lang } = useLang();
  // screenshots of the console in the page's language
  const shots = lang === "ar" ? "/screenshots/ar" : "/screenshots";
  const [active, setActive] = useState<TourKey>("overview");
  return (
    <Chapter id="console" n={6} title={t.title} kicker={t.kicker} photo="console">
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      <div className="reveal mt-14 flex flex-wrap gap-2" role="tablist" aria-label={t.tabsLabel}>
        {TOUR_KEYS.map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={active === key}
            onClick={() => setActive(key)}
            className={`rounded-full px-4 py-2 font-display text-sm font-medium transition ${
              active === key ? "bg-ink text-paper" : "bg-ink/5 text-ink/70 hover:bg-ink/10"
            }`}
          >
            {t.tour[key][0]}
          </button>
        ))}
      </div>
      <figure className="reveal mt-6">
        <div className="overflow-hidden rounded-md shadow-2xl ring-1 ring-ink/10">
          {TOUR_KEYS.map((key) => (
            <img
              key={key}
              src={`${shots}/${key}.jpg`}
              alt={t.screenAlt(t.tour[key][0])}
              width={1440}
              height={900}
              loading="lazy"
              hidden={active !== key}
              className="block w-full"
            />
          ))}
        </div>
        <figcaption className="mt-3 text-[15px] text-ink/60">
          {t.tour[active][1]} <span className="text-ink/40">{t.screensNote}</span>
        </figcaption>
      </figure>
    </Chapter>
  );
}

const FLOW_ICONS = [Video, ScanEye, Cpu, BellRing];

function EdgeChapter() {
  const t = useText(TEXT).edge;
  return (
    <Chapter id="edge" n={7} title={t.title} kicker={t.kicker} photo="how">
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      {/* the four steps as one flow: a pulse travels along the line from the camera to the supervisor */}
      <div className="relative mt-16">
        <div className="absolute inset-x-[12.5%] top-7 hidden h-px bg-ink/15 xl:block" aria-hidden>
          <span className="flow-pulse absolute -top-[3px] h-[7px] w-[7px] rounded-full bg-amber-500 shadow-[0_0_12px_rgb(245_158_11/0.9)]" />
        </div>
        <ol className="grid gap-x-8 gap-y-10 md:grid-cols-2 xl:grid-cols-4">
          {t.steps.map(([title, text], i) => {
            const Icon = FLOW_ICONS[i];
            return (
              <li key={title} className="reveal relative xl:text-center">
                <span className="relative z-10 flex h-14 w-14 items-center justify-center rounded-full bg-ink text-amber-300 ring-8 ring-paper xl:mx-auto">
                  <Icon className="h-6 w-6" />
                </span>
                <p className="mt-4 font-serif text-lg text-amber-700 italic">
                  {t.step} {ROMAN[i]}
                </p>
                <p className="mt-1 font-display text-2xl font-semibold tracking-tight">{title}</p>
                <p className="mt-2 text-[15px] leading-6 text-ink/60">{text}</p>
                <p className="mt-3 inline-block rounded-full bg-ink/[0.06] px-3 py-1 text-xs font-semibold text-ink/70">{t.facts[i]}</p>
              </li>
            );
          })}
        </ol>
      </div>
      <div className="mt-16 grid gap-4 md:grid-cols-2">
        {t.plugins.map(([title, status, text, available]) => (
          <div key={title} className="reveal rounded-md bg-ink p-6 text-paper">
            <div className="flex items-center justify-between gap-4">
              <p className="font-display text-xl font-semibold">{title}</p>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  available ? "bg-emerald-400/15 text-emerald-300" : "bg-white/10 text-paper/70"
                }`}
              >
                {status}
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-paper/60">{text}</p>
          </div>
        ))}
      </div>
      <DenseList items={t.list} />
    </Chapter>
  );
}

function Faq() {
  const t = useText(TEXT).faq;
  return (
    <section id="faq" className="paper-grain relative z-10 scroll-mt-16 bg-paper text-ink" data-surface="light">
      <div className="grid gap-12 px-5 py-24 sm:px-8 sm:py-32 lg:grid-cols-[1fr_2fr] lg:pe-12 lg:ps-[17rem]">
        <div className="reveal">
          <Flourish text={t.title} />
          <p className="mt-5 text-lg leading-8 text-ink/70">{t.lead}</p>
        </div>
        <div className="reveal divide-y divide-ink/15 border-y border-ink/15">
          {t.items.map(([q, a]) => (
            <details key={q} className="group py-5 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-display text-lg font-semibold">
                {q}
                <span className="font-serif text-2xl leading-none text-amber-700 transition group-open:rotate-45">+</span>
              </summary>
              <p className="mt-3 max-w-2xl leading-7 text-ink/65">{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

function Team() {
  const { lang } = useLang();
  const t = useText(TEXT).team;
  const [initial, rest] = splitInitial(t.title, lang);
  return (
    <section id="team" className="relative z-10 scroll-mt-16 bg-ink text-paper" data-surface="dark">
      <div className="px-5 py-24 sm:px-8 sm:py-32 lg:pe-12 lg:ps-[17rem]">
        <div className="reveal max-w-3xl">
          <h2 className="font-serif text-[2.6rem] leading-[1.05] tracking-tight sm:text-6xl">
            <span
              className={`me-[0.02em] inline-block align-[-0.08em] leading-none text-amber-400 italic ${
                lang === "ar" ? "text-[1.15em]" : "text-[1.45em]"
              }`}
            >
              {initial}
            </span>
            {rest}
          </h2>
          <p className="mt-6 text-lg leading-8 text-paper/70">{t.lead(t.university)}</p>
        </div>
        <div className="reveal mt-14 grid gap-x-12 gap-y-6 md:grid-cols-[16rem_1fr]">
          <div>
            <p className="font-serif text-lg text-amber-400 italic">{t.supervisedBy}</p>
            <p className="mt-1 font-display text-xl font-semibold">{t.supervisor}</p>
          </div>
          <div>
            <p className="font-serif text-lg text-amber-400 italic">{t.theTeam}</p>
            <ul className="mt-1 grid gap-x-8 gap-y-1 sm:grid-cols-2">
              {t.members.map((m) => (
                <li key={m.name} className="font-display text-xl font-semibold">
                  {m.name} {m.role && <span className="font-serif text-base font-normal text-paper/60 italic">{m.role}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function Closing() {
  const t = useText(TEXT);
  return (
    <section className="relative z-10 h-[80svh] min-h-[520px] overflow-hidden bg-ink" data-surface="dark">
      <Photo name="closing" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/20 to-black/30" aria-hidden />
      <div className="relative flex h-full flex-col justify-end px-5 pb-14 text-paper sm:px-8 lg:pe-12 lg:ps-[17rem]">
        <h2 className="max-w-4xl font-display text-[clamp(3rem,9vw,8rem)] leading-[0.88] font-semibold tracking-[-0.045em]">
          {t.closing.line}
          <span className="font-serif font-normal italic">{t.closing.emphasis}</span>
        </h2>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <ConsoleButton className="bg-amber-400 px-6 py-3 text-sm text-ink hover:bg-amber-300">
            {t.signInConsole} <ForwardArrow />
          </ConsoleButton>
          <DemoBadge />
        </div>
      </div>
    </section>
  );
}

// "Try it" (with the Markdown renderer for its sample report) loads after the first screen, keeping the first download small
const TryIt = lazy(() => import("../components/TryIt").then((m) => ({ default: m.TryIt })));

const REGS_URL = "https://sitesentry-regs.streamlit.app";
const REGS_CODE = "https://github.com/albaraafarag23/sitesentry-regs";

/** Opens a page of another site in a new tab, safely (no access back to this page). */
function OutLink({ href, className = "", children }: { href: string; className?: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  );
}

/** The rulebook chapter's opener: the codes' own wording, set large and faint, instead of a photo. */
function RulebookBackdrop() {
  const lines = [
    "5.13  Safety helmets – Provide head protection from dropped objects",
    "5.13  High visibility vests to be worn by employees working on construction sites",
    "5.9   Barrier off or cover over excavations or pits",
    "5.3   The working platform is capable of carrying the load it was designed for",
    "5.5.1 The entity shall protect people from falling objects",
    "5.7   The site rules shall consider … Smoking; … Restricted areas",
    "7.2   An appointed person … will telephone for an ambulance",
  ];
  return (
    <div className="absolute inset-0 overflow-hidden bg-[#16130f]">
      <div dir="ltr" className="absolute -inset-x-10 top-1/2 -translate-y-1/2 -rotate-3 space-y-3 font-serif text-[clamp(1.4rem,3.4vw,3.2rem)] leading-tight whitespace-nowrap text-paper/[0.09] italic">
        {lines.map((line, i) => (
          <p key={i} style={{ marginInlineStart: `${(i % 3) * 6}vw` }}>
            {line}
          </p>
        ))}
      </div>
      <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/60" />
    </div>
  );
}

function RulebookChapter() {
  const all = useText(TEXT);
  const t = all.regs;
  return (
    <Chapter id="regs" n={8} title={t.title} kicker={t.kicker} backdrop={<RulebookBackdrop />}>
      <Lead title={t.leadTitle}>{t.lead}</Lead>
      <div className="mt-16 grid gap-10 xl:grid-cols-[1.35fr_1fr] xl:items-start">
        <figure className="reveal">
          <article className="rounded-md bg-white p-6 shadow-sm ring-1 ring-ink/10">
            <div className="flex items-center justify-between border-b border-ink/10 pb-4">
              <div>
                <p className="text-xs font-semibold tracking-wide text-ink/40 uppercase">{t.excerptLabel}</p>
                <p className="mt-1 font-display font-semibold">{t.excerptTitle}</p>
              </div>
              <span className="rounded bg-orange-100 px-2 py-0.5 text-xs font-bold text-orange-700">{all.severity.HIGH}</span>
            </div>
            <p className="mt-4 font-serif text-xl">{t.excerptHeading}</p>
            <p className="mt-2 flex items-start gap-2 text-sm font-semibold text-ink/80">
              <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden /> {t.excerptWhere}
            </p>
            <blockquote dir="ltr" lang="en" className="mt-3 border-s-2 border-amber-600/40 ps-4 text-start font-serif text-[15px] leading-relaxed text-ink/75 italic">
              {t.excerptQuote}
            </blockquote>
            <OutLink
              href="https://mc.spsa.shj.ae/media/documents/8ZTXXGJk0O0HgcHO0bs6g_OSHJ-CoP-02%20OSH%20Management%20in%20Construction%20Version%201%20English.pdf"
              className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-ink/60 underline decoration-ink/25 underline-offset-2 hover:text-ink"
            >
              {t.excerptPdf} <ExternalLink className="h-3 w-3" aria-hidden />
            </OutLink>
          </article>
          <figcaption className="mt-3">
            <p className="font-display font-semibold">{t.excerptCaptionTitle}</p>
            <p className="mt-0.5 max-w-md text-[15px] leading-6 text-ink/60">{t.excerptCaption}</p>
          </figcaption>
        </figure>
        <Stats items={t.stats} className="grid gap-10 sm:grid-cols-2 xl:grid-cols-1" />
      </div>

      {/* the companion project, one click away */}
      <div className="reveal mt-16 overflow-hidden rounded-md bg-ink text-paper">
        <div className="grid gap-8 p-6 sm:p-10 lg:grid-cols-[1.3fr_1fr] lg:items-end">
          <div>
            <p className="font-serif text-lg text-amber-300 italic">{t.companionKicker}</p>
            <p className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">{t.companionTitle}</p>
            <p className="mt-4 max-w-xl leading-7 text-paper/70">{t.companionText}</p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <OutLink
                href={REGS_URL}
                className="inline-flex items-center gap-2 rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-ink transition hover:bg-amber-300"
              >
                {t.companionButton} <ExternalLink className="h-4 w-4" aria-hidden />
              </OutLink>
              <OutLink href={REGS_CODE} className="rounded-full px-4 py-2.5 text-sm font-semibold text-paper ring-1 ring-paper/30 transition hover:bg-white/10">
                {t.companionCode}
              </OutLink>
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-6">
            {t.companionStats.map(([value, label]) => (
              <div key={value} className="border-t border-paper/20 pt-3">
                <dt className="font-display text-4xl font-semibold tracking-tight">
                  <bdi dir="ltr">{value}</bdi>
                </dt>
                <dd className="mt-1 text-sm leading-5 text-paper/60">{label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
      <DenseList items={t.list} />
    </Chapter>
  );
}

/** Measured results, each from a write-up in the project's documentation. */
function Results() {
  const t = useText(TEXT).results;
  return (
    <section id="results" className="paper-grain relative z-10 scroll-mt-16 border-b border-ink/10 bg-paper text-ink" data-surface="light">
      <div className="px-5 py-24 sm:px-8 sm:py-32 lg:pe-12 lg:ps-[17rem]">
        <div className="reveal max-w-3xl">
          <Flourish text={t.title} as="h2" />
          <p className="mt-6 max-w-2xl text-lg leading-8 text-ink/70">{t.lead}</p>
        </div>
        <div className="mt-16 grid gap-x-10 gap-y-12 sm:grid-cols-2 xl:grid-cols-3">
          {t.items.map(([value, label]) => (
            <Stat key={label} value={value} label={label} />
          ))}
        </div>
        <p className="reveal mt-12 max-w-2xl font-serif text-lg text-ink/55 italic">{t.note}</p>
      </div>
    </section>
  );
}

const CREDITS = [
  "Nicolas Beuret",
  "Heri Susilo",
  "Michelle Ding",
  "Troy Mortier",
  "Tsuyoshi Kozu",
  "Glenov Brankovic",
  "Jerry Wei",
  "Centar MURID",
  "Tunahan Kuzgun",
];

function Footer() {
  const t = useText(TEXT);
  return (
    <footer className="relative z-10 bg-ink text-paper/50" data-surface="dark">
      <div className="flex flex-col gap-4 border-t border-white/10 px-5 py-10 text-xs sm:px-8 lg:flex-row lg:items-center lg:justify-between lg:pe-12 lg:ps-[17rem]">
        <div className="flex items-center gap-2.5 text-paper">
          <LogoMark className="h-6 w-6" />
          <span className="font-display text-sm font-semibold">{P}</span>
          <span className="text-paper/50">© {new Date().getFullYear()}</span>
        </div>
        <div className="max-w-2xl space-y-2 leading-5">
          <OutLink href={REGS_URL} className="inline-flex items-center gap-1 text-paper/75 underline decoration-paper/25 underline-offset-2 hover:text-paper">
            {t.companionFooter} <ExternalLink className="h-3 w-3" aria-hidden />
          </OutLink>
          <p>{t.credits(CREDITS.join(", "))}</p>
        </div>
      </div>
    </footer>
  );
}

export function Landing() {
  const t = useText(TEXT);
  // what's under the top bar decides whether it's light or dark
  const probeTop = useCallback(() => ({ x: window.innerWidth / 2, y: 32 }), []);
  const { active, surface: topSurface } = useScrollState(t.chapters, probeTop);

  useEffect(() => {
    document.title = t.docTitle;
  }, [t.docTitle]);

  // A link straight to a chapter (…/#regs): the browser tries to jump before this page is built, so jump once it
  // is, and again when the late-loading parts ("Try it", fonts) have settled and moved things.
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (!id) return;
    const jump = () => document.getElementById(id)?.scrollIntoView({ block: "start" });
    const timers = [0, 400, 1200].map((ms) => window.setTimeout(jump, ms));
    document.fonts?.ready.then(jump).catch(() => {});
    // a reader who starts scrolling has arrived: stop correcting
    const stop = () => timers.forEach((x) => window.clearTimeout(x));
    window.addEventListener("wheel", stop, { once: true, passive: true });
    window.addEventListener("touchmove", stop, { once: true, passive: true });
    return () => {
      stop();
      window.removeEventListener("wheel", stop);
      window.removeEventListener("touchmove", stop);
    };
  }, []);

  return (
    <div className="bg-paper font-display text-ink">
      <TopBar surface={topSurface} />
      <ChapterIndex chapters={t.chapters} active={active} label={t.chaptersLabel} />
      <main>
        <Hero />
        <Suspense fallback={<section id="try" className="min-h-[100svh] bg-paper" aria-busy="true" />}>
          <TryIt />
        </Suspense>
        <PpeChapter />
        <SmokingChapter />
        <ZonesChapter />
        <AlertsChapter />
        <RulesChapter />
        <ConsoleChapter />
        <EdgeChapter />
        <RulebookChapter />
        <Results />
        <Faq />
        <Team />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
