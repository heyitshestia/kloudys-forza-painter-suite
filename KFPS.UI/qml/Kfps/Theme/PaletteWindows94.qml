import QtQuick 6.7

QtObject {
    property color face: "#c0c0c0"
    property color light: "#dfdfdf"
    property color highlight: "#ffffff"
    property color bevelShadow: "#808080"
    property color dark: "#0a0a0a"
    property color navy: "#000080"
    property color blue: "#1084d0"
    property color desktop: "#008080"

    readonly property string name: "Windows 94"
    readonly property bool supporterOnly: true
    readonly property bool terminalMode: false
    readonly property bool classicMode: true
    readonly property bool iconGlyphsVisible: true
    readonly property string iconFolder: "icons-windows94"
    readonly property bool iconColorize: false
    readonly property color iconTint: dark
    readonly property string uiFontFile: ""
    readonly property string displayFontFile: ""
    readonly property string monoFontFile: ""

    // Optional capabilities consumed generically by shared UI components.
    readonly property string backdropComponentFile: "../themes/windows94/Windows94Backdrop.qml"
    readonly property string foregroundComponentFile: ""
    readonly property string pageTransitionComponentFile: "../themes/windows94/Windows94PageTransition.qml"
    readonly property bool equipmentAccentsEnabled: false
    readonly property bool ambientScanEnabled: false
    readonly property bool controlSignalEnabled: false
    readonly property bool navSignalEnabled: false
    readonly property bool panelLocatorEnabled: false
    readonly property bool headerSignalEnabled: false
    readonly property string logoDialFile: ""
    readonly property real logoDialOpacity: 0.0
    readonly property bool logoColorize: false
    readonly property color logoTint: dark
    readonly property color signalPrimary: navy
    readonly property color signalSecondary: blue
    readonly property color signalDanger: "#ff0000"
    readonly property color signalSuccess: "#008000"
    readonly property color signalOff: bevelShadow
    readonly property color transitionSweep: highlight
    readonly property color transitionTrail: dark
    readonly property real interactionSweepDuration: 0
    readonly property real interactionSweepWidth: 0.42
    readonly property real pageTransitionDuration: 180
    readonly property real locatorOpacity: 0.0

    readonly property color backgroundA: desktop
    readonly property color backgroundB: desktop
    readonly property color backgroundC: desktop

    readonly property color surface: face
    readonly property color surfaceSoft: face
    readonly property color surfaceStrong: face
    readonly property color surfaceRaised: light
    readonly property color surfaceTop: light
    readonly property color surfaceBottom: bevelShadow
    readonly property color surfaceStrongTop: highlight
    readonly property color surfaceStrongBottom: dark

    readonly property color border: bevelShadow
    readonly property color borderSoft: light
    readonly property color borderStrong: dark
    readonly property color divider: bevelShadow
    readonly property color text: dark
    readonly property color muted: dark
    readonly property color subtle: "#404040"
    readonly property color faint: bevelShadow

    readonly property color primary: navy
    readonly property color primaryBright: blue
    readonly property color primaryHot: blue
    readonly property color primaryDeep: navy
    readonly property color primarySoft: "#d4d0c8"
    readonly property color hover: light
    readonly property color success: "#008000"
    readonly property color warning: "#808000"
    readonly property color danger: "#ff0000"
    readonly property color updateAlertSurface: danger
    readonly property color updateAlertText: primaryText
    readonly property color classificationHandmade: "#ff9fce"
    readonly property color classificationToolmade: "#8fd8ff"
    readonly property color consoleBackground: "#000000"
    readonly property color shadow: dark
    readonly property color innerHighlight: highlight
    readonly property color focusColor: dark
    readonly property color primaryText: highlight

    readonly property color appBorder: dark
    readonly property color titleBarSurface: navy
    readonly property color titleBarButtonHover: light
    readonly property color titleBarCloseHover: face
    readonly property color logoCapsuleSurface: face

    readonly property color panelTop: face
    readonly property color panelMiddle: face
    readonly property color panelBottom: face
    readonly property color panelSoftTop: face
    readonly property color panelSoftMiddle: face
    readonly property color panelSoftBottom: face
    readonly property color panelStrongTop: face
    readonly property color panelStrongMiddle: face
    readonly property color panelStrongBottom: face
    readonly property color panelTopHighlight: "#00000000"
    readonly property color panelInnerBorder: "#00000000"
    readonly property color panelStrongInnerBorder: "#00000000"
    readonly property color panelOverlay: "#00000000"
    readonly property color panelStrongOverlay: "#00000000"
    readonly property color panelGlowShadow: dark
    readonly property color panelConvexLeftHighlight: "#00000000"
    readonly property color panelConvexRightShadow: "#00000000"
    readonly property color panelConvexBottomShadow: "#00000000"
    readonly property color panelConvexCenterGlow: "#00000000"
    readonly property real panelNoiseSoftOpacity: 0.0
    readonly property real panelNoiseOpacity: 0.0
    readonly property real panelNoiseStrongOpacity: 0.0
    readonly property real panelHighlightSoftOpacity: 0.0
    readonly property real panelHighlightOpacity: 0.0
    readonly property real panelHighlightStrongOpacity: 0.0
    readonly property real panelOverlaySoftOpacity: 0.0
    readonly property real panelOverlayOpacity: 0.0

    readonly property color primaryButtonBorder: dark
    readonly property color primaryButtonHoverBorder: dark
    readonly property color primaryButtonTop: face
    readonly property color primaryButtonMiddle: face
    readonly property color primaryButtonBottom: face
    readonly property color primaryButtonHoverTop: face
    readonly property color primaryButtonHoverMiddle: face
    readonly property color primaryButtonHoverBottom: face
    readonly property color primaryButtonShadow: dark
    readonly property color primaryButtonHoverShadow: dark
    readonly property color primaryButtonSheenTransparent: "#00000000"
    readonly property color primaryButtonSheen: "#00000000"
    readonly property color primaryButtonLip: bevelShadow
    readonly property color primaryButtonLipPressed: dark
    readonly property color primaryButtonGlassTop: "#00000000"
    readonly property color primaryButtonGlassMiddle: "#00000000"
    readonly property color primaryButtonInnerShadow: "#00000000"
    readonly property string primaryButtonTextureFile: ""
    readonly property real primaryButtonTextureOpacity: 0.0
    readonly property string primaryButtonLensOverlayFile: ""
    readonly property real primaryButtonLensOverlayOpacity: 0.0
    readonly property color primaryButtonText: dark
    readonly property real buttonGlassBackdropOpacity: 0.0
    readonly property real buttonGlassBackdropBlur: 0.0
    readonly property int buttonGlassBackdropBlurMax: 40
    readonly property real buttonGlassBackdropBlurMultiplier: 0.0
    readonly property real buttonGlassBackdropBrightness: 0.0
    readonly property real buttonGlassBackdropContrast: 0.0
    readonly property real buttonGlassBackdropSaturation: 0.0
    readonly property real buttonGlassBackdropDownsample: 1.0
    readonly property real buttonGlassLensOpacity: 0.0
    readonly property real buttonGlassLensInsetX: 0.16
    readonly property real buttonGlassLensInsetY: 0.26
    readonly property real buttonGlassLensOffsetX: -0.020
    readonly property real buttonGlassLensOffsetY: -0.070
    readonly property real buttonGlassLensBlur: 0.0
    readonly property real buttonGlassLensContrast: 0.0
    readonly property real buttonGlassLensSaturation: 0.0
    readonly property color buttonGlassLensLeftHighlight: "#00000000"
    readonly property color buttonGlassLensCenterHighlight: "#00000000"
    readonly property color buttonGlassLensRightShadow: "#00000000"

    readonly property color ghostSurface: face
    readonly property color ghostHoverSurface: face
    readonly property color ghostPressedSurface: face
    readonly property color ghostShadow: dark

    readonly property color fieldSurface: highlight
    readonly property color fieldHoverSurface: highlight
    readonly property color fieldFocusSurface: highlight
    readonly property color comboSurfaceOpen: highlight
    readonly property color comboHoverSurface: highlight
    readonly property color comboPopupSurface: face
    readonly property color comboHighlight: navy

    readonly property color checkboxSurface: highlight
    readonly property color checkboxHoverSurface: highlight
    readonly property color checkboxCheckedSurface: highlight
    readonly property color switchTrackOff: highlight
    readonly property color sliderTrack: highlight

    readonly property color navHoverSurface: face
    readonly property color navActiveGlow: "#00000000"
    readonly property color navActiveTop: navy
    readonly property color navActiveMiddle: navy
    readonly property color navActiveBottom: navy

    readonly property color rowHover: light
    readonly property color rowSelectedSurface: navy
    readonly property color previewSurface: highlight
    readonly property color previewSurfaceSoft: face

    readonly property color helpCategorySelected: navy
    readonly property color helpCategoryHover: light
    readonly property color helpCategorySurface: face
    readonly property color helpBadgeSelected: navy
    readonly property color helpBadge: light
    readonly property color helpBadgeBorder: bevelShadow
    readonly property color helpTopicSelected: navy
    readonly property color helpTopicHover: light
    readonly property color helpTopicSurface: face
    readonly property color stepBadge: navy
    readonly property color richAccent: navy

    readonly property color backdropOverlayTop: desktop
    readonly property color backdropOverlayMiddle: desktop
    readonly property color backdropOverlayBottom: desktop

    readonly property string backdropBaseFile: ""
    readonly property string backdropBranchTopFile: ""
    readonly property string backdropBranchBottomFile: ""
    readonly property string backdropPetalFile: ""
    readonly property string panelNoiseFile: ""
    readonly property string panelGlintFile: ""
    readonly property string panelRefractionFile: ""
    readonly property real panelRefractionOpacity: 0.0
    readonly property string panelEdgeFile: ""
    readonly property real panelEdgeOpacity: 0.0
    readonly property bool customFrameExclusive: false
    readonly property real customFrameRadius: 0.0
    readonly property string goldTrimFile: ""
    readonly property real goldTrimOpacity: 0.0
    readonly property bool glassBackdropEnabled: false
    readonly property real glassBackdropOpacity: 0.0
    readonly property real glassBackdropBlur: 0.0
    readonly property int glassBackdropBlurMax: 48
    readonly property real glassBackdropBlurMultiplier: 0.0
    readonly property real glassBackdropBrightness: 0.0
    readonly property real glassBackdropContrast: 0.0
    readonly property real glassBackdropSaturation: 0.0
    readonly property real glassBackdropDownsample: 1.0
    readonly property string logoFile: "kfps-logo.png"
    readonly property bool backdropBranchesVisible: false
    readonly property bool backdropPetalsVisible: false
    readonly property real backdropTopBranchOpacity: 0.0
    readonly property real backdropBottomBranchOpacity: 0.0
    readonly property real sidebarBranchOpacity: 0.0
    readonly property real sidebarCompactBranchOpacity: 0.0
    readonly property bool supporterSignatureVisible: false
    readonly property string supporterSignatureText: ""
}
