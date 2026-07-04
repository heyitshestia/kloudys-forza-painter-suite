pragma Singleton
import QtQuick 6.7

QtObject {
    id: root

    // Runtime inputs bound by Main.qml. Components should consume only semantic
    // tokens below, never branch on a page/function name or hard-code a palette.
    property real viewportScale: 1.0
    property real uiScale: 1.0
    property bool reducedMotion: false
    property bool ambientMotion: true
    property bool glassEffects: true
    property string themeName: nightBlossom.name
    property bool supporterUnlocked: false

    readonly property QtObject nightBlossom: PaletteNightBlossom {}

    readonly property string defaultThemeName: nightBlossom.name
    readonly property string activeThemeName: nightBlossom.name
    readonly property bool supporterTheme: false
    readonly property var palette: nightBlossom

    // Core color contract retained for existing pages/components.
    readonly property color backgroundA: palette.backgroundA
    readonly property color backgroundB: palette.backgroundB
    readonly property color backgroundC: palette.backgroundC
    readonly property color surface: palette.surface
    readonly property color surfaceSoft: palette.surfaceSoft
    readonly property color surfaceStrong: palette.surfaceStrong
    readonly property color surfaceRaised: palette.surfaceRaised
    readonly property color surfaceTop: palette.surfaceTop
    readonly property color surfaceBottom: palette.surfaceBottom
    readonly property color surfaceStrongTop: palette.surfaceStrongTop
    readonly property color surfaceStrongBottom: palette.surfaceStrongBottom
    readonly property color border: palette.border
    readonly property color borderSoft: palette.borderSoft
    readonly property color borderStrong: palette.borderStrong
    readonly property color divider: palette.divider
    readonly property color text: palette.text
    readonly property color muted: palette.muted
    readonly property color subtle: palette.subtle
    readonly property color faint: palette.faint
    readonly property color primary: palette.primary
    readonly property color primaryBright: palette.primaryBright
    readonly property color primaryHot: palette.primaryHot
    readonly property color primaryDeep: palette.primaryDeep
    readonly property color primarySoft: palette.primarySoft
    readonly property color hover: palette.hover
    readonly property color success: palette.success
    readonly property color warning: palette.warning
    readonly property color danger: palette.danger
    readonly property color consoleBackground: palette.consoleBackground
    readonly property color shadow: palette.shadow
    readonly property color innerHighlight: palette.innerHighlight
    readonly property color focusColor: palette.focusColor
    readonly property color primaryText: palette.primaryText

    // Shell/backdrop tokens.
    readonly property color appBorder: palette.appBorder
    readonly property color titleBarSurface: palette.titleBarSurface
    readonly property color titleBarButtonHover: palette.titleBarButtonHover
    readonly property color titleBarCloseHover: palette.titleBarCloseHover
    readonly property color logoCapsuleSurface: palette.logoCapsuleSurface
    readonly property color backdropOverlayTop: palette.backdropOverlayTop
    readonly property color backdropOverlayMiddle: palette.backdropOverlayMiddle
    readonly property color backdropOverlayBottom: palette.backdropOverlayBottom
    readonly property string backdropBaseFile: palette.backdropBaseFile
    readonly property string backdropBranchTopFile: palette.backdropBranchTopFile
    readonly property string backdropBranchBottomFile: palette.backdropBranchBottomFile
    readonly property string backdropPetalFile: palette.backdropPetalFile
    readonly property string logoFile: palette.logoFile
    readonly property bool backdropBranchesVisible: palette.backdropBranchesVisible
    readonly property bool backdropPetalsVisible: palette.backdropPetalsVisible
    readonly property real backdropTopBranchOpacity: palette.backdropTopBranchOpacity
    readonly property real backdropBottomBranchOpacity: palette.backdropBottomBranchOpacity
    readonly property real sidebarBranchOpacity: palette.sidebarBranchOpacity
    readonly property real sidebarCompactBranchOpacity: palette.sidebarCompactBranchOpacity

    // Component-specific semantic tokens.
    readonly property color panelTopHighlight: palette.panelTopHighlight
    readonly property color panelInnerBorder: palette.panelInnerBorder
    readonly property color panelStrongInnerBorder: palette.panelStrongInnerBorder
    readonly property color panelOverlay: palette.panelOverlay
    readonly property color panelStrongOverlay: palette.panelStrongOverlay
    readonly property color panelGlowShadow: palette.panelGlowShadow

    readonly property color primaryButtonBorder: palette.primaryButtonBorder
    readonly property color primaryButtonHoverBorder: palette.primaryButtonHoverBorder
    readonly property color primaryButtonTop: palette.primaryButtonTop
    readonly property color primaryButtonMiddle: palette.primaryButtonMiddle
    readonly property color primaryButtonBottom: palette.primaryButtonBottom
    readonly property color primaryButtonHoverTop: palette.primaryButtonHoverTop
    readonly property color primaryButtonHoverMiddle: palette.primaryButtonHoverMiddle
    readonly property color primaryButtonHoverBottom: palette.primaryButtonHoverBottom
    readonly property color primaryButtonShadow: palette.primaryButtonShadow
    readonly property color primaryButtonHoverShadow: palette.primaryButtonHoverShadow
    readonly property color primaryButtonSheenTransparent: palette.primaryButtonSheenTransparent
    readonly property color primaryButtonSheen: palette.primaryButtonSheen

    readonly property color ghostSurface: palette.ghostSurface
    readonly property color ghostHoverSurface: palette.ghostHoverSurface
    readonly property color ghostPressedSurface: palette.ghostPressedSurface
    readonly property color ghostShadow: palette.ghostShadow
    readonly property color fieldSurface: palette.fieldSurface
    readonly property color fieldHoverSurface: palette.fieldHoverSurface
    readonly property color fieldFocusSurface: palette.fieldFocusSurface
    readonly property color comboSurfaceOpen: palette.comboSurfaceOpen
    readonly property color comboHoverSurface: palette.comboHoverSurface
    readonly property color comboPopupSurface: palette.comboPopupSurface
    readonly property color comboHighlight: palette.comboHighlight
    readonly property color checkboxSurface: palette.checkboxSurface
    readonly property color checkboxHoverSurface: palette.checkboxHoverSurface
    readonly property color checkboxCheckedSurface: palette.checkboxCheckedSurface
    readonly property color switchTrackOff: palette.switchTrackOff
    readonly property color sliderTrack: palette.sliderTrack
    readonly property color navHoverSurface: palette.navHoverSurface
    readonly property color navActiveGlow: palette.navActiveGlow
    readonly property color navActiveTop: palette.navActiveTop
    readonly property color navActiveMiddle: palette.navActiveMiddle
    readonly property color navActiveBottom: palette.navActiveBottom
    readonly property color rowHover: palette.rowHover
    readonly property color rowSelectedSurface: palette.rowSelectedSurface
    readonly property color previewSurface: palette.previewSurface
    readonly property color previewSurfaceSoft: palette.previewSurfaceSoft

    readonly property color helpCategorySelected: palette.helpCategorySelected
    readonly property color helpCategoryHover: palette.helpCategoryHover
    readonly property color helpCategorySurface: palette.helpCategorySurface
    readonly property color helpBadgeSelected: palette.helpBadgeSelected
    readonly property color helpBadge: palette.helpBadge
    readonly property color helpBadgeBorder: palette.helpBadgeBorder
    readonly property color helpTopicSelected: palette.helpTopicSelected
    readonly property color helpTopicHover: palette.helpTopicHover
    readonly property color helpTopicSurface: palette.helpTopicSurface
    readonly property color stepBadge: palette.stepBadge
    readonly property color richAccent: palette.richAccent

    readonly property string fontFamily: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
    readonly property string displayFamily: Qt.platform.os === "windows" ? "Segoe UI Variable Display" : "Inter"
    readonly property string monoFamily: Qt.platform.os === "windows" ? "Cascadia Mono" : "monospace"

    readonly property real effectiveScale: Math.max(0.72, viewportScale * uiScale)

    function px(value) {
        return Math.round(value * effectiveScale * 100) / 100
    }

    function logical(value) {
        return value / effectiveScale
    }

    function isAtLeast(renderedWidth, designWidth) {
        return logical(renderedWidth) >= designWidth
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }

    function panelGradientTop(soft, strong) {
        return strong ? palette.panelStrongTop : (soft ? palette.panelSoftTop : palette.panelTop)
    }

    function panelGradientMiddle(soft, strong) {
        return strong ? palette.panelStrongMiddle : (soft ? palette.panelSoftMiddle : palette.panelMiddle)
    }

    function panelGradientBottom(soft, strong) {
        return strong ? palette.panelStrongBottom : (soft ? palette.panelSoftBottom : palette.panelBottom)
    }

    function panelHighlightOpacity(soft, strong) {
        return soft ? palette.panelHighlightSoftOpacity : (strong ? palette.panelHighlightStrongOpacity : palette.panelHighlightOpacity)
    }

    function panelNoiseOpacity(soft, strong) {
        return soft ? palette.panelNoiseSoftOpacity : (strong ? palette.panelNoiseStrongOpacity : palette.panelNoiseOpacity)
    }

    function panelOverlayOpacity(soft) {
        return soft ? palette.panelOverlaySoftOpacity : palette.panelOverlayOpacity
    }
}
