pragma Singleton
import QtQuick 6.7

QtObject {
    id: root

    // Runtime inputs bound by Main.qml. Components should consume only semantic
    // tokens below, never branch on a page/function name or hard-code a palette.
    property bool reducedMotion: false
    property bool ambientMotion: true
    property bool glassEffects: true
    property bool terminalGreenText: false
    property string classicFontFamily: Qt.platform.os === "windows" ? "Microsoft Sans Serif" : "sans-serif"
    property string loadedUiFontFamily: ""
    property string loadedDisplayFontFamily: ""
    property string loadedMonoFontFamily: ""
    property string themeName: nightBlossom.name
    property bool supporterUnlocked: false

    readonly property QtObject nightBlossom: PaletteNightBlossom {}
    readonly property QtObject commandPrompt: PaletteCommandPrompt {
        greenText: root.terminalGreenText
    }
    readonly property QtObject windows94: PaletteWindows94 {}
    readonly property QtObject patronsAtelier: PalettePatronsAtelier {}
    readonly property QtObject carbonDark: PaletteCarbonDark {}
    readonly property QtObject overdrive200X: PaletteOverdrive200X {}
    readonly property QtObject apexVector: PaletteApexVector {}
    readonly property QtObject nightCity2077: PaletteNightCity2077 {}
    readonly property var palettes: [nightBlossom, commandPrompt, windows94, patronsAtelier, carbonDark, overdrive200X, apexVector, nightCity2077]

    readonly property string defaultThemeName: nightBlossom.name
    readonly property var requestedPalette: paletteForName(themeName)
    readonly property bool requestedThemeAllowed: !requestedPalette.supporterOnly || supporterUnlocked
    readonly property var palette: requestedThemeAllowed ? requestedPalette : nightBlossom
    readonly property string activeThemeName: palette.name
    readonly property bool supporterTheme: palette.supporterOnly
    readonly property bool terminalMode: palette.terminalMode
    readonly property bool classicMode: palette.classicMode
    readonly property bool iconGlyphsVisible: palette.iconGlyphsVisible
    readonly property string uiFontFile: palette.uiFontFile
    readonly property string displayFontFile: palette.displayFontFile
    readonly property string monoFontFile: palette.monoFontFile

    function paletteForName(name) {
        var requestedName = String(name || "").trim()
        for (var index = 0; index < palettes.length; ++index) {
            if (palettes[index].name === requestedName)
                return palettes[index]
        }
        return nightBlossom
    }

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
    readonly property color updateAlertSurface: palette.updateAlertSurface
    readonly property color updateAlertText: palette.updateAlertText
    readonly property color classificationHandmade: palette.classificationHandmade
    readonly property color classificationToolmade: palette.classificationToolmade
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
    readonly property string panelNoiseFile: palette.panelNoiseFile
    readonly property string panelGlintFile: palette.panelGlintFile
    readonly property string panelRefractionFile: palette.panelRefractionFile
    readonly property real panelRefractionOpacity: palette.panelRefractionOpacity
    readonly property string panelEdgeFile: palette.panelEdgeFile
    readonly property real panelEdgeOpacity: palette.panelEdgeOpacity
    readonly property bool customFrameExclusive: palette.customFrameExclusive
    readonly property real customFrameRadius: palette.customFrameRadius
    readonly property string goldTrimFile: palette.goldTrimFile
    readonly property real goldTrimOpacity: palette.goldTrimOpacity
    readonly property bool glassBackdropEnabled: palette.glassBackdropEnabled
    readonly property real glassBackdropOpacity: palette.glassBackdropOpacity
    readonly property real glassBackdropBlur: palette.glassBackdropBlur
    readonly property int glassBackdropBlurMax: palette.glassBackdropBlurMax
    readonly property real glassBackdropBlurMultiplier: palette.glassBackdropBlurMultiplier
    readonly property real glassBackdropBrightness: palette.glassBackdropBrightness
    readonly property real glassBackdropContrast: palette.glassBackdropContrast
    readonly property real glassBackdropSaturation: palette.glassBackdropSaturation
    readonly property real glassBackdropDownsample: palette.glassBackdropDownsample
    readonly property string logoFile: palette.logoFile
    readonly property string iconFolder: palette.iconFolder
    readonly property bool iconColorize: palette.iconColorize
    readonly property color iconTint: palette.iconTint
    readonly property string backdropComponentFile: palette.backdropComponentFile
    readonly property string foregroundComponentFile: palette.foregroundComponentFile
    readonly property string pageTransitionComponentFile: palette.pageTransitionComponentFile
    readonly property bool equipmentAccentsEnabled: palette.equipmentAccentsEnabled
    readonly property bool ambientScanEnabled: palette.ambientScanEnabled
    readonly property bool controlSignalEnabled: palette.controlSignalEnabled
    readonly property bool navSignalEnabled: palette.navSignalEnabled
    readonly property bool panelLocatorEnabled: palette.panelLocatorEnabled
    readonly property bool headerSignalEnabled: palette.headerSignalEnabled
    readonly property bool angularControlsEnabled: palette.angularControlsEnabled
    readonly property real angularCutSize: palette.angularCutSize
    readonly property real angularNotchSize: palette.angularNotchSize
    readonly property real angularPanelCutSize: palette.angularPanelCutSize
    readonly property real angularStrokeWidth: palette.angularStrokeWidth
    readonly property bool glitchInteractionsEnabled: palette.glitchInteractionsEnabled
    readonly property real glitchIntensity: palette.glitchIntensity
    readonly property bool diagnosticEasterEggsEnabled: palette.diagnosticEasterEggsEnabled
    readonly property bool technicalTypographyEnabled: palette.technicalTypographyEnabled
    readonly property bool floatingPanelsEnabled: palette.floatingPanelsEnabled
    readonly property bool glyphRailsEnabled: palette.glyphRailsEnabled
    readonly property string logoDialFile: palette.logoDialFile
    readonly property real logoDialOpacity: palette.logoDialOpacity
    readonly property bool logoColorize: palette.logoColorize
    readonly property color logoTint: palette.logoTint
    readonly property color signalPrimary: palette.signalPrimary
    readonly property color signalSecondary: palette.signalSecondary
    readonly property color signalDanger: palette.signalDanger
    readonly property color signalSuccess: palette.signalSuccess
    readonly property color signalOff: palette.signalOff
    readonly property color transitionSweep: palette.transitionSweep
    readonly property color transitionTrail: palette.transitionTrail
    readonly property real interactionSweepDuration: palette.interactionSweepDuration
    readonly property real interactionSweepWidth: palette.interactionSweepWidth
    readonly property real pageTransitionDuration: palette.pageTransitionDuration
    readonly property real locatorOpacity: palette.locatorOpacity
    readonly property bool backdropBranchesVisible: palette.backdropBranchesVisible
    readonly property bool backdropPetalsVisible: palette.backdropPetalsVisible
    readonly property real backdropTopBranchOpacity: palette.backdropTopBranchOpacity
    readonly property real backdropBottomBranchOpacity: palette.backdropBottomBranchOpacity
    readonly property real sidebarBranchOpacity: palette.sidebarBranchOpacity
    readonly property real sidebarCompactBranchOpacity: palette.sidebarCompactBranchOpacity
    readonly property bool supporterSignatureVisible: palette.supporterSignatureVisible
    readonly property string supporterSignatureText: palette.supporterSignatureText

    // Component-specific semantic tokens.
    readonly property color panelTopHighlight: palette.panelTopHighlight
    readonly property color panelInnerBorder: palette.panelInnerBorder
    readonly property color panelStrongInnerBorder: palette.panelStrongInnerBorder
    readonly property color panelOverlay: palette.panelOverlay
    readonly property color panelStrongOverlay: palette.panelStrongOverlay
    readonly property color panelGlowShadow: palette.panelGlowShadow
    readonly property color panelConvexLeftHighlight: palette.panelConvexLeftHighlight
    readonly property color panelConvexRightShadow: palette.panelConvexRightShadow
    readonly property color panelConvexBottomShadow: palette.panelConvexBottomShadow
    readonly property color panelConvexCenterGlow: palette.panelConvexCenterGlow

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
    readonly property color primaryButtonLip: palette.primaryButtonLip
    readonly property color primaryButtonLipPressed: palette.primaryButtonLipPressed
    readonly property color primaryButtonGlassTop: palette.primaryButtonGlassTop
    readonly property color primaryButtonGlassMiddle: palette.primaryButtonGlassMiddle
    readonly property color primaryButtonInnerShadow: palette.primaryButtonInnerShadow
    readonly property string primaryButtonTextureFile: palette.primaryButtonTextureFile
    readonly property real primaryButtonTextureOpacity: palette.primaryButtonTextureOpacity
    readonly property string primaryButtonLensOverlayFile: palette.primaryButtonLensOverlayFile
    readonly property real primaryButtonLensOverlayOpacity: palette.primaryButtonLensOverlayOpacity
    readonly property color primaryButtonText: palette.primaryButtonText
    readonly property real buttonGlassBackdropOpacity: palette.buttonGlassBackdropOpacity
    readonly property real buttonGlassBackdropBlur: palette.buttonGlassBackdropBlur
    readonly property int buttonGlassBackdropBlurMax: palette.buttonGlassBackdropBlurMax
    readonly property real buttonGlassBackdropBlurMultiplier: palette.buttonGlassBackdropBlurMultiplier
    readonly property real buttonGlassBackdropBrightness: palette.buttonGlassBackdropBrightness
    readonly property real buttonGlassBackdropContrast: palette.buttonGlassBackdropContrast
    readonly property real buttonGlassBackdropSaturation: palette.buttonGlassBackdropSaturation
    readonly property real buttonGlassBackdropDownsample: palette.buttonGlassBackdropDownsample
    readonly property real buttonGlassLensOpacity: palette.buttonGlassLensOpacity
    readonly property real buttonGlassLensInsetX: palette.buttonGlassLensInsetX
    readonly property real buttonGlassLensInsetY: palette.buttonGlassLensInsetY
    readonly property real buttonGlassLensOffsetX: palette.buttonGlassLensOffsetX
    readonly property real buttonGlassLensOffsetY: palette.buttonGlassLensOffsetY
    readonly property real buttonGlassLensBlur: palette.buttonGlassLensBlur
    readonly property real buttonGlassLensContrast: palette.buttonGlassLensContrast
    readonly property real buttonGlassLensSaturation: palette.buttonGlassLensSaturation
    readonly property color buttonGlassLensLeftHighlight: palette.buttonGlassLensLeftHighlight
    readonly property color buttonGlassLensCenterHighlight: palette.buttonGlassLensCenterHighlight
    readonly property color buttonGlassLensRightShadow: palette.buttonGlassLensRightShadow

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

    readonly property string fontFamily: classicMode
                                                ? classicFontFamily
                                                : (terminalMode
                                                   ? (Qt.platform.os === "windows" ? "Consolas" : "monospace")
                                                   : (loadedUiFontFamily.length > 0
                                                      ? loadedUiFontFamily
                                                      : (Qt.platform.os === "windows" ? "Segoe UI" : "Inter")))
    readonly property string displayFamily: classicMode || terminalMode
                                             ? fontFamily
                                             : (loadedDisplayFontFamily.length > 0
                                                ? loadedDisplayFontFamily
                                                : fontFamily)
    readonly property string monoFamily: classicMode
                                                ? classicFontFamily
                                                : (terminalMode
                                                   ? (Qt.platform.os === "windows" ? "Consolas" : "monospace")
                                                   : (loadedMonoFontFamily.length > 0
                                                      ? loadedMonoFontFamily
                                                      : (Qt.platform.os === "windows" ? "Cascadia Mono" : "monospace")))

    function px(value) {
        return Math.round(value)
    }

    function logical(value) {
        return value
    }

    function isAtLeast(renderedWidth, designWidth) {
        return logical(renderedWidth) >= designWidth
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }

    function withAlpha(colorValue, alpha) {
        return Qt.rgba(colorValue.r, colorValue.g, colorValue.b, clamp(alpha, 0.0, 1.0))
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

    function framedRadius(defaultRadius) {
        return (terminalMode || classicMode) ? 0 : (customFrameExclusive ? px(customFrameRadius) : defaultRadius)
    }

    function corner(defaultRadius) {
        return (terminalMode || classicMode || angularControlsEnabled) ? 0 : defaultRadius
    }
}
