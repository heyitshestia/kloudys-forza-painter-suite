import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Button {
    id: root

    objectName: "GhostButton:" + root.text

    property string iconName: ""
    property bool accentText: false
    property bool showArrow: false
    property bool dense: false
    property real minimumWidth: Theme.px(dense ? 74 : 96)
    property real maximumTextWidth: Number.POSITIVE_INFINITY
    property real textPixelSize: Theme.px(dense ? 10.2 : 11.2)

    readonly property bool reserveSideSlots: iconName.length > 0 || showArrow
    readonly property real sideSlotWidth: reserveSideSlots ? Theme.px(dense ? 16 : 19) : 0
    readonly property real sideGap: reserveSideSlots ? Theme.px(6) : 0

    implicitHeight: Math.max(
                        Theme.px(dense ? Metrics.denseButtonHeight : 36),
                        buttonLabel.implicitHeight + Theme.px(dense ? 9 : 13))
    implicitWidth: Math.max(
                       minimumWidth,
                       Math.min(maximumTextWidth, buttonLabel.implicitWidth)
                       + (reserveSideSlots ? (sideSlotWidth + sideGap) * 2 : 0)
                       + leftPadding + rightPadding)

    Layout.minimumWidth: root.minimumWidth
    Layout.minimumHeight: root.implicitHeight

    leftPadding: Theme.px(dense ? 9 : 12)
    rightPadding: Theme.px(dense ? 9 : 12)
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    scale: down ? 0.985 : 1.0

    transform: Translate {
        id: hoverLift
        y: root.hovered && !root.down ? -Theme.px(1) : 0
        Behavior on y { enabled: !Theme.reducedMotion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }
    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }

    background: Rectangle {
        id: chrome
        radius: Theme.px(Metrics.controlRadius)
        antialiasing: true
        color: root.down ? Theme.ghostPressedSurface : (root.hovered ? Theme.ghostHoverSurface : Theme.ghostSurface)
        border.width: root.activeFocus ? Theme.px(2) : Theme.px(1)
        border.color: root.activeFocus ? Theme.focusColor : (root.hovered ? Theme.primaryBright : Theme.borderSoft)
        opacity: root.enabled ? 1.0 : 0.42
        layer.enabled: Theme.glassEffects && root.hovered && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.ghostShadow
            shadowBlur: 0.64
            shadowOpacity: 0.62
            shadowHorizontalOffset: 0
            shadowVerticalOffset: Theme.px(2)
        }
        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }

    contentItem: Item {
        implicitWidth: buttonLabel.implicitWidth
                       + (root.reserveSideSlots ? (root.sideSlotWidth + root.sideGap) * 2 : 0)
        implicitHeight: Math.max(buttonLabel.implicitHeight, root.sideSlotWidth)
        clip: true

        Icon {
            visible: root.iconName.length > 0
            name: root.iconName
            iconSize: Theme.px(root.dense ? 13 : 15)
            colorize: true
            tint: root.accentText ? Theme.primaryBright : Theme.text
            iconOpacity: root.enabled ? 0.96 : 0.48
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            id: buttonLabel
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(
                       0,
                       parent.width - (root.reserveSideSlots ? (root.sideSlotWidth + root.sideGap) * 2 : 0))
            text: root.text
            color: root.accentText ? Theme.primaryBright : Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: root.textPixelSize
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.px(root.dense ? 8.2 : 9.2)
        }

        Icon {
            visible: root.showArrow
            name: "chevron-right"
            iconSize: Theme.px(root.dense ? 13 : 15)
            colorize: true
            tint: root.accentText ? Theme.primaryBright : Theme.muted
            glow: false
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
