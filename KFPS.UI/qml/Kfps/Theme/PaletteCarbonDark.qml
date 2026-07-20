import QtQuick 6.7

QtObject {
    readonly property string name: "Carbon Dark"
    readonly property bool supporterOnly: true
    readonly property bool terminalMode: false
    readonly property bool classicMode: false
    readonly property bool iconGlyphsVisible: true
    readonly property string iconFolder: "icons-carbon"
    readonly property bool iconColorize: true
    readonly property color iconTint: primary

    // Optional capabilities consumed generically by shared UI components.
    readonly property string backdropComponentFile: "BlossomBackdrop.qml"
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
    readonly property color signalPrimary: primaryBright
    readonly property color signalSecondary: warning
    readonly property color signalDanger: danger
    readonly property color signalSuccess: success
    readonly property color signalOff: "#2f5e6265"
    readonly property color transitionSweep: primaryBright
    readonly property color transitionTrail: warning
    readonly property real interactionSweepDuration: 300
    readonly property real interactionSweepWidth: 0.42
    readonly property real pageTransitionDuration: 190
    readonly property real locatorOpacity: 0.0

    readonly property color backgroundA: "#050608"
    readonly property color backgroundB: "#0b0d10"
    readonly property color backgroundC: "#171b1f"

    readonly property color surface: "#c6090b0f"
    readonly property color surfaceSoft: "#a805070a"
    readonly property color surfaceStrong: "#dd101419"
    readonly property color surfaceRaised: "#ee151a20"
    readonly property color surfaceTop: "#c91a2026"
    readonly property color surfaceBottom: "#d506080c"
    readonly property color surfaceStrongTop: "#e4252b32"
    readonly property color surfaceStrongBottom: "#e80b0e13"

    readonly property color border: "#8a7a807f"
    readonly property color borderSoft: "#58676f76"
    readonly property color borderStrong: "#d2b98a58"
    readonly property color divider: "#52606a70"
    readonly property color text: "#ffffff"
    readonly property color muted: "#f3f6f8"
    readonly property color subtle: "#d9dee2"
    readonly property color faint: "#aeb7be"

    readonly property color primary: "#caa15b"
    readonly property color primaryBright: "#ffffff"
    readonly property color primaryHot: "#ffd98f"
    readonly property color primaryDeep: "#3a2a12"
    readonly property color primarySoft: "#43caa15b"
    readonly property color hover: "#26e5c16f"
    readonly property color success: "#6ed29a"
    readonly property color warning: "#f1c66e"
    readonly property color danger: "#ff657a"
    readonly property color classificationHandmade: "#ff9fce"
    readonly property color classificationToolmade: "#8fd8ff"
    readonly property color consoleBackground: "#ee050608"
    readonly property color shadow: "#e2000000"
    readonly property color innerHighlight: "#326c747c"
    readonly property color focusColor: "#ffffdda0"
    readonly property color primaryText: "#ffffff"

    readonly property color appBorder: "#827c6540"
    readonly property color titleBarSurface: "#ee06070a"
    readonly property color titleBarButtonHover: "#1effffff"
    readonly property color titleBarCloseHover: "#c9501f32"
    readonly property color logoCapsuleSurface: "#421b1710"

    readonly property color panelTop: "#d71b2228"
    readonly property color panelMiddle: "#ca0e1116"
    readonly property color panelBottom: "#d106080c"
    readonly property color panelSoftTop: "#c713171d"
    readonly property color panelSoftMiddle: "#b90a0d11"
    readonly property color panelSoftBottom: "#c105070a"
    readonly property color panelStrongTop: "#ed252c33"
    readonly property color panelStrongMiddle: "#de151a21"
    readonly property color panelStrongBottom: "#e1080a0e"
    readonly property color panelTopHighlight: "#62ffffff"
    readonly property color panelInnerBorder: "#3d9aa4aa"
    readonly property color panelStrongInnerBorder: "#84d1b16c"
    readonly property color panelOverlay: "#0affffff"
    readonly property color panelStrongOverlay: "#12000000"
    readonly property color panelGlowShadow: "#b0caa15b"
    readonly property color panelConvexLeftHighlight: "#24ffffff"
    readonly property color panelConvexRightShadow: "#78000000"
    readonly property color panelConvexBottomShadow: "#86000000"
    readonly property color panelConvexCenterGlow: "#06000000"
    readonly property real panelNoiseSoftOpacity: 0.070
    readonly property real panelNoiseOpacity: 0.085
    readonly property real panelNoiseStrongOpacity: 0.105
    readonly property real panelHighlightSoftOpacity: 0.20
    readonly property real panelHighlightOpacity: 0.26
    readonly property real panelHighlightStrongOpacity: 0.34
    readonly property real panelOverlaySoftOpacity: 0.16
    readonly property real panelOverlayOpacity: 0.23

    readonly property color primaryButtonBorder: "#e0c27a"
    readonly property color primaryButtonHoverBorder: "#fff0bd"
    readonly property color primaryButtonTop: "#a7394249"
    readonly property color primaryButtonMiddle: "#8e222932"
    readonly property color primaryButtonBottom: "#9b0f1217"
    readonly property color primaryButtonHoverTop: "#c04e5860"
    readonly property color primaryButtonHoverMiddle: "#a92f3740"
    readonly property color primaryButtonHoverBottom: "#b8181c22"
    readonly property color primaryButtonShadow: "#b0000000"
    readonly property color primaryButtonHoverShadow: "#a8caa15b"
    readonly property color primaryButtonSheenTransparent: "#00ffffff"
    readonly property color primaryButtonSheen: "#72fff3cf"
    readonly property color primaryButtonLip: "#9a090b0d"
    readonly property color primaryButtonLipPressed: "#b8060709"
    readonly property color primaryButtonGlassTop: "#aafffbef"
    readonly property color primaryButtonGlassMiddle: "#20464d54"
    readonly property color primaryButtonInnerShadow: "#66000000"
    readonly property string primaryButtonTextureFile: "themes/patrons-atelier/carbon-button-glass.png"
    readonly property real primaryButtonTextureOpacity: 0.22
    readonly property string primaryButtonLensOverlayFile: "themes/patrons-atelier/carbon-lens-overlay.png"
    readonly property real primaryButtonLensOverlayOpacity: 0.54
    readonly property color primaryButtonText: "#ffffff"
    readonly property real buttonGlassBackdropOpacity: 0.82
    readonly property real buttonGlassBackdropBlur: 0.26
    readonly property int buttonGlassBackdropBlurMax: 40
    readonly property real buttonGlassBackdropBlurMultiplier: 0.62
    readonly property real buttonGlassBackdropBrightness: -0.035
    readonly property real buttonGlassBackdropContrast: 0.34
    readonly property real buttonGlassBackdropSaturation: 0.72
    readonly property real buttonGlassBackdropDownsample: 0.86
    readonly property real buttonGlassLensOpacity: 0.78
    readonly property real buttonGlassLensInsetX: 0.16
    readonly property real buttonGlassLensInsetY: 0.26
    readonly property real buttonGlassLensOffsetX: -0.020
    readonly property real buttonGlassLensOffsetY: -0.070
    readonly property real buttonGlassLensBlur: 0.03
    readonly property real buttonGlassLensContrast: 0.42
    readonly property real buttonGlassLensSaturation: 0.86
    readonly property color buttonGlassLensLeftHighlight: "#24ffffff"
    readonly property color buttonGlassLensCenterHighlight: "#12ffecc2"
    readonly property color buttonGlassLensRightShadow: "#5a000000"

    readonly property color ghostSurface: "#8d101419"
    readonly property color ghostHoverSurface: "#bd1d252d"
    readonly property color ghostPressedSurface: "#d0090b0e"
    readonly property color ghostShadow: "#a0000000"

    readonly property color fieldSurface: "#db07090d"
    readonly property color fieldHoverSurface: "#e40d1116"
    readonly property color fieldFocusSurface: "#f1141920"
    readonly property color comboSurfaceOpen: "#f1151a20"
    readonly property color comboHoverSurface: "#df11161c"
    readonly property color comboPopupSurface: "#f00b0e13"
    readonly property color comboHighlight: "#8b6330"

    readonly property color checkboxSurface: "#db07090d"
    readonly property color checkboxHoverSurface: "#bc1e242a"
    readonly property color checkboxCheckedSurface: primary
    readonly property color switchTrackOff: "#3e4247"
    readonly property color sliderTrack: "#5a504432"

    readonly property color navHoverSurface: "#5e1f252b"
    readonly property color navActiveGlow: "#d8caa15b"
    readonly property color navActiveTop: "#d6434c54"
    readonly property color navActiveMiddle: "#ba2a3138"
    readonly property color navActiveBottom: "#aa12161b"

    readonly property color rowHover: "#20f1d48b"
    readonly property color rowSelectedSurface: "#44caa15b"
    readonly property color previewSurface: "#df050608"
    readonly property color previewSurfaceSoft: "#c9040508"

    readonly property color helpCategorySelected: "#ddcaa15b"
    readonly property color helpCategoryHover: "#c41a2027"
    readonly property color helpCategorySurface: "#aa090c12"
    readonly property color helpBadgeSelected: "#32ffffff"
    readonly property color helpBadge: "#22ffffff"
    readonly property color helpBadgeBorder: "#68e0c27a"
    readonly property color helpTopicSelected: "#c8362712"
    readonly property color helpTopicHover: "#c41b2026"
    readonly property color helpTopicSurface: "#aa080b10"
    readonly property color stepBadge: "#40caa15b"
    readonly property color richAccent: "#ffffff"

    readonly property color backdropOverlayTop: "#34000000"
    readonly property color backdropOverlayMiddle: "#0e000000"
    readonly property color backdropOverlayBottom: "#56000000"

    readonly property string backdropBaseFile: "themes/patrons-atelier/carbon-dark-backdrop.png"
    readonly property string backdropBranchTopFile: "themes/patrons-atelier/branch-top.png"
    readonly property string backdropBranchBottomFile: "themes/patrons-atelier/branch-bottom.png"
    readonly property string backdropPetalFile: "themes/patrons-atelier/soft-mote.png"
    readonly property string panelNoiseFile: "themes/patrons-atelier/carbon-panel-frost.png"
    readonly property string panelGlintFile: "themes/patrons-atelier/carbon-light-weave.png"
    readonly property string panelRefractionFile: "themes/patrons-atelier/carbon-light-weave.png"
    readonly property real panelRefractionOpacity: 0.014
    readonly property string panelEdgeFile: "themes/patrons-atelier/carbon-edge-prism.png"
    readonly property real panelEdgeOpacity: 0.30
    readonly property bool customFrameExclusive: false
    readonly property real customFrameRadius: 6.0
    readonly property string goldTrimFile: "themes/patrons-atelier/carbon-gold-trim.png"
    readonly property real goldTrimOpacity: 0.24
    readonly property bool glassBackdropEnabled: true
    readonly property real glassBackdropOpacity: 0.56
    readonly property real glassBackdropBlur: 0.52
    readonly property int glassBackdropBlurMax: 48
    readonly property real glassBackdropBlurMultiplier: 1.04
    readonly property real glassBackdropBrightness: -0.035
    readonly property real glassBackdropContrast: 0.28
    readonly property real glassBackdropSaturation: 0.80
    readonly property real glassBackdropDownsample: 0.82
    readonly property string logoFile: "themes/patrons-atelier/kfps-logo-gold.png"
    readonly property bool backdropBranchesVisible: false
    readonly property bool backdropPetalsVisible: false
    readonly property real backdropTopBranchOpacity: 0.0
    readonly property real backdropBottomBranchOpacity: 0.0
    readonly property real sidebarBranchOpacity: 0.0
    readonly property real sidebarCompactBranchOpacity: 0.0
    readonly property bool supporterSignatureVisible: true
    readonly property string supporterSignatureText: "thank you for the support -kloudy"
}
