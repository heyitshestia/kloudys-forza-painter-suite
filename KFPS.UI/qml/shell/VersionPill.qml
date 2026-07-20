import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property bool compact: false

    width: Theme.px(compact ? 198 : 230)
    height: Theme.px(38)
    radius: Theme.framedRadius(height / 2)
    soft: true

    Row {
        visible: Theme.headerSignalEnabled
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(3)
        spacing: Theme.px(3)

        Repeater {
            model: 4
            Rectangle {
                required property int index
                width: Theme.px(index === 3 ? 8 : 4)
                height: Theme.px(1.5)
                radius: height / 2
                color: versionService.updateAvailable
                       ? Theme.signalDanger
                       : (index === 3 ? Theme.signalSuccess : Theme.signalPrimary)
                opacity: 0.68
            }
        }
    }

    RowLayout {
        anchors.centerIn: parent
        spacing: Theme.px(9)

        Rectangle {
            id: statusDot
            Layout.preferredWidth: Theme.px(10)
            Layout.preferredHeight: Theme.px(10)
            Layout.alignment: Qt.AlignVCenter
            radius: width / 2
            color: versionService.updateAvailable ? Theme.danger : Theme.success
            layer.enabled: Theme.glassEffects && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: statusDot.color
                shadowBlur: 0.8
                shadowOpacity: 0.9
            }

            SequentialAnimation on opacity {
                running: versionService.updateAvailable && !Theme.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { to: 0.30; duration: 650 }
                NumberAnimation { to: 1.0; duration: 650 }
            }
        }

        Text {
            Layout.alignment: Qt.AlignVCenter
            Layout.maximumWidth: Theme.px(root.compact ? 154 : 184)
            text: versionService.displayText
            color: versionService.updateAvailable
                   ? (versionService.blinkOn ? Theme.danger : Theme.text)
                   : Theme.text
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
