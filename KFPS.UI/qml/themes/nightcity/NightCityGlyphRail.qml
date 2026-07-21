import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property color railColor: Theme.signalPrimary
    property color alternateColor: Theme.signalSecondary
    property int duration: 36000
    property real phaseOffset: 0.0
    readonly property bool applicationActive: Window.window ? Window.window.active : true
    readonly property bool motionAllowed: Theme.glyphRailsEnabled
                                          && Theme.ambientMotion
                                          && !Theme.reducedMotion
                                          && !screenshotMode
                                          && applicationActive
    readonly property string glyphBlock:
        "7A\nF0\n//\nB5\n19\n::\nK6\n2D\nAF\n77\n<>\n0E\nC1\n55\n/\\\n9B\n03\nFF\nNC\n20\n77\n::\nA4\n6E\n11\nKX\n//\nD0\n3C\n88\n"
    readonly property string glyphStream: glyphBlock + glyphBlock + glyphBlock + glyphBlock
    readonly property real loopHeight: Math.max(1, streamA.implicitHeight + Theme.px(18))
    property real scrollOffset: screenshotMode ? loopHeight * 0.28 : phaseOffset * loopHeight

    clip: true

    Text {
        id: streamA
        x: 0
        y: -root.scrollOffset
        width: root.width
        text: root.glyphStream
        color: root.railColor
        opacity: 0.66
        font.family: Theme.monoFamily
        font.pixelSize: Theme.px(8.2)
        font.weight: Font.Medium
        horizontalAlignment: Text.AlignHCenter
        lineHeight: 0.92
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: root.railColor
            shadowBlur: 0.78
            shadowOpacity: 0.72
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            autoPaddingEnabled: false
        }
    }

    Text {
        x: 0
        y: streamA.y + root.loopHeight
        width: root.width
        text: root.glyphStream
        color: root.alternateColor
        opacity: 0.52
        font.family: Theme.monoFamily
        font.pixelSize: Theme.px(8.2)
        font.weight: Font.Medium
        horizontalAlignment: Text.AlignHCenter
        lineHeight: 0.92
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: Theme.px(28)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.backgroundA }
            GradientStop { position: 1.0; color: Theme.withAlpha(Theme.backgroundA, 0.0) }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Theme.px(28)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.withAlpha(Theme.backgroundA, 0.0) }
            GradientStop { position: 1.0; color: Theme.backgroundA }
        }
    }

    NumberAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        target: root
        property: "scrollOffset"
        from: root.phaseOffset * root.loopHeight
        to: root.loopHeight + root.phaseOffset * root.loopHeight
        duration: root.duration
        easing.type: Easing.Linear
    }
}
