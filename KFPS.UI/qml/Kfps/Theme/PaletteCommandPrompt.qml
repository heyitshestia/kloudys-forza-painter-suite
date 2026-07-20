import QtQuick 6.7

QtObject {
    property bool greenText: false
    property color ink: greenText ? "#00ff66" : "#f2f2f2"
    property color brightInk: greenText ? "#66ff9f" : "#ffffff"
    property color dimInk: greenText ? "#00a843" : "#a8a8a8"
    property color faintInk: greenText ? "#005c25" : "#5f5f5f"
    property color softInk: Qt.rgba(ink.r, ink.g, ink.b, 0.10)
    property color selectedInk: Qt.rgba(ink.r, ink.g, ink.b, 0.18)

    readonly property string name: "Command Prompt"
    readonly property bool supporterOnly: false
    readonly property bool terminalMode: true
    readonly property bool classicMode: false
    readonly property bool iconGlyphsVisible: false
    readonly property string iconFolder: "icons-carbon"
    readonly property bool iconColorize: true
    readonly property color iconTint: ink

    // Optional capabilities consumed generically by shared UI components.
    readonly property string backdropComponentFile: "../themes/terminal/TerminalBackdrop.qml"
    readonly property string foregroundComponentFile: ""
    readonly property string pageTransitionComponentFile: ""
    readonly property bool equipmentAccentsEnabled: false
    readonly property bool ambientScanEnabled: false
    readonly property bool controlSignalEnabled: false
    readonly property bool navSignalEnabled: false
    readonly property bool panelLocatorEnabled: false
    readonly property bool headerSignalEnabled: false
    readonly property string logoDialFile: ""
    readonly property real logoDialOpacity: 0.0
    readonly property bool logoColorize: false
    readonly property color logoTint: primaryBright
    readonly property color signalPrimary: ink
    readonly property color signalSecondary: dimInk
    readonly property color signalDanger: ink
    readonly property color signalSuccess: ink
    readonly property color signalOff: faintInk
    readonly property color transitionSweep: ink
    readonly property color transitionTrail: dimInk
    readonly property real interactionSweepDuration: 0
    readonly property real interactionSweepWidth: 0.42
    readonly property real pageTransitionDuration: 0
    readonly property real locatorOpacity: 0.0

    readonly property color backgroundA: "#000000"
    readonly property color backgroundB: "#000000"
    readonly property color backgroundC: "#000000"

    readonly property color surface: "#000000"
    readonly property color surfaceSoft: "#000000"
    readonly property color surfaceStrong: "#000000"
    readonly property color surfaceRaised: "#000000"
    readonly property color surfaceTop: "#000000"
    readonly property color surfaceBottom: "#000000"
    readonly property color surfaceStrongTop: "#000000"
    readonly property color surfaceStrongBottom: "#000000"

    readonly property color border: dimInk
    readonly property color borderSoft: faintInk
    readonly property color borderStrong: ink
    readonly property color divider: faintInk
    readonly property color text: ink
    readonly property color muted: ink
    readonly property color subtle: dimInk
    readonly property color faint: faintInk

    readonly property color primary: ink
    readonly property color primaryBright: brightInk
    readonly property color primaryHot: brightInk
    readonly property color primaryDeep: ink
    readonly property color primarySoft: softInk
    readonly property color hover: softInk
    readonly property color success: ink
    readonly property color warning: ink
    readonly property color danger: ink
    readonly property color classificationHandmade: "#ff9fce"
    readonly property color classificationToolmade: "#8fd8ff"
    readonly property color consoleBackground: "#000000"
    readonly property color shadow: "#00000000"
    readonly property color innerHighlight: "#00000000"
    readonly property color focusColor: brightInk
    readonly property color primaryText: "#000000"

    readonly property color appBorder: ink
    readonly property color titleBarSurface: "#000000"
    readonly property color titleBarButtonHover: softInk
    readonly property color titleBarCloseHover: selectedInk
    readonly property color logoCapsuleSurface: "#000000"

    readonly property color panelTop: "#000000"
    readonly property color panelMiddle: "#000000"
    readonly property color panelBottom: "#000000"
    readonly property color panelSoftTop: "#000000"
    readonly property color panelSoftMiddle: "#000000"
    readonly property color panelSoftBottom: "#000000"
    readonly property color panelStrongTop: "#000000"
    readonly property color panelStrongMiddle: "#000000"
    readonly property color panelStrongBottom: "#000000"
    readonly property color panelTopHighlight: "#00000000"
    readonly property color panelInnerBorder: "#00000000"
    readonly property color panelStrongInnerBorder: "#00000000"
    readonly property color panelOverlay: "#00000000"
    readonly property color panelStrongOverlay: "#00000000"
    readonly property color panelGlowShadow: "#00000000"
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

    readonly property color primaryButtonBorder: ink
    readonly property color primaryButtonHoverBorder: brightInk
    readonly property color primaryButtonTop: "#000000"
    readonly property color primaryButtonMiddle: "#000000"
    readonly property color primaryButtonBottom: "#000000"
    readonly property color primaryButtonHoverTop: ink
    readonly property color primaryButtonHoverMiddle: ink
    readonly property color primaryButtonHoverBottom: ink
    readonly property color primaryButtonShadow: "#00000000"
    readonly property color primaryButtonHoverShadow: "#00000000"
    readonly property color primaryButtonSheenTransparent: "#00000000"
    readonly property color primaryButtonSheen: "#00000000"
    readonly property color primaryButtonLip: "#000000"
    readonly property color primaryButtonLipPressed: faintInk
    readonly property color primaryButtonGlassTop: "#00000000"
    readonly property color primaryButtonGlassMiddle: "#00000000"
    readonly property color primaryButtonInnerShadow: "#00000000"
    readonly property string primaryButtonTextureFile: ""
    readonly property real primaryButtonTextureOpacity: 0.0
    readonly property string primaryButtonLensOverlayFile: ""
    readonly property real primaryButtonLensOverlayOpacity: 0.0
    readonly property color primaryButtonText: "#000000"
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

    readonly property color ghostSurface: "#000000"
    readonly property color ghostHoverSurface: softInk
    readonly property color ghostPressedSurface: ink
    readonly property color ghostShadow: "#00000000"

    readonly property color fieldSurface: "#000000"
    readonly property color fieldHoverSurface: softInk
    readonly property color fieldFocusSurface: "#000000"
    readonly property color comboSurfaceOpen: "#000000"
    readonly property color comboHoverSurface: softInk
    readonly property color comboPopupSurface: "#000000"
    readonly property color comboHighlight: ink

    readonly property color checkboxSurface: "#000000"
    readonly property color checkboxHoverSurface: softInk
    readonly property color checkboxCheckedSurface: ink
    readonly property color switchTrackOff: "#000000"
    readonly property color sliderTrack: faintInk

    readonly property color navHoverSurface: softInk
    readonly property color navActiveGlow: "#00000000"
    readonly property color navActiveTop: ink
    readonly property color navActiveMiddle: ink
    readonly property color navActiveBottom: ink

    readonly property color rowHover: softInk
    readonly property color rowSelectedSurface: selectedInk
    readonly property color previewSurface: "#000000"
    readonly property color previewSurfaceSoft: "#000000"

    readonly property color helpCategorySelected: selectedInk
    readonly property color helpCategoryHover: softInk
    readonly property color helpCategorySurface: "#000000"
    readonly property color helpBadgeSelected: selectedInk
    readonly property color helpBadge: softInk
    readonly property color helpBadgeBorder: dimInk
    readonly property color helpTopicSelected: selectedInk
    readonly property color helpTopicHover: softInk
    readonly property color helpTopicSurface: "#000000"
    readonly property color stepBadge: selectedInk
    readonly property color richAccent: ink

    readonly property color backdropOverlayTop: "#000000"
    readonly property color backdropOverlayMiddle: "#000000"
    readonly property color backdropOverlayBottom: "#000000"

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
