import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import QtQuick.Effects 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    readonly property string promoUrl: "https://ko-fi.com/s/2d1507698d"
    property bool compact: false
    property bool expired: false
    readonly property bool eligible: Theme.activeThemeName === Theme.defaultThemeName
                                     && supporterService.activationState === "no_key"

    width: Theme.px(compact ? 330 : 430)
    height: Theme.px(compact ? 74 : 88)
    strong: true
    glow: true
    visible: eligible && !expired
    opacity: visible ? 1 : 0
    panelOpacity: 0.98

    Behavior on opacity {
        NumberAnimation {
            duration: Theme.reducedMotion ? 0 : 220
            easing.type: Easing.OutCubic
        }
    }

    Timer {
        interval: 30000
        running: root.visible
        repeat: false
        onTriggered: root.expired = true
    }

    Item {
        id: carnivalRim
        anchors.fill: parent
        z: 10
        property real spin: 0

        NumberAnimation on spin {
            from: 0
            to: 360
            duration: 2600
            loops: Animation.Infinite
            running: root.visible && !Theme.reducedMotion
        }

        Repeater {
            model: 20

            Rectangle {
                readonly property real angle: (index * 360 / 20 + carnivalRim.spin) * Math.PI / 180
                readonly property real dotSize: Theme.px(index % 2 === 0 ? 4.4 : 3.5)
                width: dotSize
                height: dotSize
                radius: width / 2
                x: carnivalRim.width / 2 + Math.cos(angle) * (carnivalRim.width / 2 - Theme.px(10)) - width / 2
                y: carnivalRim.height / 2 + Math.sin(angle) * (carnivalRim.height / 2 - Theme.px(7)) - height / 2
                color: index % 2 === 0 ? Theme.primaryBright : Theme.primaryHot
                opacity: 0.82
                antialiasing: true
                layer.enabled: Theme.glassEffects && !screenshotMode
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Theme.primaryBright
                    shadowBlur: 0.78
                    shadowOpacity: 0.78
                    autoPaddingEnabled: true
                }
            }
        }
    }

    SequentialAnimation {
        running: root.visible && !Theme.reducedMotion
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "panelOpacity"; from: 0.96; to: 1.0; duration: 780; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "panelOpacity"; from: 1.0; to: 0.96; duration: 780; easing.type: Easing.InOutSine }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.px(16)
        anchors.rightMargin: Theme.px(16)
        anchors.topMargin: Theme.px(compact ? 9 : 11)
        anchors.bottomMargin: Theme.px(compact ? 9 : 11)
        spacing: Theme.px(10)

        Icon {
            name: "heart"
            iconSize: Theme.px(compact ? 18 : 22)
            glow: true
            Layout.alignment: Qt.AlignVCenter
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.px(1)

            Text {
                Layout.fillWidth: true
                text: "Supporter extras"
                color: Theme.primaryBright
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(compact ? 12.5 : 14.5)
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: compact
                      ? "FH6 mass exports + supporter themes. Click Ko-fi."
                      : "One-click FH6 mass exports and supporter themes. Click to open Ko-fi."
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(compact ? 9.8 : 11.0)
                font.weight: Font.Medium
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                lineHeight: 0.95
                elide: Text.ElideRight
            }
        }
    }

    MouseArea {
        id: promoMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: desktop.openUrl(root.promoUrl)
    }

    KfpsToolTip {
        visible: promoMouse.containsMouse
        text: "Open the KFPS supporter page in your web browser."
    }
}
