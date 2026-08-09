/**
 * English and Lao strings.
 *
 * A national platform for Lao PDR presented only in English would be a strange
 * artefact — the people whose coverage this maps should be able to read it.
 *
 * The Lao translations below were written without a native reviewer and should
 * be checked by one before any public launch. Where a technical term has no
 * settled Lao equivalent (RSRP, 4G, H3), the English is kept rather than
 * invented, which is what Lao technical writing generally does.
 */

export type Language = "en" | "lo";

export interface Strings {
  title: string;
  tagline: string;

  navMap: string;
  navDashboard: string;
  getApp: string;

  statMeasurements: string;
  statAreaMapped: string;
  statNoService: string;
  statDevices: string;
  statUpdated: string;
  ofCountry: string;
  never: string;
  none: string;

  coverage: string;
  allOperators: string;
  operator: string;

  legendPredicted: string;
  legendUnmeasured: string;
  legendShow: string;
  legendHide: string;

  loading: string;
  noTilesInView: string;
  jumpToData: string;

  stateGoodLabel: string;
  stateGoodMeaning: string;
  stateGoodRemedy: string;
  stateWeakLabel: string;
  stateWeakMeaning: string;
  stateWeakRemedy: string;
  stateCallsLabel: string;
  stateCallsMeaning: string;
  stateCallsRemedy: string;
  stateUnusableLabel: string;
  stateUnusableMeaning: string;
  stateUnusableRemedy: string;
  stateNoneLabel: string;
  stateNoneMeaning: string;
  stateNoneRemedy: string;

  inspectorRemedy: string;
  inspectorPredicted: string;
  inspectorLowConfidence: string;
  inspectorDropout: string;
  inspectorMeasurements: string;
  inspectorDevices: string;
  inspectorSignal: string;
  inspectorDownload: string;
  inspectorLatency: string;
  inspectorLastMeasured: string;

  dashTitle: string;
  dashSubtitle: string;
  dashWhatItWouldTake: string;
  dashNewTower: string;
  dashUpgrade: string;
  dashOptimisation: string;
  dashNoAction: string;
  dashAreas: string;
  dashByOperator: string;
  dashOperatorTiles: string;
  dashOperatorArea: string;
  dashOperatorGood: string;
  dashOperatorUnusable: string;
  dashOperatorSignal: string;
  dashPriority: string;
  dashPrioritySubtitle: string;
  dashRank: string;
  dashLocation: string;
  dashState: string;
  dashEvidence: string;
  dashAction: string;
  dashShowOnMap: string;
  dashMeasuredNotModelled: string;
  dashNoData: string;
  dashCoverageScope: string;
}

const en: Strings = {
  title: "Where the internet actually works",
  tagline:
    "Measured on ordinary phones across Lao PDR — including the places with no signal at all.",

  navMap: "Map",
  navDashboard: "Dashboard",
  getApp: "Get the app",

  statMeasurements: "Measurements",
  statAreaMapped: "Area measured",
  statNoService: "Readings with no service",
  statDevices: "Contributing devices",
  statUpdated: "Updated",
  ofCountry: "of Lao PDR",
  never: "Never",
  none: "None",

  coverage: "Coverage",
  allOperators: "All networks",
  operator: "Network",

  legendPredicted: "Dashed and faded hexagons are predicted, not measured.",
  legendUnmeasured: "Unmeasured areas are left blank — the map claims nothing about them.",
  legendShow: "Show legend",
  legendHide: "Hide",

  loading: "Loading coverage…",
  noTilesInView: "No measurements in this view.",
  jumpToData: "Go to measured areas",

  stateGoodLabel: "Good service",
  stateGoodMeaning: "4G data works normally",
  stateGoodRemedy: "No action needed",
  stateWeakLabel: "Weak 4G",
  stateWeakMeaning: "Data works but is slow (RSRP below −110 dBm)",
  stateWeakRemedy: "Optimisation",
  stateCallsLabel: "Calls only",
  stateCallsMeaning: "Calls and SMS work, data does not",
  stateCallsRemedy: "Data capacity upgrade",
  stateUnusableLabel: "Too weak to use",
  stateUnusableMeaning: "A tower is visible but the phone cannot connect",
  stateUnusableRemedy: "Upgrade or repeater — no new tower needed",
  stateNoneLabel: "No network at all",
  stateNoneMeaning: "No tower reaches this area",
  stateNoneRemedy: "New tower — capital investment",

  inspectorRemedy: "What it would take:",
  inspectorPredicted:
    "Predicted by the coverage model — nobody has measured this hexagon yet.",
  inspectorLowConfidence:
    "Measured, but by too few devices to publish the details without risking identifying whoever travelled through.",
  inspectorDropout: "Service here is not always this good — at its worst it drops to",
  inspectorMeasurements: "Measurements",
  inspectorDevices: "Contributing devices",
  inspectorSignal: "Average signal",
  inspectorDownload: "Download",
  inspectorLatency: "Latency",
  inspectorLastMeasured: "Last measured",

  dashTitle: "Coverage dashboard",
  dashSubtitle: "For operators and the Ministry of Technology and Communications",
  dashWhatItWouldTake: "What it would take to fix",
  dashNewTower: "New tower needed",
  dashUpgrade: "Upgrade or repeater",
  dashOptimisation: "Optimisation",
  dashNoAction: "No action needed",
  dashAreas: "areas",
  dashByOperator: "By network",
  dashOperatorTiles: "Areas",
  dashOperatorArea: "Measured",
  dashOperatorGood: "Good",
  dashOperatorUnusable: "Unusable",
  dashOperatorSignal: "Avg signal",
  dashPriority: "Priority areas",
  dashPrioritySubtitle:
    "Places where no usable service was recorded, ranked by severity then by weight of evidence.",
  dashRank: "#",
  dashLocation: "Location",
  dashState: "Finding",
  dashEvidence: "Evidence",
  dashAction: "Action",
  dashShowOnMap: "Show on map",
  dashMeasuredNotModelled:
    "This list comes from measurements alone. Modelled tower-site ranking, which needs population and terrain data, is not part of the pilot yet.",
  dashNoData: "Nothing measured yet.",
  dashCoverageScope: "measured so far",
};

