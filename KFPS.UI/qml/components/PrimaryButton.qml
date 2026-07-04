import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Button {
    id: root

    objectName: "PrimaryButton:" + root.text

    property string iconName: ""
    property bool showArrow: false
    property bool dense: false
    property real minimumWidth: Theme.px(dense ? 88 : 112)
    property real maximumTextWidth: Number.POSITIVE_INFINITY
    property real textPixelSize: Theme.px(dense ? 10.5 : 11.5)

    readonly property bool reserveSideSlots: iconName.length > 0 || showArrow
    readonly property real sideSlotWidth: reserveSideSlots ? Theme.px(dense ? 17 : 20) : 0
    readonly property real sideGap: reserveSideSlots ? Theme.px(7) : 0

    implicitHeight: Math.max(
                        Theme.px(dense ? Metrics.denseButtonHeight : Metrics.buttonHeight),
                        buttonLabel.implicitHeight + Theme.px(dense ? 10 : 14))
    implicitWidth: Math.max(
                       minimumWidth,
                       Math.min(maximumTextWidth, buttonLabel.implicitWidth)
                       + (reserveSideSlots ? (sideSlotWidth + sideGap) * 2 : 0)
                       + leftPadding + rightPadding)

    Layout.minimumWidth: root.minimumWidth
    Layout.minimumHeight: root.implicitHeight

    leftPadding: Theme.px(dense ? 10 : 13)
    rightPadding: Theme.px(dense ? 10 : 13)
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    scale: down ? 0.985 : 1.0

    transform: Translate {
        id: hoverLift
        y: root.hovered && !root.down ? -Theme.px(1) : 0

        Behavior on y {
            enabled: !Theme.reducedMotion
            NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
        }
    }
    Behavior on scale {
        enabled: !Theme.reducedMotion
        NumberAnimation { duration: 70; easing.type: Easing.OutCubic }
    }

    background: Item {
        Rectangle {
            id: chrome
            anchors.fill: parent
            radius: Theme.px(Metrics.controlRadius)
            antialiasing: true
            border.width: root.activeFocus ? Theme.px(2) : Theme.px(1)
            border.color: root.activeFocus ? Theme.focusColor : (root.hovered ? Theme.primaryButtonHoverBorder : Theme.primaryButtonBorder)
            opacity: root.enabled ? 1.0 : 0.42
            clip: true
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.hovered ? Theme.primaryButtonHoverTop : Theme.primaryButtonTop }
                GradientStop { position: 0.55; color: root.hovered ? Theme.primaryButtonHoverMiddle : Theme.primaryButtonMiddle }
                GradientStop { position: 1.0; color: root.hovered ? Theme.primaryButtonHoverBottom : Theme.primaryButtonBottom }
            }
            layer.enabled: Theme.glassEffects && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: root.hovered ? Theme.primaryButtonHoverShadow : Theme.primaryButtonShadow
                shadowBlur: root.hovered ? 0.8 : 0.5
                shadowOpacity: root.hovered ? 0.8 : 0.48
                shadowHorizontalOffset: 0
                shadowVerticalOffset: root.hovered ? Theme.px(3) : Theme.px(2)
            }

            Rectangle {
                id: sheen
                width: parent.width * 0.42
                height: parent.height * 1.7
                y: -parent.height * 0.35
                x: -width * 1.8
                rotation: -18
                opacity: 0
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.primaryButtonSheenTransparent }
                    GradientStop { position: 0.5; color: Theme.primaryButtonSheen }
                    GradientStop { position: 1; color: Theme.primaryButtonSheenTransparent }
                }
            }
        }
    }

    contentItem: Item {
        id: buttonContent
        implicitWidth: buttonLabel.implicitWidth
                       + (root.reserveSideSlots ? (root.sideSlotWidth + root.sideGap) * 2 : 0)
        implicitHeight: Math.max(buttonLabel.implicitHeight, root.sideSlotWidth)
        clip: true

        Icon {
            visible: root.iconName.length > 0
            name: root.iconName
            iconSize: Theme.px(root.dense ? 13 : 15)
            colorize: true
            tint: Theme.primaryText
            glow: false
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
            color: Theme.primaryText
            font.family: Theme.fontFamily
            font.pixelSize: root.textPixelSize
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.px(root.dense ? 8.5 : 9.5)
        }

        Icon {
            visible: root.showArrow
            name: "chevron-right"
            iconSize: Theme.px(root.dense ? 13 : 15)
            colorize: true
            tint: Theme.primaryText
            glow: false
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    onHoveredChanged: if (hovered && !Theme.reducedMotion) sheenAnimation.restart()

    SequentialAnimation {
        id: sheenAnimation
        PropertyAction { target: sheen; property: "opacity"; value: 0.46 }
        NumberAnimation {
            target: sheen
            property: "x"
            from: -sheen.width * 1.8
            to: root.width + sheen.width
            duration: 430
            easing.type: Easing.OutCubic
        }
        PropertyAction { target: sheen; property: "opacity"; value: 0 }
    }
}
