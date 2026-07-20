import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    objectName: "AnnouncementTicker"

    property bool compact: false
    property bool paused: false
    readonly property bool hovered: tickerMouse.containsMouse
    readonly property bool pressed: tickerMouse.pressed
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
    radius: Theme.framedRadius(height / 2)
    soft: true
    glow: visible
    clip: true

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: Theme.hover
        opacity: tickerMouse.pressed
                 ? (Theme.customFrameExclusive ? 0.92 : 0.18)
                 : (tickerMouse.containsMouse ? (Theme.customFrameExclusive ? 0.72 : 0.10) : 0)
        Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 100 } }
    }

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
        interval: 80
        repeat: false
        onTriggered: {
            tickerTrack.x = 0
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
            readonly property real tickerGap: Theme.px(root.compact ? 28 : 36)
            readonly property real tickerStep: Math.max(1, tickerMeasure.width + tickerGap)
            readonly property int tickerCopies: Math.min(32, Math.max(3, Math.ceil(width / tickerStep) + 2))
            readonly property int tickerDuration: Math.max(3600, Math.round(tickerStep * 18))
            onTickerStepChanged: root.restartScroll()
            onTickerCopiesChanged: root.restartScroll()

            Text {
                id: tickerMeasure
                visible: false
                text: root.effectiveText
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.compact ? 10.2 : 11.4)
                font.weight: Font.DemiBold
                renderType: Text.NativeRendering
            }

            Item {
                id: tickerTrack
                visible: !Theme.reducedMotion && !root.paused
                x: 0
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(parent.width, tickerViewport.tickerStep * tickerViewport.tickerCopies)

                Repeater {
                    model: tickerViewport.tickerCopies

                    Text {
                        x: index * tickerViewport.tickerStep
                        y: Math.round((tickerViewport.height - height) / 2)
                        text: root.effectiveText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(root.compact ? 10.2 : 11.4)
                        font.weight: Font.DemiBold
                        verticalAlignment: Text.AlignVCenter
                        renderType: Text.NativeRendering
                    }
                }
            }

            NumberAnimation {
                id: scrollAnimation
                loops: Animation.Infinite
                running: root.visible && !Theme.reducedMotion && !root.paused
                target: tickerTrack
                property: "x"
                from: 0
                to: -tickerViewport.tickerStep
                duration: tickerViewport.tickerDuration
                easing.type: Easing.Linear
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
        id: tickerMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.paused = !root.paused
    }

    KfpsToolTip {
        visible: tickerMouse.containsMouse
        text: root.paused ? "Click to resume the scrolling KFPS status message." : "Click to pause the scrolling KFPS status message."
    }
}
