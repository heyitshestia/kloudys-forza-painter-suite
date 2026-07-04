import QtQuick 6.7

QtObject {
    readonly property string name: "Ko-fi Cherry"

    readonly property color backgroundA: "#10070d"
    readonly property color backgroundB: "#221018"
    readonly property color backgroundC: "#3b1728"

    readonly property color surface: "#cf24151f"
    readonly property color surfaceSoft: "#b3150b14"
    readonly property color surfaceStrong: "#df3c2430"
    readonly property color surfaceRaised: "#ef4a2c36"
    readonly property color surfaceTop: "#ba66475a"
    readonly property color surfaceBottom: "#df160b1c"
    readonly property color surfaceStrongTop: "#d9795568"
    readonly property color surfaceStrongBottom: "#e0251128"

    readonly property color border: "#a87a5e80"
    readonly property color borderSoft: "#68513e5c"
    readonly property color borderStrong: "#e2a57d9a"
    readonly property color divider: "#5a46364d"
    readonly property color text: "#fff8fc"
    readonly property color muted: "#ead1df"
    readonly property color subtle: "#c09aad"
    readonly property color faint: "#856778"

    readonly property color primary: "#ff5b9d"
    readonly property color primaryBright: "#ffc1d8"
    readonly property color primaryHot: "#ff79b4"
    readonly property color primaryDeep: "#b91d5d"
    readonly property color primarySoft: "#55ff7fb1"
    readonly property color hover: "#2dffc6dd"
    readonly property color success: "#60dc91"
    readonly property color warning: "#ffc66d"
    readonly property color danger: "#ff536f"
    readonly property color consoleBackground: "#ee09060e"
    readonly property color shadow: "#d5000000"
    readonly property color innerHighlight: "#2d8a5a7d"
    readonly property color focusColor: "#ffff9ac8"
    readonly property color primaryText: "#ffffff"

    readonly property color appBorder: "#5f9b6d7a"
    readonly property color titleBarSurface: "#f412080f"
    readonly property color titleBarButtonHover: "#24ffffff"
    readonly property color titleBarCloseHover: "#d4522552"
    readonly property color logoCapsuleSurface: "#5421132d"

    readonly property color panelTop: "#e83d2a42"
    readonly property color panelMiddle: "#d82a1730"
    readonly property color panelBottom: "#dc160d1a"
    readonly property color panelSoftTop: "#dc2c192d"
    readonly property color panelSoftMiddle: "#c91a0e1f"
    readonly property color panelSoftBottom: "#ce0d0713"
    readonly property color panelStrongTop: "#f05f3c5c"
    readonly property color panelStrongMiddle: "#e23b2442"
    readonly property color panelStrongBottom: "#e51f1124"
    readonly property color panelTopHighlight: "#82ffffff"
    readonly property color panelInnerBorder: "#338a5a7d"
    readonly property color panelStrongInnerBorder: "#72ffd0bd"
    readonly property color panelOverlay: "#0effffff"
    readonly property color panelStrongOverlay: "#15000000"
    readonly property color panelGlowShadow: "#ccff6b8c"
    readonly property real panelNoiseSoftOpacity: 0.064
    readonly property real panelNoiseOpacity: 0.072
    readonly property real panelNoiseStrongOpacity: 0.084
    readonly property real panelHighlightSoftOpacity: 0.24
    readonly property real panelHighlightOpacity: 0.30
    readonly property real panelHighlightStrongOpacity: 0.38
    readonly property real panelOverlaySoftOpacity: 0.18
    readonly property real panelOverlayOpacity: 0.24

    readonly property color primaryButtonBorder: primaryBright
    readonly property color primaryButtonHoverBorder: "#ffffe7f0"
    readonly property color primaryButtonTop: "#ffff6fb0"
    readonly property color primaryButtonMiddle: "#fff04798"
    readonly property color primaryButtonBottom: "#ffc72268"
    readonly property color primaryButtonHoverTop: "#ffff86bf"
    readonly property color primaryButtonHoverMiddle: "#ffff5aa4"
    readonly property color primaryButtonHoverBottom: "#ffe12a78"
    readonly property color primaryButtonShadow: "#a62a001c"
    readonly property color primaryButtonHoverShadow: "#d6ff5a9f"
    readonly property color primaryButtonSheenTransparent: "#00ffffff"
    readonly property color primaryButtonSheen: "#92ffffff"

    readonly property color ghostSurface: "#b92d1730"
    readonly property color ghostHoverSurface: "#dc4a2948"
    readonly property color ghostPressedSurface: "#df271530"
    readonly property color ghostShadow: "#b7ff407d"

    readonly property color fieldSurface: "#ce150b16"
    readonly property color fieldHoverSurface: "#d924131f"
    readonly property color fieldFocusSurface: "#e6321b2a"
    readonly property color comboSurfaceOpen: "#f03d2240"
    readonly property color comboHoverSurface: "#dc2b1728"
    readonly property color comboPopupSurface: surfaceRaised
    readonly property color comboHighlight: primaryDeep

    readonly property color checkboxSurface: "#ce150b16"
    readonly property color checkboxHoverSurface: "#b43d2440"
    readonly property color checkboxCheckedSurface: primary
    readonly property color switchTrackOff: "#50374a"
    readonly property color sliderTrack: "#7146304d"

    readonly property color navHoverSurface: "#6850314f"
    readonly property color navActiveGlow: "#efff73aa"
    readonly property color navActiveTop: "#f1dc5890"
    readonly property color navActiveMiddle: "#dfbf3576"
    readonly property color navActiveBottom: "#da8c2454"

    readonly property color rowHover: "#32ffa9d2"
    readonly property color rowSelectedSurface: primarySoft
    readonly property color previewSurface: "#df100810"
    readonly property color previewSurfaceSoft: "#c90b050d"

    readonly property color helpCategorySelected: "#ecff6fb0"
    readonly property color helpCategoryHover: "#dc321940"
    readonly property color helpCategorySurface: "#bf180c26"
    readonly property color helpBadgeSelected: "#38ffffff"
    readonly property color helpBadge: "#24ffffff"
    readonly property color helpBadgeBorder: "#5cffffff"
    readonly property color helpTopicSelected: "#dc47234f"
    readonly property color helpTopicHover: "#cf321940"
    readonly property color helpTopicSurface: "#ad160b26"
    readonly property color stepBadge: "#42ff86bd"
    readonly property color richAccent: primaryBright

    readonly property color backdropOverlayTop: "#0d000000"
    readonly property color backdropOverlayMiddle: "#05000000"
    readonly property color backdropOverlayBottom: "#35000000"

    readonly property string backdropBaseFile: "night-blossom-base.png"
    readonly property string backdropBranchTopFile: "branch-top.png"
    readonly property string backdropBranchBottomFile: "branch-bottom.png"
    readonly property string backdropPetalFile: "petal.png"
    readonly property string logoFile: "kfps-logo.png"
    readonly property bool backdropBranchesVisible: true
    readonly property bool backdropPetalsVisible: true
    readonly property real backdropTopBranchOpacity: 0.82
    readonly property real backdropBottomBranchOpacity: 0.66
    readonly property real sidebarBranchOpacity: 0.44
    readonly property real sidebarCompactBranchOpacity: 0.34
}
