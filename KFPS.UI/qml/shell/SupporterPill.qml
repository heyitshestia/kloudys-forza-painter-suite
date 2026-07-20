import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property bool compact: false

    visible: supporterService.unlocked
    width: Theme.px(compact ? 150 : 178)
    height: Theme.px(34)
    radius: Theme.framedRadius(height / 2)
    soft: true

    Rectangle {
        id: authenticationGlint
        visible: Theme.headerSignalEnabled
        width: parent.width * 0.16
        height: parent.height * 1.8
        y: -parent.height * 0.4
        x: screenshotMode ? parent.width * 0.42 : -width * 2
        rotation: -15
        opacity: 0.38
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Theme.withAlpha(Theme.signalPrimary, 0.0) }
            GradientStop { position: 0.42; color: Theme.withAlpha(Theme.signalPrimary, 0.53) }
            GradientStop { position: 0.58; color: Theme.withAlpha(Theme.signalSecondary, 0.44) }
            GradientStop { position: 1.0; color: Theme.withAlpha(Theme.signalDanger, 0.0) }
        }
    }

    SequentialAnimation {
        running: root.visible
                 && Theme.headerSignalEnabled
                 && Theme.ambientMotion
                 && !Theme.reducedMotion
                 && !screenshotMode
        loops: Animation.Infinite
        PauseAnimation { duration: 3200 }
        PropertyAction { target: authenticationGlint; property: "x"; value: -authenticationGlint.width * 2 }
        NumberAnimation {
            target: authenticationGlint
            property: "x"
            to: root.width + authenticationGlint.width
            duration: 1400
            easing.type: Easing.InOutCubic
        }
        PauseAnimation { duration: 12000 }
    }

    Row {
        visible: Theme.headerSignalEnabled
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(3)
        spacing: Theme.px(3)

        Repeater {
            model: [Theme.signalPrimary, Theme.signalSecondary, Theme.signalDanger]
            Rectangle {
                required property color modelData
                width: Theme.px(5)
                height: Theme.px(1.5)
                radius: Theme.corner(height / 2)
                color: modelData
                opacity: 0.64
            }
        }
    }

    RowLayout {
        anchors.centerIn: parent
        spacing: Theme.px(6)

        Text {
            text: Theme.terminalMode ? "[" : "✦"
            color: Theme.primaryBright
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.compact ? 13 : 15)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            text: Theme.terminalMode ? "SUPPORTER" : "supporter"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.compact ? 10.8 : 11.8)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            text: Theme.terminalMode ? "]" : "✦"
            color: Theme.primaryBright
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.compact ? 13 : 15)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }
    }

    layer.enabled: !Theme.terminalMode && Theme.glassEffects && !screenshotMode
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Theme.primary
        shadowBlur: 0.72
        shadowOpacity: 0.44
        shadowVerticalOffset: Theme.px(2)
    }
}
