import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    objectName: "VersionPill"

    property bool compact: false
    readonly property bool updateAlertPhase: versionService.updateAvailable
                                                    && versionService.blinkOn

    width: Theme.px(compact ? 198 : 230)
    height: Theme.px(38)
    radius: Theme.framedRadius(height / 2)
    soft: true

    Rectangle {
        anchors.fill: parent
        anchors.margins: Theme.classicMode ? Theme.px(2) : 0
        radius: Theme.corner(Math.max(0, root.radius - anchors.margins))
        color: Theme.updateAlertSurface
        opacity: root.updateAlertPhase ? 0.94 : 0.0
        antialiasing: !Theme.terminalMode && !Theme.classicMode
        z: 70

        Behavior on opacity {
            enabled: !Theme.reducedMotion
            NumberAnimation { duration: 110; easing.type: Easing.InOutQuad }
        }
    }

    Row {
        visible: Theme.headerSignalEnabled
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(3)
        spacing: Theme.px(3)
        z: 100

        Repeater {
            model: 4
            Rectangle {
                required property int index
                width: Theme.px(index === 3 ? 8 : 4)
                height: Theme.px(1.5)
                radius: Theme.corner(height / 2)
                color: versionService.updateAvailable
                       ? (root.updateAlertPhase ? Theme.updateAlertText : Theme.updateAlertSurface)
                       : (index === 3 ? Theme.signalSuccess : Theme.signalPrimary)
                opacity: 0.68
            }
        }
    }

    RowLayout {
        anchors.centerIn: parent
        spacing: Theme.px(9)
        z: 100

        Rectangle {
            id: statusDot
            Layout.preferredWidth: Theme.px(10)
            Layout.preferredHeight: Theme.px(10)
            Layout.alignment: Qt.AlignVCenter
            radius: Theme.corner(width / 2)
            color: versionService.updateAvailable
                   ? (root.updateAlertPhase ? Theme.updateAlertText : Theme.updateAlertSurface)
                   : Theme.success
            layer.enabled: !Theme.terminalMode && Theme.glassEffects && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: statusDot.color
                shadowBlur: 0.8
                shadowOpacity: 0.9
            }

            Behavior on color { ColorAnimation { duration: 100 } }
        }

        Text {
            Layout.alignment: Qt.AlignVCenter
            Layout.maximumWidth: Theme.px(root.compact ? 154 : 184)
            text: Theme.terminalMode ? "VER " + versionService.displayText : versionService.displayText
            color: root.updateAlertPhase ? Theme.updateAlertText : Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(11.5)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            Behavior on color { ColorAnimation { duration: 100 } }
        }
    }
}
