import QtQuick 6.7

QtObject {
    readonly property string name: "Night Blossom"

    readonly property color backgroundA: "#07050d"
    readonly property color backgroundB: "#120915"
    readonly property color backgroundC: "#260e24"

    readonly property color surface: "#c6150e1d"
    readonly property color surfaceSoft: "#ad0d0913"
    readonly property color surfaceStrong: "#d91d1325"
    readonly property color surfaceRaised: "#ed25162d"
    readonly property color surfaceTop: "#b72d2036"
    readonly property color surfaceBottom: "#d0100a17"
    readonly property color surfaceStrongTop: "#cc37243d"
    readonly property color surfaceStrongBottom: "#dd160d20"

    readonly property color border: "#765e4b68"
    readonly property color borderSoft: "#4f49334f"
    readonly property color borderStrong: "#b78a667f"
    readonly property color divider: "#3d493445"
    readonly property color text: "#fff8fc"
    readonly property color muted: "#d8c9d5"
    readonly property color subtle: "#a98fa4"
    readonly property color faint: "#755f73"

    readonly property color primary: "#ea3c88"
    readonly property color primaryBright: "#ff78b6"
    readonly property color primaryHot: "#ff4c9a"
    readonly property color primaryDeep: "#9c174f"
    readonly property color primarySoft: "#4dea3c88"
    readonly property color hover: "#22ff8fc2"
    readonly property color success: "#60dc91"
    readonly property color warning: "#ffc66d"
    readonly property color danger: "#ff536f"
    readonly property color consoleBackground: "#ee09060e"
    readonly property color shadow: "#d5000000"
    readonly property color innerHighlight: "#2d8a5a7d"
    readonly property color focusColor: "#ffff9ac8"
    readonly property color primaryText: "#ffffff"

    readonly property color appBorder: "#4c7b526d"
    readonly property color titleBarSurface: "#f1090710"
    readonly property color titleBarButtonHover: "#20ffffff"
    readonly property color titleBarCloseHover: "#c9481f43"
    readonly property color logoCapsuleSurface: "#45160b22"

    readonly property color panelTop: "#e5322338"
    readonly property color panelMiddle: "#d81d1226"
    readonly property color panelBottom: "#dc0e0913"
    readonly property color panelSoftTop: "#d81c1225"
    readonly property color panelSoftMiddle: "#c8120b18"
    readonly property color panelSoftBottom: "#ce08060e"
    readonly property color panelStrongTop: "#ee3d2a46"
    readonly property color panelStrongMiddle: "#e625172f"
    readonly property color panelStrongBottom: "#e6120a18"
    readonly property color panelTopHighlight: "#78ffffff"
    readonly property color panelInnerBorder: "#2d8a5a7d"
    readonly property color panelStrongInnerBorder: "#5fb9899f"
    readonly property color panelOverlay: "#0affffff"
    readonly property color panelStrongOverlay: "#13000000"
    readonly property color panelGlowShadow: "#c9561546"
    readonly property real panelNoiseSoftOpacity: 0.060
    readonly property real panelNoiseOpacity: 0.068
    readonly property real panelNoiseStrongOpacity: 0.078
    readonly property real panelHighlightSoftOpacity: 0.22
    readonly property real panelHighlightOpacity: 0.28
    readonly property real panelHighlightStrongOpacity: 0.34
    readonly property real panelOverlaySoftOpacity: 0.18
    readonly property real panelOverlayOpacity: 0.24

    readonly property color primaryButtonBorder: "#ff78b6"
    readonly property color primaryButtonHoverBorder: "#ffffd5e8"
    readonly property color primaryButtonTop: "#fff04b95"
    readonly property color primaryButtonMiddle: "#ffe22f7f"
    readonly property color primaryButtonBottom: "#ffae1456"
    readonly property color primaryButtonHoverTop: "#ffff68aa"
    readonly property color primaryButtonHoverMiddle: "#fff13f8d"
    readonly property color primaryButtonHoverBottom: "#ffd51f6c"
    readonly property color primaryButtonShadow: "#99250018"
    readonly property color primaryButtonHoverShadow: "#ccff2d82"
    readonly property color primaryButtonSheenTransparent: "#00ffffff"
    readonly property color primaryButtonSheen: "#8affffff"

    readonly property color ghostSurface: "#a9251428"
    readonly property color ghostHoverSurface: "#d73a1c3b"
    readonly property color ghostPressedSurface: "#d91e1022"
    readonly property color ghostShadow: "#a7d61f69"

    readonly property color fieldSurface: "#c60c0811"
    readonly property color fieldHoverSurface: "#d3160c1b"
    readonly property color fieldFocusSurface: "#e21b101f"
    readonly property color comboSurfaceOpen: "#ed201328"
    readonly property color comboHoverSurface: "#d21c1021"
    readonly property color comboPopupSurface: surfaceRaised
    readonly property color comboHighlight: primaryDeep

    readonly property color checkboxSurface: "#c60c0811"
    readonly property color checkboxHoverSurface: "#a22c1830"
    readonly property color checkboxCheckedSurface: primary
    readonly property color switchTrackOff: "#423043"
    readonly property color sliderTrack: "#5b38263d"

    readonly property color navHoverSurface: "#56442543"
    readonly property color navActiveGlow: "#efff2e83"
    readonly property color navActiveTop: "#e8c3216d"
    readonly property color navActiveMiddle: "#d8ad195e"
    readonly property color navActiveBottom: "#d876123f"

    readonly property color rowHover: "#25ff82ba"
    readonly property color rowSelectedSurface: primarySoft
    readonly property color previewSurface: "#d908050b"
    readonly property color previewSurfaceSoft: "#c006040a"

    readonly property color helpCategorySelected: "#e6ff4d9a"
    readonly property color helpCategoryHover: "#d7251435"
    readonly property color helpCategorySurface: "#bc120a20"
    readonly property color helpBadgeSelected: "#34ffffff"
    readonly property color helpBadge: "#22ffffff"
    readonly property color helpBadgeBorder: "#55ffffff"
    readonly property color helpTopicSelected: "#d7351a42"
    readonly property color helpTopicHover: "#c72a1435"
    readonly property color helpTopicSurface: "#a1120920"
    readonly property color stepBadge: "#35ff6fac"
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
    readonly property real backdropTopBranchOpacity: 0.78
    readonly property real backdropBottomBranchOpacity: 0.62
    readonly property real sidebarBranchOpacity: 0.40
    readonly property real sidebarCompactBranchOpacity: 0.30
}
