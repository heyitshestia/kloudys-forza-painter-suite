pragma Singleton
import QtQuick 6.7

QtObject {
    // Continuous scale derived from the live window dimensions. Every visual
    // metric flows through effectiveScale instead of discrete window presets.
    property real viewportScale: 1.0
    property real uiScale: 1.0
    property bool reducedMotion: false
    property bool ambientMotion: true
    property bool glassEffects: true
    property string themeName: "Night Blossom"
    property bool supporterUnlocked: false

    readonly property bool supporterTheme: supporterUnlocked && themeName === "Ko-fi Cherry"

    readonly property color backgroundA: supporterTheme ? "#10070d" : "#07050d"
    readonly property color backgroundB: supporterTheme ? "#221018" : "#120915"
    readonly property color backgroundC: supporterTheme ? "#3b1728" : "#260e24"

    readonly property color surface: supporterTheme ? "#cf24151f" : "#c6150e1d"
    readonly property color surfaceSoft: supporterTheme ? "#b3150b14" : "#ad0d0913"
    readonly property color surfaceStrong: supporterTheme ? "#df3c2430" : "#d91d1325"
    readonly property color surfaceRaised: supporterTheme ? "#ef4a2c36" : "#ed25162d"
    readonly property color surfaceTop: supporterTheme ? "#ba66475a" : "#b72d2036"
    readonly property color surfaceBottom: supporterTheme ? "#df160b1c" : "#d0100a17"
    readonly property color surfaceStrongTop: supporterTheme ? "#d9795568" : "#cc37243d"
    readonly property color surfaceStrongBottom: supporterTheme ? "#e0251128" : "#dd160d20"

    readonly property color border: supporterTheme ? "#a87a5e80" : "#765e4b68"
    readonly property color borderSoft: supporterTheme ? "#68513e5c" : "#4f49334f"
    readonly property color borderStrong: supporterTheme ? "#e2a57d9a" : "#b78a667f"
    readonly property color divider: supporterTheme ? "#5a46364d" : "#3d493445"
    readonly property color text: "#fff8fc"
    readonly property color muted: supporterTheme ? "#ead1df" : "#d8c9d5"
    readonly property color subtle: supporterTheme ? "#c09aad" : "#a98fa4"
    readonly property color faint: supporterTheme ? "#856778" : "#755f73"

    readonly property color primary: supporterTheme ? "#ff5b9d" : "#ea3c88"
    readonly property color primaryBright: supporterTheme ? "#ffc1d8" : "#ff78b6"
    readonly property color primaryHot: supporterTheme ? "#ff79b4" : "#ff4c9a"
    readonly property color primaryDeep: supporterTheme ? "#b91d5d" : "#9c174f"
    readonly property color primarySoft: supporterTheme ? "#55ff7fb1" : "#4dea3c88"
    readonly property color hover: supporterTheme ? "#2dffc6dd" : "#22ff8fc2"
    readonly property color success: "#60dc91"
    readonly property color warning: "#ffc66d"
    readonly property color danger: "#ff536f"
    readonly property color consoleBackground: "#ee09060e"
    readonly property color shadow: "#d5000000"
    readonly property color innerHighlight: "#2d8a5a7d"
    readonly property color focus: "#ffff9ac8"

    readonly property string fontFamily: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
    readonly property string displayFamily: Qt.platform.os === "windows" ? "Segoe UI Variable Display" : "Inter"
    readonly property string monoFamily: Qt.platform.os === "windows" ? "Cascadia Mono" : "monospace"

    readonly property real effectiveScale: Math.max(0.72, viewportScale * uiScale)

    // Single continuous geometry scale used by every component and page.
    function px(value) {
        return Math.round(value * effectiveScale * 100) / 100
    }

    // Responsive fallbacks activate only when user zoom or an extreme aspect
    // ratio genuinely leaves less logical room.
    function logical(value) {
        return value / effectiveScale
    }

    function isAtLeast(renderedWidth, designWidth) {
        return logical(renderedWidth) >= designWidth
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }
}
