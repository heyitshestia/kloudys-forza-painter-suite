import QtQuick 6.7
import QtQuick.Effects 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property color surfaceColor: Theme.surfaceRaised
    property color outlineColor: Theme.borderStrong
    property color accentColor: Theme.signalSecondary
    property real cornerRadius: Theme.px(10)
    property real revealPhase: screenshotMode ? 1.0 : 0.0
    property real scanProgress: screenshotMode ? 0.62 : -0.12

    clip: true

    onVisibleChanged: {
        if (!visible)
            return
        if (Theme.angularControlsEnabled && !Theme.reducedMotion && !screenshotMode)
            revealAnimation.restart()
        else
            revealPhase = 1.0
    }

    Rectangle {
        anchors.fill: parent
        visible: !Theme.angularControlsEnabled
        radius: Theme.framedRadius(root.cornerRadius)
        color: root.surfaceColor
        border.width: Theme.classicMode ? 0 : (Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1)))
        border.color: root.outlineColor
        antialiasing: true
    }

    AngularControlFrame {
        anchors.fill: parent
        fillColor: root.surfaceColor
        borderColor: root.outlineColor
        accentColor: root.accentColor
        panelFrame: true
        enclosedPanel: true
    }

    Item {
        anchors.fill: parent
        visible: Theme.angularControlsEnabled
        opacity: root.revealPhase

        Rectangle {
            anchors.left: parent.left
            anchors.leftMargin: Theme.px(18)
            anchors.top: parent.top
            anchors.topMargin: Theme.px(5)
            width: Math.max(Theme.px(48), parent.width * 0.22)
            height: Math.max(1, Theme.px(2))
            color: Theme.signalSecondary
            opacity: 0.90
            layer.enabled: Theme.glassEffects && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Theme.signalSecondary
                shadowBlur: 0.90
                shadowOpacity: 0.86
                shadowHorizontalOffset: 0
                shadowVerticalOffset: 0
                autoPaddingEnabled: false
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: Theme.px(18)
            anchors.top: parent.top
            anchors.topMargin: Theme.px(7)
            spacing: Theme.px(3)

            Repeater {
                model: 5
                Rectangle {
                    required property int index
                    width: Theme.px(index === 4 ? 18 : (index % 2 === 0 ? 7 : 3))
                    height: Math.max(1, Theme.px(1.5))
                    color: index === 3 ? Theme.signalSecondary : Theme.signalPrimary
                    opacity: root.revealPhase > index * 0.15 ? 0.84 : 0.12
                }
            }
        }

        Rectangle {
            x: Theme.px(4)
            y: root.scanProgress * root.height
            width: Math.max(Theme.px(80), root.width - Theme.px(8))
            height: Theme.px(18)
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.withAlpha(Theme.signalSecondary, 0.0) }
                GradientStop { position: 0.48; color: Theme.withAlpha(Theme.signalSecondary, 0.025) }
                GradientStop { position: 0.52; color: Theme.withAlpha(Theme.signalSecondary, 0.14) }
                GradientStop { position: 1.0; color: Theme.withAlpha(Theme.signalSecondary, 0.0) }
            }
        }

        Rectangle {
            x: Theme.px(8)
            y: root.scanProgress * root.height + Theme.px(9)
            width: Math.max(Theme.px(64), root.width - Theme.px(16))
            height: Math.max(1, Theme.px(1))
            color: Theme.signalSecondary
            opacity: 0.42
        }
    }

    ClassicBevel {
        anchors.fill: parent
        z: 100
    }

    SequentialAnimation {
        id: revealAnimation
        PropertyAction { target: root; property: "revealPhase"; value: 0.0 }
        PropertyAction { target: root; property: "scanProgress"; value: -0.12 }
        NumberAnimation { target: root; property: "revealPhase"; to: 1.0; duration: 130; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "scanProgress"; to: 1.08; duration: 330; easing.type: Easing.OutCubic }
    }
}
