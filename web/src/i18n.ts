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

  brandSubtitle: string;
  sidebarNote: string;
  navMapHint: string;
  navOverview: string;
  navOverviewHint: string;
  navPriority: string;
  navPriorityHint: string;
  navNetworks: string;
  navNetworksHint: string;
  navCollectors: string;
  navCollectorsHint: string;
  menu: string;
  basemapStreets: string;
  basemapSatellite: string;
  terrain: string;
  terrainHint: string;

  collectorsTitle: string;
  collectorsSubtitle: string;
  collectorsDevice: string;
  collectorsLastSeen: string;
  collectorsAccepted: string;
  collectorsRejected: string;
  collectorsRejectRate: string;
  collectorsSimulated: string;
  towersTitle: string;
  towersSubtitle: string;
  towersOperator: string;
  towersSites: string;
  towersPlaced: string;
  towersCells: string;
  towersNotMeasured: string;
  towersNote: string;
  collectorsNone: string;
  collectorsDormant: string;
  collectorsDormantWhy: string;
  collectorsRealCount: string;

  overviewTitle: string;
  overviewSubtitle: string;
  priorityTitle: string;
  networksTitle: string;

  statMeasurements: string;
  statAreaMapped: string;
  statNoService: string;
  statDevices: string;
  statUpdated: string;
  statEnrolled: string;
  live: string;
  railCollapse: string;
  railExpand: string;
  livePaused: string;
  liveResume: string;
  livePause: string;
  collectingNow: string;
  reportingExplain: string;
  collectorHere: string;
  approxPosition: string;
  ofCountry: string;
  never: string;
  none: string;

  coverage: string;
  allOperators: string;
  signalState: string;
  allStates: string;
  operator: string;

  areaCountry: string;
  areaProvince: string;
  areaDistrict: string;
  areaVillage: string;
  areaAllCountry: string;
  areaAllProvinces: string;
  areaAllDistricts: string;
  areaAllVillages: string;
  areaClear: string;
  areaNotMeasured: string;
  areaGood: string;
  areaUnusable: string;
  areaMeasuredHere: string;
  areaOfArea: string;
  areaDevices: string;
  areaLowConfidence: string;
  areaApproximate: string;
  areaSource: string;
  areaTooLarge: string;
  areaDrillHint: string;

  networkUnmeasured: string;
  networksUnmeasuredNote: string;

  loginTitle: string;
  loginWhy: string;
  loginWithGoogle: string;
  loginChooseAccount: string;
  loginApprovalNote: string;
  loginSigningIn: string;
  loginFailed: string;
  loginScriptFailed: string;
  loginNotConfigured: string;
  loginUnreachable: string;
  loginPendingTitle: string;
  loginPendingBody: string;
  loginRejectedTitle: string;
  loginRejectedBody: string;
  loginUseAnother: string;
  loginTeamTitle: string;
  loginAdvisorsTitle: string;
  signOut: string;

  navUsers: string;
  navUsersHint: string;
  usersTitle: string;
  usersSubtitle: string;
  usersNone: string;
  usersPendingCount: string;
  usersPerson: string;
  usersRole: string;
  usersStatus: string;
  usersRequested: string;
  usersActions: string;
  usersApprove: string;
  usersReject: string;
  usersYou: string;
  usersLastSuperAdmin: string;
  usersRoleAdmin: string;
  usersRoleOperator: string;
  usersNoNetwork: string;
  usersChooseNetwork: string;
  usersChooseNetworkWhy: string;
  cancel: string;
  imageryLimit: string;
  mastLabel: string;
  mastAccuracy: string;
  mastHeardFrom: string;
  mastStrongest: string;
  mastEstimate: string;
  scopeBanner: string;
  scopeBannerDetail: string;
  usersRoleSuperAdmin: string;
  usersStatusPending: string;
  usersStatusApproved: string;
  usersStatusRejected: string;

  legendPredicted: string;
  legendAreaShading: string;
  legendCollector: string;
  legendMasts: string;
  legendMastHalo: string;
  legendMastVague: string;
  legendMastsShort: string;
  legendMastHaloShort: string;
  legendMastVagueShort: string;
  legendMore: string;
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
  inspectorLocation: string;
  inspectorDirections: string;

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

  brandSubtitle: "Coverage mapping · Lao PDR",
  sidebarNote: "Measured on ordinary phones, including where there is no signal at all.",
  navMapHint: "Where the internet works",
  navOverview: "Overview",
  navOverviewHint: "What it would cost to fix",
  navPriority: "Priority areas",
  navPriorityHint: "Measured dead zones, ranked",
  navNetworks: "Networks",
  navNetworksHint: "Coverage by operator",
  navCollectors: "Collectors",
  navCollectorsHint: "Phones reporting data",
  menu: "Menu",
  basemapStreets: "Map",
  basemapSatellite: "Satellite",
  terrain: "3D",
  terrainHint:
    "Tilt the map and show the terrain. Relief is exaggerated slightly so ridges read at this scale. Uses more data.",

  collectorsTitle: "Collectors",
  collectorsSubtitle:
    "The phones contributing measurements. No positions are shown here — where a collector travelled is exactly what the map's hexagons exist to hide.",
  collectorsDevice: "Device",
  collectorsLastSeen: "Last seen",
  collectorsAccepted: "Accepted",
  collectorsRejected: "Rejected",
  collectorsRejectRate: "Refused",
  collectorsSimulated: "simulated",
  collectorsNone: "No collectors have enrolled yet.",
  towersTitle: "Cells heard",
  towersSubtitle: "What the collectors have picked up, by operator — not an operator's own inventory",
  towersOperator: "Operator",
  towersSites: "Sites",
  towersPlaced: "Placed",
  towersCells: "Cells",
  towersNotMeasured: "no collector has carried this SIM",
  towersNote:
    "A mast usually carries several cells, so cells count antennas rather than structures. Sites group cells heard from the same places; that grouping holds up better than any single position, because cells sharing a mast are heard in the same places and their estimates move together — but it is still a count of what was heard, not of structures anybody has seen. Only cells heard from far enough apart get a position at all, and everything here is what the fleet has heard, never what an operator owns.",
  collectorsDormant: "%N% enrolments with no readings",
  collectorsDormantWhy:
    "Almost always the same handset after a reinstall. The signing key lives in the phone's secure hardware and cannot be backed up, so a reinstalled app has to enrol as a new device. These are kept rather than deleted, but they are not working collectors.",
  collectorsRealCount: "%REAL% real, %SIM% simulated",

  overviewTitle: "Coverage overview",
  overviewSubtitle: "For operators and the Ministry of Technology and Communications",
  priorityTitle: "Priority areas",
  networksTitle: "Coverage by network",

  statMeasurements: "Measurements",
  statAreaMapped: "Area measured",
  statNoService: "Readings with no service",
  statDevices: "Contributing devices",
  // Not "Updated": the map is rebuilt every minute, so that word described
  // the aggregation while showing the age of the newest reading. With no
  // collector out today it read "Updated 4 h" over a map rebuilt seconds ago.
  statUpdated: "Last reading",
  statEnrolled: "%N% enrolled",
  live: "Live",
  railCollapse: "Hide details",
  railExpand: "Show details",
  livePaused: "Paused",
  liveResume: "Resume live updates",
  livePause: "Pause live updates",
  collectingNow: "uploaded recently",
  reportingExplain:
    "Phones that have uploaded in the last 10 minutes. A collector in a dead zone is still working and will look silent until they reach coverage.",
  collectorHere: "Collector",
  approxPosition: "Approximate position — hexagon centre, not an exact location.",
  ofCountry: "of Lao PDR",
  never: "Never",
  none: "None",

  coverage: "Coverage",
  allOperators: "All networks",
  signalState: "Signal status",
  allStates: "All signal levels",
  operator: "Network",

  areaCountry: "Country",
  areaProvince: "Province",
  areaDistrict: "District",
  areaVillage: "Village",
  areaAllCountry: "Whole country",
  areaAllProvinces: "All provinces",
  areaAllDistricts: "All districts",
  areaAllVillages: "All villages",
  areaClear: "Clear selection",
  areaNotMeasured: "Nothing has been measured here yet. The map claims nothing about this area.",
  areaGood: "Usable service",
  areaUnusable: "No usable service",
  areaMeasuredHere: "Measured here",
  areaOfArea: "of this area",
  areaDevices: "Contributing devices",
  areaLowConfidence:
    "Too few separate devices have measured this area to publish the details without risking identifying whoever travelled through.",
  areaApproximate:
    "This village has no published boundary. The circle shows everything within %R% of its recorded centre — an approximation, not a surveyed border.",
  areaSource: "Boundaries: %S%",
  areaTooLarge:
    "This area holds too many hexagons to draw at once. The shaded areas show coverage by district; choose one to see the detail.",
  areaDrillHint: "Select a shaded area to go deeper.",

  networkUnmeasured: "not measured yet",
  networksUnmeasuredNote:
    "No measurements exist for %N%. A phone can only measure the network its own SIM is attached to, so this means no collector carries that SIM — not that these networks have no coverage. Recruiting collectors on each network is what would fill this in.",

  loginTitle: "Sign in",
  loginWhy: "This platform holds national coverage data. Access is granted to named accounts.",
  loginWithGoogle: "Sign in with Google",
  loginChooseAccount: "Use your institutional account",
  loginApprovalNote:
    "New accounts are reviewed by a super administrator before access is granted.",
  loginSigningIn: "Signing in…",
  loginFailed: "Sign-in failed. Please try again.",
  loginScriptFailed:
    "Could not reach Google to sign in. Check the internet connection and try again.",
  loginNotConfigured:
    "Google sign-in is not configured on this server yet. Contact the administrator.",
  loginUnreachable:
    "Cannot reach the server. It may be restarting after an update — reload in a moment. Nothing needs configuring.",
  loginPendingTitle: "Waiting for approval",
  loginPendingBody:
    "Your account has been created and a super administrator has been asked to approve it. You will be able to sign in as soon as they do — there is nothing else you need to do.",
  loginRejectedTitle: "Access not granted",
  loginRejectedBody:
    "A super administrator has not granted this account access. If you believe this is a mistake, contact them directly.",
  loginUseAnother: "Use a different account",
  loginTeamTitle: "Developed by",
  loginAdvisorsTitle: "Advisors",
  signOut: "Sign out",

  navUsers: "Access",
  navUsersHint: "Approve who may sign in",
  usersTitle: "Access",
  usersSubtitle:
    "Signing in with Google proves who someone is. This page is where it is decided what they may see.",
  usersNone: "No accounts yet.",
  usersPendingCount: "%N% waiting",
  usersPerson: "Person",
  usersRole: "Role",
  usersStatus: "Status",
  usersRequested: "Requested",
  usersActions: "",
  usersApprove: "Approve",
  usersReject: "Reject",
  usersYou: "you",
  usersLastSuperAdmin: "the last super admin",
  usersRoleAdmin: "Admin",
  usersRoleOperator: "Network operator",
  usersNoNetwork: "no network set",
  usersChooseNetwork: "Which network does this account belong to?",
  usersChooseNetworkWhy:
    "A network account sees that network's coverage and the places with no service at all. It cannot see other networks, the collector fleet, or the national summary.",
  cancel: "Cancel",
  imageryLimit: "Satellite imagery is at full detail — Sentinel-2 photographs 10 m per pixel",
  mastLabel: "Observed cell",
  mastAccuracy: "Could be out by",
  mastHeardFrom: "Heard from",
  mastStrongest: "strongest",
  mastEstimate:
    "The centre of where collectors heard this cell — not the position of a mast. Readings taken along a road put this point on the road, so the mast itself may be well to one side. Two separate drives have placed the same cell about 2 km apart.",
  scopeBanner: "Showing %NETWORK% only",
  scopeBannerDetail:
    "Hexagons where %NETWORK% was measured, plus places with no network at all. Other operators are not shown, and an empty area means nobody has measured it rather than that there is no coverage.",
  usersRoleSuperAdmin: "Super admin",
  usersStatusPending: "Waiting",
  usersStatusApproved: "Approved",
  usersStatusRejected: "Rejected",

  legendPredicted: "Dashed and faded hexagons are predicted, not measured.",
  legendAreaShading:
    "A shaded province or district is coloured by what has been measured inside it, and shaded faintly when little of it has been. Pale does not mean poor coverage — it means little evidence.",
  legendCollector:
    "A collector's last reported hexagon — hollow once the phone has gone quiet. Not a live position.",
  legendMasts:
    "Cells the collectors have heard, drawn at the centre of the places they were heard — not mast positions. The pulsing ring is a marker, not the reach of a mast.",
  legendMastHalo:
    "The pale circle is how far the point could be out, not the area covered. It spans the whole stretch the cell was heard along, because from a road that is as far as the readings can narrow it — and the mast may sit off the road entirely, which no reading here can see.",
  legendMastVague:
    "Faded where that could be more than 2 km. Read these as somewhere along this stretch, not as a place.",
  // Short forms carry the warning at a glance; the full text above sits one
  // click away. The caveat has to survive the trim, so what is cut is the
  // reasoning, never the correction.
  legendMastsShort: "Cells heard by collectors — not mast positions.",
  legendMastHaloShort: "How far the point could be out — not the area covered.",
  legendMastVagueShort: "Faded: could be out by more than 2 km.",
  legendMore: "How to read this map",
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
  inspectorLocation: "Location",
  inspectorDirections: "Directions",

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

  brandSubtitle: "ແຜນທີ່ການຄອບຄຸມສັນຍານ · ສປປ ລາວ",
  sidebarNote: "ວັດແທກດ້ວຍໂທລະສັບທົ່ວໄປ ລວມທັງບ່ອນທີ່ບໍ່ມີສັນຍານເລີຍ.",
  navMapHint: "ອິນເຕີເນັດໃຊ້ໄດ້ຢູ່ໃສ",
  navOverview: "ພາບລວມ",
  navOverviewHint: "ຕ້ອງໃຊ້ຫຍັງເພື່ອແກ້ໄຂ",
  navPriority: "ພື້ນທີ່ບຸລິມະສິດ",
  navPriorityHint: "ບ່ອນບໍ່ມີສັນຍານ ຈັດລຳດັບແລ້ວ",
  navNetworks: "ເຄືອຂ່າຍ",
  navNetworksHint: "ການຄອບຄຸມຕາມຜູ້ໃຫ້ບໍລິການ",
  navCollectors: "ອຸປະກອນເກັບຂໍ້ມູນ",
  navCollectorsHint: "ໂທລະສັບທີ່ສົ່ງຂໍ້ມູນ",
  menu: "ເມນູ",
  basemapStreets: "ແຜນທີ່",
  basemapSatellite: "ພາບດາວທຽມ",
  terrain: "3D",
  terrainHint:
    "ອຽງແຜນທີ່ ແລະ ສະແດງພູມສັນຖານ. ຄວາມສູງຖືກຂະຫຍາຍເລັກນ້ອຍເພື່ອໃຫ້ເຫັນສັນພູໄດ້ຊັດ. ໃຊ້ຂໍ້ມູນຫຼາຍຂຶ້ນ.",

  collectorsTitle: "ອຸປະກອນເກັບຂໍ້ມູນ",
  collectorsSubtitle:
    "ໂທລະສັບທີ່ສົ່ງຂໍ້ມູນການວັດແທກ. ບໍ່ສະແດງຕຳແໜ່ງໃນໜ້ານີ້ — ເສັ້ນທາງທີ່ຜູ້ເກັບຂໍ້ມູນເດີນທາງ ແມ່ນສິ່ງທີ່ຮູບຫົກແຈໃນແຜນທີ່ມີໄວ້ເພື່ອປົກປິດ.",
  collectorsDevice: "ອຸປະກອນ",
  collectorsLastSeen: "ເຫັນຄັ້ງລ່າສຸດ",
  collectorsAccepted: "ຮັບແລ້ວ",
  collectorsRejected: "ຖືກປະຕິເສດ",
  collectorsRejectRate: "ອັດຕາປະຕິເສດ",
  collectorsSimulated: "ຈຳລອງ",
  collectorsNone: "ຍັງບໍ່ມີອຸປະກອນລົງທະບຽນ.",
  towersTitle: "ເຊວທີ່ໄດ້ຍິນ",
  towersSubtitle: "ສິ່ງທີ່ຜູ້ເກັບຂໍ້ມູນຮັບໄດ້, ຕາມຜູ້ໃຫ້ບໍລິການ — ບໍ່ແມ່ນລາຍການຊັບສິນຂອງຜູ້ໃຫ້ບໍລິການເອງ",
  towersOperator: "ຜູ້ໃຫ້ບໍລິການ",
  towersSites: "ຈຸດຕັ້ງ",
  towersPlaced: "ລະບຸຕຳແໜ່ງໄດ້",
  towersCells: "ເຊວ",
  towersNotMeasured: "ຍັງບໍ່ມີຜູ້ເກັບຂໍ້ມູນຖືຊິມນີ້",
  towersNote:
    "ເສົາໜຶ່ງມັກມີຫຼາຍເຊວ ດັ່ງນັ້ນ ເຊວ ນັບເສົາອາກາດ ບໍ່ແມ່ນນັບໂຄງສ້າງ. ຈຸດຕັ້ງ ຈັດກຸ່ມເຊວທີ່ໄດ້ຍິນຈາກບ່ອນດຽວກັນ; ການຈັດກຸ່ມນີ້ໜ້າເຊື່ອຖືກວ່າຕຳແໜ່ງດ່ຽວໆ ເພາະເຊວທີ່ຢູ່ເສົາດຽວກັນຈະໄດ້ຍິນຈາກບ່ອນດຽວກັນ ແລະ ການຄາດຄະເນຂອງພວກມັນຈະເໜັງໄປນຳກັນ — ແຕ່ກໍຍັງເປັນການນັບສິ່ງທີ່ໄດ້ຍິນ ບໍ່ແມ່ນນັບໂຄງສ້າງທີ່ໃຜໄດ້ເຫັນ. ສະເພາະເຊວທີ່ໄດ້ຍິນຈາກໄລຍະຫ່າງພຽງພໍຈຶ່ງລະບຸຕຳແໜ່ງໄດ້, ແລະ ທັງໝົດນີ້ແມ່ນສິ່ງທີ່ກອງເກັບຂໍ້ມູນໄດ້ຍິນ ບໍ່ແມ່ນສິ່ງທີ່ຜູ້ໃຫ້ບໍລິການເປັນເຈົ້າຂອງ.",
  collectorsDormant: "%N% ການລົງທະບຽນທີ່ຍັງບໍ່ມີການວັດແທກ",
  collectorsDormantWhy:
    "ສ່ວນຫຼາຍແມ່ນເຄື່ອງເກົ່າທີ່ຕິດຕັ້ງແອັບໃໝ່. ກະແຈລົງລາຍເຊັນເກັບຢູ່ໃນຮາດແວປອດໄພຂອງໂທລະສັບ ແລະ ສຳຮອງບໍ່ໄດ້ ດັ່ງນັ້ນແອັບທີ່ຕິດຕັ້ງໃໝ່ຈຶ່ງຕ້ອງລົງທະບຽນເປັນເຄື່ອງໃໝ່. ລາຍການເຫຼົ່ານີ້ຖືກເກັບໄວ້ ແຕ່ບໍ່ແມ່ນຜູ້ເກັບຂໍ້ມູນທີ່ໃຊ້ງານຢູ່.",
  collectorsRealCount: "ຈິງ %REAL% · ຈຳລອງ %SIM%",

  overviewTitle: "ພາບລວມການຄອບຄຸມ",
  overviewSubtitle: "ສຳລັບຜູ້ໃຫ້ບໍລິການ ແລະ ກະຊວງເຕັກໂນໂລຊີ ແລະ ການສື່ສານ",
  priorityTitle: "ພື້ນທີ່ບຸລິມະສິດ",
  networksTitle: "ການຄອບຄຸມຕາມເຄືອຂ່າຍ",

  statMeasurements: "ຈຳນວນການວັດແທກ",
  statAreaMapped: "ພື້ນທີ່ວັດແທກແລ້ວ",
  statNoService: "ຈຸດທີ່ບໍ່ມີສັນຍານ",
  statDevices: "ອຸປະກອນທີ່ຮ່ວມ",
  statUpdated: "ການວັດແທກຫຼ້າສຸດ",
  statEnrolled: "ລົງທະບຽນແລ້ວ %N%",
  live: "ສົດ",
  railCollapse: "ເຊື່ອງລາຍລະອຽດ",
  railExpand: "ສະແດງລາຍລະອຽດ",
  livePaused: "ຢຸດຊົ່ວຄາວ",
  liveResume: "ສືບຕໍ່ອັບເດດສົດ",
  livePause: "ຢຸດອັບເດດສົດ",
  collectingNow: "ອັບໂຫຼດເມື່ອບໍ່ດົນມານີ້",
  reportingExplain:
    "ໂທລະສັບທີ່ອັບໂຫຼດພາຍໃນ 10 ນາທີຜ່ານມາ. ຜູ້ເກັບຂໍ້ມູນຢູ່ເຂດບໍ່ມີສັນຍານຍັງເຮັດວຽກຢູ່ ແຕ່ຈະເບິ່ງຄືງຽບຈົນກວ່າຈະຮອດເຂດມີສັນຍານ.",
  collectorHere: "ຜູ້ເກັບຂໍ້ມູນ",
  approxPosition: "ຕຳແໜ່ງໂດຍປະມານ — ຈຸດກາງຂອງຮວງເຜິ້ງ, ບໍ່ແມ່ນຕຳແໜ່ງແທ້.",
  ofCountry: "ຂອງ ສປປ ລາວ",
  never: "ຍັງບໍ່ມີ",
  none: "ບໍ່ມີ",

  coverage: "ການຄອບຄຸມສັນຍານ",
  allOperators: "ທຸກເຄືອຂ່າຍ",
  signalState: "ສະຖານະສັນຍານ",
  allStates: "ທຸກລະດັບສັນຍານ",
  operator: "ເຄືອຂ່າຍ",

  areaCountry: "ປະເທດ",
  areaProvince: "ແຂວງ",
  areaDistrict: "ເມືອງ",
  areaVillage: "ບ້ານ",
  areaAllCountry: "ທົ່ວປະເທດ",
  areaAllProvinces: "ທຸກແຂວງ",
  areaAllDistricts: "ທຸກເມືອງ",
  areaAllVillages: "ທຸກບ້ານ",
  areaClear: "ລຶບການເລືອກ",
  areaNotMeasured: "ຍັງບໍ່ມີການວັດແທກຢູ່ນີ້. ແຜນທີ່ບໍ່ໄດ້ອ້າງອີງຫຍັງກ່ຽວກັບພື້ນທີ່ນີ້.",
  areaGood: "ບໍລິການໃຊ້ໄດ້",
  areaUnusable: "ໃຊ້ບໍລິການບໍ່ໄດ້",
  areaMeasuredHere: "ວັດແທກຢູ່ນີ້",
  areaOfArea: "ຂອງພື້ນທີ່ນີ້",
  areaDevices: "ອຸປະກອນທີ່ຮ່ວມ",
  areaLowConfidence:
    "ມີອຸປະກອນວັດແທກພື້ນທີ່ນີ້ໜ້ອຍເກີນໄປ ຈຶ່ງບໍ່ສະແດງລາຍລະອຽດ ເພື່ອປົກປ້ອງຄວາມເປັນສ່ວນຕົວຂອງຜູ້ເດີນທາງ.",
  areaApproximate:
    "ບ້ານນີ້ບໍ່ມີເສັ້ນເຂດແດນທີ່ເຜີຍແຜ່ໄວ້. ວົງມົນສະແດງທຸກຢ່າງພາຍໃນ %R% ຈາກຈຸດໃຈກາງທີ່ບັນທຶກໄວ້ — ເປັນການປະມານ ບໍ່ແມ່ນເສັ້ນເຂດແດນຈິງ.",
  areaSource: "ເສັ້ນເຂດແດນ: %S%",
  areaTooLarge:
    "ພື້ນທີ່ນີ້ມີຮູບຫົກແຈຫຼາຍເກີນໄປທີ່ຈະສະແດງພ້ອມກັນ. ພື້ນທີ່ທີ່ແຕ້ມສີສະແດງການຄອບຄຸມຕາມເມືອງ; ເລືອກເມືອງໜຶ່ງເພື່ອເບິ່ງລາຍລະອຽດ.",
  areaDrillHint: "ເລືອກພື້ນທີ່ທີ່ແຕ້ມສີເພື່ອເບິ່ງລະອຽດຂຶ້ນ.",

  networkUnmeasured: "ຍັງບໍ່ໄດ້ວັດແທກ",
  networksUnmeasuredNote:
    "ຍັງບໍ່ມີການວັດແທກສຳລັບ %N%. ໂທລະສັບວັດແທກໄດ້ສະເພາະເຄືອຂ່າຍທີ່ຊິມຂອງຕົນເອງເຊື່ອມຕໍ່ຢູ່ ດັ່ງນັ້ນນີ້ໝາຍຄວາມວ່າຍັງບໍ່ມີຜູ້ເກັບຂໍ້ມູນຄົນໃດໃຊ້ຊິມນັ້ນ — ບໍ່ແມ່ນວ່າເຄືອຂ່າຍເຫຼົ່ານີ້ບໍ່ມີສັນຍານ. ການຊອກຫາຜູ້ເກັບຂໍ້ມູນໃນແຕ່ລະເຄືອຂ່າຍຈະຊ່ວຍຕື່ມຂໍ້ມູນສ່ວນນີ້.",

  loginTitle: "ເຂົ້າສູ່ລະບົບ",
  loginWhy: "ລະບົບນີ້ເກັບຂໍ້ມູນການຄອບຄຸມສັນຍານລະດັບຊາດ. ອະນຸຍາດໃຫ້ສະເພາະບັນຊີທີ່ໄດ້ຮັບການອະນຸມັດ.",
  loginWithGoogle: "ເຂົ້າສູ່ລະບົບດ້ວຍ Google",
  loginChooseAccount: "ໃຊ້ບັນຊີຂອງສະຖາບັນ",
  loginApprovalNote: "ບັນຊີໃໝ່ຕ້ອງໄດ້ຮັບການອະນຸມັດຈາກຜູ້ດູແລລະບົບສູງສຸດກ່ອນ.",
  loginSigningIn: "ກຳລັງເຂົ້າສູ່ລະບົບ…",
  loginFailed: "ເຂົ້າສູ່ລະບົບບໍ່ສຳເລັດ. ກະລຸນາລອງໃໝ່.",
  loginScriptFailed: "ຕິດຕໍ່ Google ບໍ່ໄດ້. ກະລຸນາກວດສອບອິນເຕີເນັດ ແລ້ວລອງໃໝ່.",
  loginNotConfigured: "ເຊີບເວີຍັງບໍ່ໄດ້ຕັ້ງຄ່າການເຂົ້າສູ່ລະບົບດ້ວຍ Google. ກະລຸນາຕິດຕໍ່ຜູ້ດູແລລະບົບ.",
  loginUnreachable:
    "ຕິດຕໍ່ເຊີບເວີບໍ່ໄດ້. ອາດກຳລັງເລີ່ມໃໝ່ຫຼັງອັບເດດ — ກະລຸນາໂຫຼດໜ້າໃໝ່ໃນອີກບໍ່ດົນ. ບໍ່ຈຳເປັນຕ້ອງຕັ້ງຄ່າຫຍັງ.",
  loginPendingTitle: "ກຳລັງລໍຖ້າການອະນຸມັດ",
  loginPendingBody:
    "ສ້າງບັນຊີຂອງທ່ານແລ້ວ ແລະ ໄດ້ແຈ້ງໃຫ້ຜູ້ດູແລລະບົບສູງສຸດອະນຸມັດ. ທ່ານຈະເຂົ້າໃຊ້ໄດ້ທັນທີທີ່ໄດ້ຮັບການອະນຸມັດ — ບໍ່ຕ້ອງເຮັດຫຍັງເພີ່ມ.",
  loginRejectedTitle: "ບໍ່ໄດ້ຮັບອະນຸຍາດ",
  loginRejectedBody:
    "ຜູ້ດູແລລະບົບສູງສຸດບໍ່ໄດ້ອະນຸຍາດໃຫ້ບັນຊີນີ້ເຂົ້າໃຊ້. ຫາກທ່ານຄິດວ່າເປັນຄວາມຜິດພາດ ກະລຸນາຕິດຕໍ່ຜູ້ດູແລລະບົບໂດຍກົງ.",
  loginUseAnother: "ໃຊ້ບັນຊີອື່ນ",
  loginTeamTitle: "ພັດທະນາໂດຍ",
  loginAdvisorsTitle: "ທີ່ປຶກສາ",
  signOut: "ອອກຈາກລະບົບ",

  navUsers: "ສິດເຂົ້າໃຊ້",
  navUsersHint: "ອະນຸມັດຜູ້ທີ່ເຂົ້າໃຊ້ໄດ້",
  usersTitle: "ສິດເຂົ້າໃຊ້",
  usersSubtitle:
    "ການເຂົ້າສູ່ລະບົບດ້ວຍ Google ພຽງແຕ່ຢືນຢັນວ່າເປັນໃຜ. ໜ້ານີ້ແມ່ນບ່ອນຕັດສິນວ່າເຂົາເຈົ້າເຫັນຫຍັງໄດ້.",
  usersNone: "ຍັງບໍ່ມີບັນຊີ.",
  usersPendingCount: "ລໍຖ້າ %N%",
  usersPerson: "ຜູ້ໃຊ້",
  usersRole: "ບົດບາດ",
  usersStatus: "ສະຖານະ",
  usersRequested: "ຮ້ອງຂໍເມື່ອ",
  usersActions: "",
  usersApprove: "ອະນຸມັດ",
  usersReject: "ປະຕິເສດ",
  usersYou: "ທ່ານ",
  usersLastSuperAdmin: "ຜູ້ດູແລສູງສຸດຄົນສຸດທ້າຍ",
  usersRoleAdmin: "ຜູ້ດູແລ",
  usersRoleOperator: "ຜູ້ໃຫ້ບໍລິການເຄືອຂ່າຍ",
  usersNoNetwork: "ຍັງບໍ່ໄດ້ກຳນົດເຄືອຂ່າຍ",
  usersChooseNetwork: "ບັນຊີນີ້ຂຶ້ນກັບເຄືອຂ່າຍໃດ?",
  usersChooseNetworkWhy:
    "ບັນຊີເຄືອຂ່າຍຈະເຫັນການຄຸ້ມຄອງຂອງເຄືອຂ່າຍນັ້ນ ແລະ ບ່ອນທີ່ບໍ່ມີສັນຍານເລີຍ. ຈະບໍ່ເຫັນເຄືອຂ່າຍອື່ນ, ກອງເກັບຂໍ້ມູນ, ຫຼື ສະຫຼຸບລວມທົ່ວປະເທດ.",
  cancel: "ຍົກເລີກ",
  imageryLimit: "ພາບຖ່າຍດາວທຽມລະອຽດເຕັມທີ່ແລ້ວ — Sentinel-2 ຖ່າຍໄດ້ 10 ແມັດຕໍ່ຈຸດ",
  mastLabel: "ເຊວທີ່ສັງເກດເຫັນ",
  mastAccuracy: "ອາດຄາດເຄື່ອນເຖິງ",
  mastHeardFrom: "ໄດ້ຍິນຈາກ",
  mastStrongest: "ແຮງສຸດ",
  mastEstimate:
    "ຈຸດກາງຂອງບ່ອນທີ່ຜູ້ເກັບຂໍ້ມູນໄດ້ຍິນເຊວນີ້ — ບໍ່ແມ່ນຕຳແໜ່ງຂອງເສົາສັນຍານ. ການວັດແທກທີ່ເກັບຕາມເສັ້ນທາງ ຈະເຮັດໃຫ້ຈຸດນີ້ຢູ່ເທິງເສັ້ນທາງ ດັ່ງນັ້ນເສົາຈິງອາດຢູ່ຫ່າງອອກໄປທາງຂ້າງ. ການຂັບເກັບຂໍ້ມູນສອງຄັ້ງແຍກກັນ ວາງເຊວດຽວກັນຫ່າງກັນປະມານ 2 ກິໂລແມັດ.",
  scopeBanner: "ສະແດງສະເພາະ %NETWORK%",
  scopeBannerDetail:
    "ຮວງເຜິ້ງທີ່ວັດແທກ %NETWORK% ໄດ້, ພ້ອມທັງບ່ອນທີ່ບໍ່ມີເຄືອຂ່າຍເລີຍ. ບໍ່ສະແດງຜູ້ໃຫ້ບໍລິການອື່ນ, ແລະ ພື້ນທີ່ຫວ່າງໝາຍຄວາມວ່າຍັງບໍ່ມີໃຜວັດແທກ ບໍ່ແມ່ນວ່າບໍ່ມີສັນຍານ.",
  usersRoleSuperAdmin: "ຜູ້ດູແລສູງສຸດ",
  usersStatusPending: "ລໍຖ້າ",
  usersStatusApproved: "ອະນຸມັດແລ້ວ",
  usersStatusRejected: "ປະຕິເສດ",

  legendPredicted: "ຮູບຫົກແຈທີ່ເປັນເສັ້ນຂີດ ແລະ ຈາງ ແມ່ນການຄາດຄະເນ ບໍ່ແມ່ນການວັດແທກ.",
  legendAreaShading:
    "ແຂວງ ຫຼື ເມືອງ ທີ່ແຕ້ມສີ ໃຊ້ສີຕາມສິ່ງທີ່ວັດແທກໄດ້ພາຍໃນ ແລະ ຈະຈາງລົງເມື່ອວັດແທກໄດ້ໜ້ອຍ. ສີຈາງບໍ່ໄດ້ໝາຍຄວາມວ່າສັນຍານບໍ່ດີ — ແຕ່ໝາຍຄວາມວ່າມີຂໍ້ມູນໜ້ອຍ.",
  legendCollector:
    "ຮວງເຜິ້ງຫຼ້າສຸດທີ່ຜູ້ເກັບຂໍ້ມູນລາຍງານ — ເປັນວົງເປົ່າເມື່ອໂທລະສັບງຽບໄປ. ບໍ່ແມ່ນຕຳແໜ່ງສົດ.",
  legendMasts:
    "ເຊວທີ່ຜູ້ເກັບຂໍ້ມູນໄດ້ຍິນ, ແຕ້ມຢູ່ຈຸດກາງຂອງບ່ອນທີ່ໄດ້ຍິນ — ບໍ່ແມ່ນຕຳແໜ່ງເສົາສັນຍານ. ວົງທີ່ກະພິບເປັນພຽງເຄື່ອງໝາຍ ບໍ່ແມ່ນໄລຍະທີ່ເສົາສົ່ງເຖິງ.",
  legendMastHalo:
    "ວົງກົມສີຈາງ ຄືໄລຍະທີ່ຈຸດນີ້ອາດຄາດເຄື່ອນໄດ້ ບໍ່ແມ່ນພື້ນທີ່ໃຫ້ບໍລິການ. ມັນກວມທັງໄລຍະທາງທີ່ໄດ້ຍິນເຊວນີ້ ເພາະການເກັບຕາມເສັ້ນທາງ ຈຳກັດໄດ້ພຽງເທົ່ານັ້ນ — ແລະ ເສົາອາດຢູ່ນອກເສັ້ນທາງເລີຍ ຊຶ່ງການວັດແທກນີ້ບໍ່ສາມາດເຫັນໄດ້.",
  legendMastVague:
    "ຈາງລົງ ເມື່ອຄາດເຄື່ອນອາດເກີນ 2 ກິໂລແມັດ. ໃຫ້ອ່ານວ່າຢູ່ຕາມໄລຍະນີ້ ບໍ່ແມ່ນຈຸດໃດຈຸດໜຶ່ງ.",
  legendMastsShort: "ເຊວທີ່ຜູ້ເກັບຂໍ້ມູນໄດ້ຍິນ — ບໍ່ແມ່ນຕຳແໜ່ງເສົາ.",
  legendMastHaloShort: "ໄລຍະທີ່ຈຸດນີ້ອາດຄາດເຄື່ອນ — ບໍ່ແມ່ນພື້ນທີ່ໃຫ້ບໍລິການ.",
  legendMastVagueShort: "ຈາງ: ອາດຄາດເຄື່ອນເກີນ 2 ກິໂລແມັດ.",
  legendMore: "ວິທີອ່ານແຜນທີ່ນີ້",
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
  inspectorLocation: "ທີ່ຕັ້ງ",
  inspectorDirections: "ນຳທາງໄປ",

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