const lo: Strings = {
  title: "ອິນເຕີເນັດໃຊ້ໄດ້ຢູ່ໃສແທ້",
  tagline:
    "ວັດແທກດ້ວຍໂທລະສັບທົ່ວໄປໃນ ສປປ ລາວ — ລວມທັງບ່ອນທີ່ບໍ່ມີສັນຍານເລີຍ.",

  navMap: "ແຜນທີ່",
  navDashboard: "ລາຍງານ",
  getApp: "ດາວໂຫຼດແອັບ",

  statMeasurements: "ຈຳນວນການວັດແທກ",
  statAreaMapped: "ພື້ນທີ່ວັດແທກແລ້ວ",
  statNoService: "ຈຸດທີ່ບໍ່ມີສັນຍານ",
  statDevices: "ອຸປະກອນທີ່ຮ່ວມ",
  statUpdated: "ອັບເດດ",
  ofCountry: "ຂອງ ສປປ ລາວ",
  never: "ຍັງບໍ່ມີ",
  none: "ບໍ່ມີ",

  coverage: "ການຄອບຄຸມສັນຍານ",
  allOperators: "ທຸກເຄືອຂ່າຍ",
  operator: "ເຄືອຂ່າຍ",

  legendPredicted: "ຮູບຫົກແຈທີ່ເປັນເສັ້ນຂີດ ແລະ ຈາງ ແມ່ນການຄາດຄະເນ ບໍ່ແມ່ນການວັດແທກ.",
  legendUnmeasured: "ພື້ນທີ່ທີ່ຍັງບໍ່ໄດ້ວັດແທກຈະຖືກປະໄວ້ວ່າງ — ແຜນທີ່ບໍ່ໄດ້ອ້າງອີງຫຍັງກ່ຽວກັບມັນ.",
  legendShow: "ສະແດງຄຳອະທິບາຍ",
  legendHide: "ເຊື່ອງ",

  loading: "ກຳລັງໂຫຼດຂໍ້ມູນ…",
  noTilesInView: "ບໍ່ມີການວັດແທກໃນພື້ນທີ່ນີ້.",
  jumpToData: "ໄປຫາພື້ນທີ່ທີ່ວັດແທກແລ້ວ",

  stateGoodLabel: "ສັນຍານດີ",
  stateGoodMeaning: "ອິນເຕີເນັດ 4G ໃຊ້ໄດ້ປົກກະຕິ",
  stateGoodRemedy: "ບໍ່ຕ້ອງແກ້ໄຂ",
  stateWeakLabel: "4G ອ່ອນ",
  stateWeakMeaning: "ໃຊ້ໄດ້ແຕ່ຊ້າ (RSRP ຕ່ຳກວ່າ −110 dBm)",
  stateWeakRemedy: "ປັບປຸງປະສິດທິພາບ",
  stateCallsLabel: "ໂທໄດ້ຢ່າງດຽວ",
  stateCallsMeaning: "ໂທ ແລະ ສົ່ງ SMS ໄດ້ ແຕ່ໃຊ້ອິນເຕີເນັດບໍ່ໄດ້",
  stateCallsRemedy: "ຍົກລະດັບຄວາມສາມາດຂໍ້ມູນ",
  stateUnusableLabel: "ອ່ອນເກີນໄປ ໃຊ້ບໍ່ໄດ້",
  stateUnusableMeaning: "ເຫັນເສົາສັນຍານ ແຕ່ໂທລະສັບເຊື່ອມຕໍ່ບໍ່ໄດ້",
  stateUnusableRemedy: "ຍົກລະດັບ ຫຼື ຕິດຕັ້ງຕົວຂະຫຍາຍສັນຍານ — ບໍ່ຕ້ອງສ້າງເສົາໃໝ່",
  stateNoneLabel: "ບໍ່ມີສັນຍານເລີຍ",
  stateNoneMeaning: "ບໍ່ມີເສົາສັນຍານໃດເຂົ້າເຖິງພື້ນທີ່ນີ້",
  stateNoneRemedy: "ຕ້ອງສ້າງເສົາໃໝ່ — ການລົງທຶນ",

  inspectorRemedy: "ສິ່ງທີ່ຕ້ອງເຮັດ:",
  inspectorPredicted: "ຄາດຄະເນໂດຍແບບຈຳລອງ — ຍັງບໍ່ມີໃຜວັດແທກພື້ນທີ່ນີ້.",
  inspectorLowConfidence:
    "ວັດແທກແລ້ວ ແຕ່ມີອຸປະກອນໜ້ອຍເກີນໄປ ຈຶ່ງບໍ່ສະແດງລາຍລະອຽດ ເພື່ອປົກປ້ອງຄວາມເປັນສ່ວນຕົວຂອງຜູ້ເດີນທາງ.",
  inspectorDropout: "ສັນຍານຢູ່ນີ້ບໍ່ດີສະເໝີໄປ — ຮ້າຍແຮງທີ່ສຸດຫຼຸດລົງເປັນ",
  inspectorMeasurements: "ຈຳນວນການວັດແທກ",
  inspectorDevices: "ອຸປະກອນທີ່ຮ່ວມ",
  inspectorSignal: "ຄວາມແຮງສັນຍານສະເລ່ຍ",
  inspectorDownload: "ຄວາມໄວດາວໂຫຼດ",
  inspectorLatency: "ຄວາມຊັກຊ້າ",
  inspectorLastMeasured: "ວັດແທກຄັ້ງລ່າສຸດ",

  dashTitle: "ລາຍງານການຄອບຄຸມສັນຍານ",
  dashSubtitle: "ສຳລັບຜູ້ໃຫ້ບໍລິການ ແລະ ກະຊວງເຕັກໂນໂລຊີ ແລະ ການສື່ສານ",
  dashWhatItWouldTake: "ສິ່ງທີ່ຕ້ອງເຮັດເພື່ອແກ້ໄຂ",
  dashNewTower: "ຕ້ອງສ້າງເສົາໃໝ່",
  dashUpgrade: "ຍົກລະດັບ ຫຼື ຕົວຂະຫຍາຍສັນຍານ",
  dashOptimisation: "ປັບປຸງປະສິດທິພາບ",
  dashNoAction: "ບໍ່ຕ້ອງແກ້ໄຂ",
  dashAreas: "ພື້ນທີ່",
  dashByOperator: "ຕາມເຄືອຂ່າຍ",
  dashOperatorTiles: "ພື້ນທີ່",
  dashOperatorArea: "ວັດແທກແລ້ວ",
  dashOperatorGood: "ດີ",
  dashOperatorUnusable: "ໃຊ້ບໍ່ໄດ້",
  dashOperatorSignal: "ສັນຍານສະເລ່ຍ",
  dashPriority: "ພື້ນທີ່ບຸລິມະສິດ",
  dashPrioritySubtitle:
    "ບ່ອນທີ່ບໍ່ພົບການບໍລິການທີ່ໃຊ້ໄດ້ ຈັດລຳດັບຕາມຄວາມຮ້າຍແຮງ ແລະ ນ້ຳໜັກຂອງຫຼັກຖານ.",
  dashRank: "ລຳດັບ",
  dashLocation: "ທີ່ຕັ້ງ",
  dashState: "ຜົນການວັດແທກ",
  dashEvidence: "ຫຼັກຖານ",
  dashAction: "ການດຳເນີນການ",
  dashShowOnMap: "ສະແດງໃນແຜນທີ່",
  dashMeasuredNotModelled:
    "ລາຍການນີ້ມາຈາກການວັດແທກຈິງເທົ່ານັ້ນ. ການຈັດລຳດັບຈຸດຕັ້ງເສົາດ້ວຍແບບຈຳລອງ ເຊິ່ງຕ້ອງການຂໍ້ມູນປະຊາກອນ ແລະ ພູມສັນຖານ ຍັງບໍ່ທັນຢູ່ໃນໄລຍະນຳຮ່ອງ.",
  dashNoData: "ຍັງບໍ່ມີການວັດແທກ.",
  dashCoverageScope: "ວັດແທກແລ້ວ",
};

export const TRANSLATIONS: Record<Language, Strings> = { en, lo };

export const LANGUAGE_NAMES: Record<Language, string> = { en: "English", lo: "ລາວ" };

const STORAGE_KEY = "aipnicmp.language";

export function loadLanguage(): Language {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "lo") return stored;
  return navigator.language?.toLowerCase().startsWith("lo") ? "lo" : "en";
}

export function saveLanguage(language: Language): void {
  localStorage.setItem(STORAGE_KEY, language);
}
