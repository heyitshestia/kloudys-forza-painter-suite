import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root

    readonly property bool applicationActive: Window.window ? Window.window.active : true
    readonly property bool motionAllowed: Theme.ambientMotion
                                          && !Theme.reducedMotion
                                          && !screenshotMode
                                          && applicationActive
    readonly property bool compactSidebar: Theme.logical(width) < 1240
    readonly property real sidebarSeam: Theme.px(compactSidebar ? Metrics.compactSidebar : Metrics.wideSidebar)
    readonly property var diagnosticMessages: [
        "FF:06:B5 // OPTICAL BUS READY",
        "KFPS://BLACKWALL // PASSIVE",
        "PAINT THE FUTURE // NO LIMIT",
        "SHAPE BUDGET // NEGOTIABLE",
        "NC-2077 // GALATEA LINK"
    ]
    property real topTraceProgress: screenshotMode ? 0.46 : -0.14
    property real rightTraceProgress: screenshotMode ? 0.64 : -0.16
    property real traceStrength: screenshotMode ? 0.76 : 0.18
    property int diagnosticIndex: screenshotMode ? 2 : 0
    property real diagnosticOpacity: screenshotMode ? 0.52 : 0.22

    // Sidebar datum: a broad internal bloom and a sharp signal core.
    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam - Theme.px(3)
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Theme.px(7)
        color: Theme.withAlpha(Theme.signalPrimary, 0.10)
    }

    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.max(1, Theme.px(1.2))
        color: Theme.signalPrimary
        opacity: 0.72
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.signalPrimary
            shadowBlur: 0.90
            shadowOpacity: 0.86
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            autoPaddingEnabled: false
        }
    }

    // Open top signal path. It replaces the repeated LED motif with one
    // continuous illuminated route and a slow travelling acquisition beam.
    Rectangle {
        x: root.sidebarSeam + Theme.px(18)
        y: Theme.px(33)
        width: Math.max(Theme.px(180), root.width - x - Theme.px(78))
        height: Theme.px(5)
        color: Theme.withAlpha(Theme.signalPrimary, 0.07)
    }

    Rectangle {
        x: root.sidebarSeam + Theme.px(18)
        y: Theme.px(35)
        width: Math.max(Theme.px(180), root.width - x - Theme.px(78))
        height: Math.max(1, Theme.px(1.2))
        color: Theme.signalPrimary
        opacity: 0.46
    }

    Rectangle {
        x: root.sidebarSeam + Theme.px(18)
           + Math.max(0, root.width - root.sidebarSeam - Theme.px(96)) * root.topTraceProgress
        y: Theme.px(33)
        width: Theme.px(116)
        height: Theme.px(4)
        opacity: root.traceStrength
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Theme.withAlpha(Theme.signalPrimary, 0.0) }
            GradientStop { position: 0.34; color: Theme.withAlpha(Theme.signalPrimary, 0.78) }
            GradientStop { position: 0.72; color: Theme.withAlpha(Theme.signalSecondary, 0.92) }
            GradientStop { position: 1.0; color: Theme.withAlpha(Theme.signalSecondary, 0.0) }
        }
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.signalSecondary
            shadowBlur: 0.92
            shadowOpacity: 0.88
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            autoPaddingEnabled: false
        }
    }

    NightCityGlyphRail {
        visible: Theme.glyphRailsEnabled
        x: root.sidebarSeam + Theme.px(5)
        y: Theme.px(76)
        width: Theme.px(18)
        height: Math.max(Theme.px(220), root.height - Theme.px(116))
        railColor: Theme.signalSecondary
        alternateColor: Theme.signalPrimary
        duration: 43000
        phaseOffset: 0.15
        opacity: 0.58
    }

    NightCityGlyphRail {
        visible: Theme.glyphRailsEnabled
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(3)
        y: Theme.px(66)
        width: Theme.px(19)
        height: Math.max(Theme.px(220), root.height - Theme.px(106))
        railColor: Theme.signalPrimary
        alternateColor: Theme.signalSecondary
        duration: 52000
        phaseOffset: 0.48
        opacity: 0.66
    }

    Rectangle {
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(26)
        anchors.top: parent.top
        anchors.topMargin: Theme.px(82)
        width: Math.max(1, Theme.px(1))
        height: Math.max(Theme.px(180), root.height - Theme.px(146))
        color: Theme.signalSecondary
        opacity: 0.20
    }

    Rectangle {
        x: root.width - Theme.px(29)
        y: Theme.px(82) + Math.max(0, root.height - Theme.px(180)) * root.rightTraceProgress
        width: Theme.px(7)
        height: Theme.px(96)
        color: Theme.withAlpha(Theme.signalSecondary, 0.34)
        opacity: root.traceStrength
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.signalSecondary
            shadowBlur: 0.92
            shadowOpacity: 0.82
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            autoPaddingEnabled: false
        }
    }

    Text {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam + Theme.px(34)
        anchors.top: parent.top
        anchors.topMargin: Theme.px(38)
        text: "NEURAL UI / KFPS-77 / PAINT BUS"
        color: Theme.signalSecondary
        opacity: 0.58
        font.family: Theme.monoFamily
        font.pixelSize: Theme.px(8.2)
        font.weight: Font.Medium
    }

    Text {
        visible: Theme.diagnosticEasterEggsEnabled
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(36)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(12)
        text: root.diagnosticMessages[root.diagnosticIndex]
        color: root.diagnosticIndex % 2 === 0 ? Theme.signalPrimary : Theme.signalSecondary
        opacity: root.diagnosticOpacity
        font.family: Theme.monoFamily
        font.pixelSize: Theme.px(8.8)
        font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "topTraceProgress"; value: -0.14 }
        NumberAnimation { target: root; property: "traceStrength"; to: 0.92; duration: 260; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "topTraceProgress"; to: 1.02; duration: 3600; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "traceStrength"; to: 0.18; duration: 520; easing.type: Easing.InCubic }
        PauseAnimation { duration: 4700 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "rightTraceProgress"; value: -0.16 }
        PauseAnimation { duration: 1900 }
        NumberAnimation { target: root; property: "rightTraceProgress"; to: 1.04; duration: 4800; easing.type: Easing.InOutCubic }
        PauseAnimation { duration: 6100 }
    }

    SequentialAnimation {
        running: root.motionAllowed && Theme.diagnosticEasterEggsEnabled
        loops: Animation.Infinite
        PauseAnimation { duration: 7600 }
        NumberAnimation { target: root; property: "diagnosticOpacity"; to: 0.74; duration: 90 }
        ScriptAction { script: root.diagnosticIndex = (root.diagnosticIndex + 1) % root.diagnosticMessages.length }
        NumberAnimation { target: root; property: "diagnosticOpacity"; to: 0.18; duration: 460 }
        PauseAnimation { duration: 3900 }
    }
}
