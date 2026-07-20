import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Button {
    id: root

    objectName: "GhostButton:" + root.text

    property string iconName: ""
    property string toolTipText: ""
    property bool accentText: false
    property bool selected: false
    property color labelColor: accentText ? Theme.primaryBright : Theme.text
    property bool showArrow: false
    property bool dense: false
    property bool auditAllowOutsideFeedback: false
    property real minimumWidth: Theme.px(dense ? 74 : 96)
    property real maximumTextWidth: Number.POSITIVE_INFINITY
    property real textPixelSize: Theme.px(dense ? 10.2 : 11.2)

    readonly property bool checkedState: root.selected || (root.checkable && root.checked)
    readonly property bool reserveSideSlots: iconName.length > 0 || showArrow
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : text
    readonly property real sideSlotWidth: reserveSideSlots ? Theme.px(dense ? 16 : 19) : 0
    readonly property real sideGap: reserveSideSlots ? Theme.px(6) : 0
    readonly property real lipDepth: Theme.px(dense ? 1.8 : 2.8)
    readonly property real capTravel: down ? Theme.px(dense ? 1.1 : 2.0) : 0

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
    scale: down ? 0.982 : 1.0

    transform: Translate {
        id: hoverLift
        y: root.hovered && !root.down && !Theme.customFrameExclusive ? -Theme.px(1) : 0
        Behavior on y { enabled: !Theme.reducedMotion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }
    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }

    KfpsToolTip {
        visible: root.hovered && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }

    background: Item {
        clip: true

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: Theme.px(2)
            anchors.rightMargin: Theme.px(2)
            height: Theme.px(root.dense ? 3 : 5)
            radius: Theme.framedRadius(Theme.px(Metrics.controlRadius))
            color: Theme.ghostShadow
            opacity: root.down ? 0.02 : (root.hovered ? 0.05 : 0.025)
            antialiasing: true
            Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.min(parent.height, root.lipDepth + Theme.px(root.dense ? 3 : 5))
            radius: Theme.framedRadius(Theme.px(Metrics.controlRadius))
            antialiasing: true
            color: root.down ? Theme.ghostPressedSurface
                             : (root.checkedState ? Theme.primaryDeep : Theme.panelGradientBottom(false, false))
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: root.checkedState ? Theme.primaryHot
                                            : (root.hovered ? Theme.primaryBright : Theme.borderSoft)
            opacity: root.enabled ? (root.checkedState ? 0.72 : 0.36) : 0.14
            Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 120 } }
            Behavior on border.color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 120 } }
        }

        Rectangle {
            id: chrome
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: Math.max(Theme.px(8), parent.height - (root.down ? Theme.px(1.0) : root.lipDepth))
            y: root.capTravel
            radius: Theme.framedRadius(Theme.px(Metrics.controlRadius))
            antialiasing: true
            border.width: root.activeFocus || root.checkedState
                          ? Theme.px(2)
                          : (Theme.customFrameExclusive ? 0 : Theme.px(1))
            border.color: root.activeFocus ? Theme.focusColor
                                           : (root.checkedState ? Theme.primaryHot
                                                                : (root.hovered ? Theme.primaryBright : Theme.borderSoft))
            opacity: root.enabled ? 1.0 : 0.42
            clip: true
            gradient: Gradient {
                GradientStop {
                    position: 0.0
                    color: root.down ? Theme.ghostPressedSurface
                                     : (root.checkedState ? Theme.navActiveTop : Theme.fieldFocusSurface)
                }
                GradientStop {
                    position: 0.48
                    color: root.checkedState ? Theme.navActiveMiddle
                                             : (root.hovered ? Theme.ghostHoverSurface : Theme.ghostSurface)
                }
                GradientStop {
                    position: 1.0
                    color: root.down ? Theme.ghostPressedSurface
                                     : (root.checkedState ? Theme.navActiveBottom : Theme.ghostSurface)
                }
            }
            layer.enabled: Theme.glassEffects && (root.hovered || root.checkedState) && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: root.checkedState ? Theme.navActiveGlow : Theme.ghostShadow
                shadowBlur: root.checkedState ? 0.34 : 0.18
                shadowOpacity: root.checkedState ? 0.20 : 0.05
                shadowHorizontalOffset: 0
                shadowVerticalOffset: Theme.px(root.down ? 0.5 : 1)
            }
            Behavior on y { enabled: !Theme.reducedMotion; NumberAnimation { duration: 85; easing.type: Easing.OutCubic } }
            Behavior on height { enabled: !Theme.reducedMotion; NumberAnimation { duration: 85; easing.type: Easing.OutCubic } }
            Behavior on border.color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 120 } }

            ButtonGlassBackdrop {
                anchors.fill: parent
                extraOpacity: root.down ? 0.30 : (root.hovered ? 0.54 : 0.36)
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: Theme.px(1.4)
                radius: Math.max(0, chrome.radius - Theme.px(1.5))
                antialiasing: true
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.46; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.16 : (root.hovered ? 0.34 : 0.22)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Image {
                anchors.fill: parent
                visible: Theme.primaryButtonTextureFile.length > 0
                source: visible ? assetRoot + "/" + Theme.primaryButtonTextureFile : ""
                fillMode: Image.Tile
                opacity: Theme.primaryButtonTextureOpacity * (root.hovered ? 0.26 : 0.14)
                smooth: true
                clip: true
            }

            BorderImage {
                anchors.fill: parent
                visible: !Theme.customFrameExclusive && Theme.panelEdgeFile.length > 0
                source: visible ? assetRoot + "/" + Theme.panelEdgeFile : ""
                border.left: 42
                border.right: 42
                border.top: 42
                border.bottom: 42
                horizontalTileMode: BorderImage.Stretch
                verticalTileMode: BorderImage.Stretch
                opacity: Theme.panelEdgeOpacity * (root.hovered ? 0.46 : 0.24)
                smooth: true
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: Theme.px(1)
                anchors.rightMargin: Theme.px(1)
                anchors.topMargin: Theme.px(1)
                height: parent.height * 0.48
                radius: Math.max(0, chrome.radius - Theme.px(1))
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.78; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.18 : (root.hovered ? 0.38 : 0.24)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: Theme.px(1.4)
                radius: Math.max(0, chrome.radius - Theme.px(1.4))
                color: "transparent"
                border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
                border.color: Theme.primaryButtonGlassTop
                opacity: root.down ? 0.10 : (root.hovered ? 0.30 : 0.18)
                antialiasing: true
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Image {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                visible: Theme.goldTrimFile.length > 0
                source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
                height: Math.max(1, Theme.px(1))
                fillMode: Image.TileHorizontally
                opacity: Theme.goldTrimOpacity * (root.hovered ? 0.46 : 0.24)
                smooth: true
            }

            Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(1, Theme.px(1.4))
                radius: chrome.radius
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.12 : (root.hovered ? 0.34 : 0.22)
            }

            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(1, Theme.px(1.4))
                radius: chrome.radius
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.primaryButtonSheenTransparent }
                    GradientStop { position: 1.0; color: Theme.primaryButtonInnerShadow }
                }
                opacity: root.down ? 0.10 : (root.hovered ? 0.22 : 0.14)
            }

            Rectangle {
                anchors.fill: parent
                radius: chrome.radius
                color: Theme.primaryButtonGlassTop
                opacity: root.down ? 0.14 : 0
                antialiasing: true
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 80 } }
            }

            ButtonLensOverlay {
                anchors.fill: parent
                hovered: root.hovered || root.checkedState
                pressed: root.down
                latched: root.checkedState
                strength: root.checkedState ? 0.86 : 0.58
            }

            Rectangle {
                visible: root.checkedState
                anchors.left: parent.left
                anchors.leftMargin: Theme.px(3)
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(Theme.px(2.5), 2)
                height: Math.max(Theme.px(12), parent.height - Theme.px(12))
                radius: width / 2
                color: Theme.primaryHot
                antialiasing: true
            }
        }
    }

    contentItem: Item {
        implicitWidth: buttonLabel.implicitWidth
                       + (root.reserveSideSlots ? (root.sideSlotWidth + root.sideGap) * 2 : 0)
        implicitHeight: Math.max(buttonLabel.implicitHeight, root.sideSlotWidth)
        clip: true
        transform: Translate {
            y: root.down ? Theme.px(0.9) : 0
            Behavior on y {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: 82; easing.type: Easing.OutCubic }
            }
        }

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
            color: root.labelColor
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
