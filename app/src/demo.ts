// 示範資料：術語掃描、翻譯進度與結果還沒接上 Python 後端，先用設計稿的內容。
// 接上後端後，這個檔案只留給介面預覽使用。

export interface TermChoice {
  id: string;
  term: string;
  where: string;
  context: string;
  suggest: number; // 預選的選項；-1 代表需要使用者選
  options: { zh: string; src: string }[];
}

export const DEMO_TERMS: TermChoice[] = [
  { id: "moment", term: "moment", where: "p.14 等 63 處", context: "the pitching moment about the quarter-chord point", suggest: 0,
    options: [{ zh: "力矩", src: "力學" }, { zh: "動差", src: "統計學" }, { zh: "矩", src: "數學" }] },
  { id: "circulation", term: "circulation", where: "p.22 等 41 處", context: "the circulation around the airfoil determines the lift", suggest: -1,
    options: [{ zh: "環流量", src: "力學" }, { zh: "環流", src: "氣象學" }, { zh: "循環", src: "物理學" }] },
  { id: "head", term: "head", where: "p.31 等 9 處", context: "the total pressure head measured by the pitot tube", suggest: -1,
    options: [{ zh: "水頭", src: "力學" }, { zh: "揚程", src: "機械工程" }, { zh: "壓頭", src: "化學工程" }] },
  { id: "lift", term: "lift", where: "p.3 等 118 處", context: "lift per unit span is proportional to the circulation", suggest: 0,
    options: [{ zh: "升力", src: "航空太空" }, { zh: "舉力", src: "機械工程" }] },
  { id: "chord", term: "chord", where: "p.5 等 72 處", context: "measured from the leading edge along the chord", suggest: 0,
    options: [{ zh: "弦長", src: "航空太空" }, { zh: "弦", src: "數學" }] },
  { id: "stall", term: "stall", where: "p.47 等 12 處", context: "flow separation near stall reduces the lift slope", suggest: 0,
    options: [{ zh: "失速", src: "航空太空" }, { zh: "停轉", src: "機械工程" }] },
];

// 「顯示其餘」展開的詞：已依科目的名詞庫順序選好
export const DEMO_TERMS_PRESET: TermChoice[] = [
  { id: "airfoil", term: "airfoil", where: "p.2 等 103 處", context: "the pressure distribution over a thin airfoil", suggest: 0,
    options: [{ zh: "翼剖面", src: "力學" }, { zh: "翼形", src: "航空太空" }] },
  { id: "stagnation", term: "stagnation", where: "p.4 等 54 處", context: "the stagnation pressure upstream of the shock", suggest: 0,
    options: [{ zh: "停滯", src: "力學" }, { zh: "止流", src: "航空太空" }] },
  { id: "isentropic", term: "isentropic", where: "p.3 等 45 處", context: "an isentropic expansion through the nozzle", suggest: 0,
    options: [{ zh: "等熵", src: "氣象學" }, { zh: "等熵線", src: "物理學" }] },
  { id: "hypersonic", term: "hypersonic", where: "p.61 等 28 處", context: "hypersonic flow past a blunt body", suggest: 0,
    options: [{ zh: "極音速", src: "機械工程" }, { zh: "超高音速", src: "氣象學" }] },
  { id: "compressibility", term: "compressibility", where: "p.2 等 27 處", context: "compressibility effects become significant above Mach 0.3", suggest: 0,
    options: [{ zh: "可壓縮性", src: "力學" }, { zh: "壓縮係數", src: "氣象學" }] },
  { id: "divergence", term: "divergence", where: "p.18 等 16 處", context: "the drag divergence Mach number", suggest: 0,
    options: [{ zh: "發散", src: "力學" }, { zh: "散度", src: "力學" }] },
  { id: "shear", term: "shear", where: "p.71 等 10 處", context: "the wall shear stress in the boundary layer", suggest: 0,
    options: [{ zh: "剪力", src: "力學" }, { zh: "剪切", src: "造船工程" }] },
  { id: "turbulence", term: "turbulence", where: "p.75 等 5 處", context: "free-stream turbulence in the test section", suggest: 0,
    options: [{ zh: "紊流", src: "航空太空" }, { zh: "亂流", src: "力學" }] },
];

export const DEMO_FIXES = [
  { cn: "湍流", tw: "紊流", en: "turbulence", n: 11 },
  { cn: "無量綱", tw: "無因次", en: "dimensionless", n: 2 },
  { cn: "伯努利", tw: "白努利", en: "Bernoulli", n: 4 },
  { cn: "迎角", tw: "攻角", en: "angle of attack", n: 6 },
  { cn: "鏈式法則", tw: "連鎖律", en: "chain rule", n: 1 },
];

export const DEMO_KEEP = [
  { name: "Pearson Education", pages: "頁尾 120 處" },
  { name: "Sandia National Laboratories", pages: "p.58" },
  { name: "NACA 2412", pages: "p.9 等 14 處" },
  { name: "Prandtl", pages: "p.21 等 6 處" },
];

export const DEMO_PARAGRAPHS = [
  {
    en: "The lift coefficient increases linearly with angle of attack until flow separation begins near the trailing edge.",
    zh: "升力係數隨攻角線性增加，直到後緣附近開始出現流動分離。",
  },
  {
    en: "As the Reynolds number increases, the boundary layer undergoes transition and becomes turbulent upstream of the separation point.",
    zh: "雷諾數增加時，邊界層會發生轉捩，並在分離點上游變成紊流。",
    fixed: { from: "湍流", to: "紊流" },
  },
  {
    en: "The pressure coefficient on the upper surface reaches its minimum near the leading edge.",
    zh: null,
  },
];

export const DEMO_CHECKS = [
  { page: 12, count: 5, text: "表 8.1 的馬赫數範圍與流動型態" },
  { page: 31, count: 3, text: "皮托管量測的總壓水頭" },
  { page: 44, count: 6, text: "NACA 2412 的升力曲線" },
  { page: 58, count: 4, text: "Sandia National Laboratories 的風洞資料" },
  { page: 77, count: 4, text: "斜震波的偏轉角關係" },
  { page: 93, count: 3, text: "跨音速翼型的震波位置" },
  { page: 104, count: 3, text: "超臨界翼型的設計條件" },
];

export const DEMO_RECENT = [
  { name: "空氣動力學講義.pdf", meta: "26 頁 · 03:13" },
  { name: "aerodynamics-ch8.p1-8.pdf", meta: "8 頁 · 02:10" },
];

/** 模擬翻譯中，每頁約 250 毫秒。 */
export const DEMO_MS_PER_PAGE = 250;
export const DEMO_ANALYSIS_SECONDS = 74;
