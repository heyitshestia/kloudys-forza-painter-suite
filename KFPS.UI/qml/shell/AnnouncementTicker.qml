import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property bool compact: false
    property bool paused: false
    readonly property string severity: announcementService.severity
    readonly property string effectiveText: announcementService.enabled
                                           ? announcementService.displayText
                                           : (announcementService.checking
                                              ? "Checking KFPS live status..."
                                              : "KFPS live status: no current announcement.")
    readonly property color accentColor: severity === "critical"
                                        ? Theme.danger
                                        : (severity === "warning"
                                           ? Theme.warning
                                           : (severity === "success" ? Theme.success : Theme.primaryBright))

    visible: true
    height: Theme.px(compact ? 28 : 32)
    radius: height / 2
    soft: true
    glow: visible
    clip: true

    function restartScroll() {
        if (!visible || Theme.reducedMotion || paused)
            return
        scrollAnimation.stop()
        restartTimer.restart()
    }

    onVisibleChanged: restartScroll()
    onWidthChanged: restartScroll()
    onEffectiveTextChanged: restartScroll()
    onPausedChanged: {
        if (paused) {
            scrollAnimation.stop()
        } else {
            restartScroll()
        }
    }

    Connections {
        target: announcementService
        function onChanged() {
            root.restartScroll()
        }
    }

    Timer {
        id: restartTimer
        interval: 160
        repeat: false
        onTriggered: {
            tickerText.x = Theme.px(2)
            scrollAnimation.restart()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.px(12)
        anchors.rightMargin: Theme.px(12)
        spacing: Theme.px(9)

        Rectangle {
            Layout.preferredWidth: Theme.px(root.compact ? 8 : 9)
            Layout.preferredHeight: width
            Layout.alignment: Qt.AlignVCenter
            radius: width / 2
            color: root.accentColor
            opacity: announcementService.checking ? 0.55 : 1.0

            SequentialAnimation on opacity {
                running: announcementService.checking && !Theme.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { to: 0.35; duration: 360 }
                NumberAnimation { to: 1.0; duration: 360 }
            }

            layer.enabled: Theme.glassEffects && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: root.accentColor
                shadowBlur: 0.72
                shadowOpacity: 0.72
            }
        }

        Item {
            id: tickerViewport
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Text {
                id: tickerText
                visible: !Theme.reducedMotion && !root.paused
                x: Theme.px(2)
                y: Math.round((tickerViewport.height - height) / 2)
                text: root.effectiveText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.compact ? 10.2 : 11.4)
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
            }

            SequentialAnimation {
                id: scrollAnimation
                loops: Animation.Infinite
                running: root.visible && !Theme.reducedMotion && !root.paused
                PauseAnimation { duration: 2400 }
                NumberAnimation {
                    target: tickerText
                    property: "x"
                    to: -tickerText.width
                    duration: Math.max(9000, Math.round((tickerText.width + tickerViewport.width) * 16))
                    easing.type: Easing.Linear
                }
                ScriptAction { script: tickerText.x = tickerViewport.width }
                PauseAnimation { duration: 500 }
                NumberAnimation {
                    target: tickerText
                    property: "x"
                    to: Theme.px(2)
                    duration: Math.max(2400, Math.round(tickerViewport.width * 8))
                    easing.type: Easing.Linear
                }
            }

            Text {
                anchors.fill: parent
                visible: Theme.reducedMotion || root.paused
                text: root.effectiveText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.compact ? 10.2 : 11.4)
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                renderType: Text.NativeRendering
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.paused = !root.paused
    }
}
