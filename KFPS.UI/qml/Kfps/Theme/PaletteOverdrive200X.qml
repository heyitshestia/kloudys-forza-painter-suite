import QtQuick 6.7

QtObject {
    readonly property string name: "Overdrive 200X"
    readonly property bool supporterOnly: true
    readonly property string iconFolder: "icons-carbon"
    readonly property bool iconColorize: true
    readonly property color iconTint: signalPrimary

    // Optional capabilities consumed generically by shared UI components.
    readonly property string backdropComponentFile: "../themes/overdrive/OverdriveBackdrop.qml"
    readonly property string foregroundComponentFile: "../themes/overdrive/OverdriveForeground.qml"
    readonly property string pageTransitionComponentFile: "../themes/overdrive/OverdrivePageTransition.qml"
    readonly property bool equipmentAccentsEnabled: true
    readonly property bool ambientScanEnabled: true
    readonly property bool controlSignalEnabled: true
    readonly property bool navSignalEnabled: true
    readonly property bool panelLocatorEnabled: true
    readonly property bool headerSignalEnabled: true
    readonly property string logoDialFile: "themes/overdrive-200x/overdrive-logo-dial.svg"
    readonly property real logoDialOpacity: 0.94
    readonly property bool logoColorize: true
    readonly property color logoTint: "#c9f9ff"
    readonly property color signalPrimary: "#62efff"
    readonly property color signalSecondary: "#ffc45a"
    readonly property color signalDanger: "#ff6074"
    readonly property color signalSuccess: "#aeea72"
    readonly property color signalOff: "#3b294047"
    readonly property color transitionSweep: "#d9fbff"
    readonly property color transitionTrail: "#ffc45a"
    readonly property real interactionSweepDuration: 210
    readonly property real interactionSweepWidth: 0.24
    readonly property real pageTransitionDuration: 360
    readonly property real locatorOpacity: 0.92

    readonly property color backgroundA: "#05080a"
    readonly property color backgroundB: "#09151a"
    readonly property color backgroundC: "#182126"

    readonly property color surface: "#d00a1216"
    readonly property color surfaceSoft: "#bd071014"
    readonly property color surfaceStrong: "#ed101c22"
    readonly property color surfaceRaised: "#f217252b"
    readonly property color surfaceTop: "#d324343b"
    readonly property color surfaceBottom: "#df071014"
    readonly property color surfaceStrongTop: "#f02e424a"
    readonly property color surfaceStrongBottom: "#f009151a"

    readonly property color border: "#8b799398"
    readonly property color borderSoft: "#5863767b"
    readonly property color borderStrong: "#db9fdde4"
    readonly property color divider: "#5f506970"
    readonly property color text: "#f4fbfc"
    readonly property color muted: "#d3e2e5"
    readonly property color subtle: "#a8bdc2"
    readonly property color faint: "#71868b"

    readonly property color primary: "#25cfe4"
    readonly property color primaryBright: "#62efff"
    readonly property color primaryHot: "#baf8ff"
    readonly property color primaryDeep: "#087f91"
    readonly property color primarySoft: "#4325cfe4"
    readonly property color hover: "#2862efff"
    readonly property color success: "#aeea72"
    readonly property color warning: "#ffc45a"
    readonly property color danger: "#ff6074"
    readonly property color classificationHandmade: "#ff9fce"
    readonly property color classificationToolmade: "#8fd8ff"
    readonly property color consoleBackground: "#f0050b0e"
    readonly property color shadow: "#e9000000"
    readonly property color innerHighlight: "#3e8cb9c0"
    readonly property color focusColor: "#dffaff"
    readonly property color primaryText: "#f8fdff"

    readonly property color appBorder: "#a88ba9ae"
    readonly property color titleBarSurface: "#f3060a0d"
    readonly property color titleBarButtonHover: "#2662efff"
    readonly property color titleBarCloseHover: "#d6522130"
    readonly property color logoCapsuleSurface: "#b409161b"

    readonly property color panelTop: "#df203139"
    readonly property color panelMiddle: "#db111d22"
    readonly property color panelBottom: "#e4081014"
    readonly property color panelSoftTop: "#ce17252b"
    readonly property color panelSoftMiddle: "#c40c171c"
    readonly property color panelSoftBottom: "#d2070e12"
    readonly property color panelStrongTop: "#f12a3d45"
    readonly property color panelStrongMiddle: "#e817272d"
    readonly property color panelStrongBottom: "#ed091317"
    readonly property color panelTopHighlight: "#80e8fbff"
    readonly property color panelInnerBorder: "#4f82adb4"
    readonly property color panelStrongInnerBorder: "#a762efff"
    readonly property color panelOverlay: "#0bffffff"
    readonly property color panelStrongOverlay: "#16000000"
    readonly property color panelGlowShadow: "#b825cfe4"
    readonly property color panelConvexLeftHighlight: "#32e9fbff"
    readonly property color panelConvexRightShadow: "#84000000"
    readonly property color panelConvexBottomShadow: "#92000000"
    readonly property color panelConvexCenterGlow: "#0b62efff"
    readonly property real panelNoiseSoftOpacity: 0.045
    readonly property real panelNoiseOpacity: 0.062
    readonly property real panelNoiseStrongOpacity: 0.080
    readonly property real panelHighlightSoftOpacity: 0.20
    readonly property real panelHighlightOpacity: 0.28
    readonly property real panelHighlightStrongOpacity: 0.38
    readonly property real panelOverlaySoftOpacity: 0.14
    readonly property real panelOverlayOpacity: 0.22

    readonly property color primaryButtonBorder: "#9bdde5"
    readonly property color primaryButtonHoverBorder: "#e6fcff"
    readonly property color primaryButtonTop: "#c6335b65"
    readonly property color primaryButtonMiddle: "#bd176876"
    readonly property color primaryButtonBottom: "#c0085361"
    readonly property color primaryButtonHoverTop: "#dc4c7b85"
    readonly property color primaryButtonHoverMiddle: "#d3228190"
    readonly property color primaryButtonHoverBottom: "#d10a6978"
    readonly property color primaryButtonShadow: "#c0000000"
    readonly property color primaryButtonHoverShadow: "#b962efff"
    readonly property color primaryButtonSheenTransparent: "#00dffaff"
    readonly property color primaryButtonSheen: "#b5e8fdff"
    readonly property color primaryButtonLip: "#d0053540"
    readonly property color primaryButtonLipPressed: "#e004222a"
    readonly property color primaryButtonGlassTop: "#8fe8fbff"
    readonly property color primaryButtonGlassMiddle: "#2837c4d6"
    readonly property color primaryButtonInnerShadow: "#7a000000"
    readonly property string primaryButtonTextureFile: "themes/overdrive-200x/overdrive-panel-texture.png"
    readonly property real primaryButtonTextureOpacity: 0.15
    readonly property string primaryButtonLensOverlayFile: "themes/overdrive-200x/overdrive-button-lens.svg"
    readonly property real primaryButtonLensOverlayOpacity: 0.72
    readonly property color primaryButtonText: "#f8fdff"
    readonly property real buttonGlassBackdropOpacity: 0.70
    readonly property real buttonGlassBackdropBlur: 0.20
    readonly property int buttonGlassBackdropBlurMax: 36
    readonly property real buttonGlassBackdropBlurMultiplier: 0.52
    readonly property real buttonGlassBackdropBrightness: -0.025
    readonly property real buttonGlassBackdropContrast: 0.30
    readonly property real buttonGlassBackdropSaturation: 0.88
    readonly property real buttonGlassBackdropDownsample: 0.86
    readonly property real buttonGlassLensOpacity: 0.82
    readonly property real buttonGlassLensInsetX: 0.13
    readonly property real buttonGlassLensInsetY: 0.24
    readonly property real buttonGlassLensOffsetX: -0.018
    readonly property real buttonGlassLensOffsetY: -0.055
    readonly property real buttonGlassLensBlur: 0.025
    readonly property real buttonGlassLensContrast: 0.46
    readonly property real buttonGlassLensSaturation: 1.12
    readonly property color buttonGlassLensLeftHighlight: "#32f2fdff"
    readonly property color buttonGlassLensCenterHighlight: "#1762efff"
    readonly property color buttonGlassLensRightShadow: "#6a000000"

    readonly property color ghostSurface: "#a20b171c"
    readonly property color ghostHoverSurface: "#d2193038"
    readonly property color ghostPressedSurface: "#e0071419"
    readonly property color ghostShadow: "#b0000000"

    readonly property color fieldSurface: "#e0061014"
    readonly property color fieldHoverSurface: "#ed0d1d23"
    readonly property color fieldFocusSurface: "#f112252c"
    readonly property color comboSurfaceOpen: "#f3152930"
    readonly property color comboHoverSurface: "#e7112228"
    readonly property color comboPopupSurface: "#f2081115"
    readonly property color comboHighlight: "#087f91"

    readonly property color checkboxSurface: "#e0061014"
    readonly property color checkboxHoverSurface: "#ca173039"
    readonly property color checkboxCheckedSurface: primary
    readonly property color switchTrackOff: "#38484d"
    readonly property color sliderTrack: "#4d677077"

    readonly property color navHoverSurface: "#6720353c"
    readonly property color navActiveGlow: "#dc25cfe4"
    readonly property color navActiveTop: "#dc1e6f7d"
    readonly property color navActiveMiddle: "#d013505b"
    readonly property color navActiveBottom: "#c6092930"

    readonly property color rowHover: "#2262efff"
    readonly property color rowSelectedSurface: "#3f25cfe4"
    readonly property color previewSurface: "#e9050b0e"
    readonly property color previewSurfaceSoft: "#d104090c"

    readonly property color helpCategorySelected: "#da087f91"
    readonly property color helpCategoryHover: "#d0162b32"
    readonly property color helpCategorySurface: "#b7081217"
    readonly property color helpBadgeSelected: "#31f4fbfc"
    readonly property color helpBadge: "#1ef4fbfc"
    readonly property color helpBadgeBorder: "#6a62efff"
    readonly property color helpTopicSelected: "#d4113942"
    readonly property color helpTopicHover: "#cf10262d"
    readonly property color helpTopicSurface: "#ad071116"
    readonly property color stepBadge: "#4262efff"
    readonly property color richAccent: "#ffc45a"

    readonly property color backdropOverlayTop: "#26000000"
    readonly property color backdropOverlayMiddle: "#12000000"
    readonly property color backdropOverlayBottom: "#4d000000"

    readonly property string backdropBaseFile: "themes/overdrive-200x/overdrive-backdrop.png"
    readonly property string backdropBranchTopFile: ""
    readonly property string backdropBranchBottomFile: ""
    readonly property string backdropPetalFile: ""
    readonly property string panelNoiseFile: "themes/overdrive-200x/overdrive-panel-texture.png"
    readonly property string panelGlintFile: "themes/overdrive-200x/overdrive-glint.svg"
    readonly property string panelRefractionFile: "themes/overdrive-200x/overdrive-panel-texture.png"
    readonly property real panelRefractionOpacity: 0.026
    readonly property string panelEdgeFile: ""
    readonly property real panelEdgeOpacity: 0.0
    readonly property bool customFrameExclusive: true
    readonly property real customFrameRadius: 14.0
    readonly property string goldTrimFile: ""
    readonly property real goldTrimOpacity: 0.0
    readonly property bool glassBackdropEnabled: true
    readonly property real glassBackdropOpacity: 0.46
    readonly property real glassBackdropBlur: 0.38
    readonly property int glassBackdropBlurMax: 42
    readonly property real glassBackdropBlurMultiplier: 0.82
    readonly property real glassBackdropBrightness: -0.035
    readonly property real glassBackdropContrast: 0.34
    readonly property real glassBackdropSaturation: 0.92
    readonly property real glassBackdropDownsample: 0.82
    readonly property string logoFile: "kfps-logo.png"
    readonly property bool backdropBranchesVisible: false
    readonly property bool backdropPetalsVisible: false
    readonly property real backdropTopBranchOpacity: 0.0
    readonly property real backdropBottomBranchOpacity: 0.0
    readonly property real sidebarBranchOpacity: 0.0
    readonly property real sidebarCompactBranchOpacity: 0.0
    readonly property bool supporterSignatureVisible: true
    readonly property string supporterSignatureText: "signal received - thank you for the support"
}
