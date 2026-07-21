import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Button {
    id: root

    objectName: "PrimaryButton:" + root.text

    property string iconName: ""
    property string toolTipText: ""
    property bool showArrow: false
    property bool dense: false
    property real minimumWidth: Theme.px(dense ? 88 : 112)
    property real maximumTextWidth: Number.POSITIVE_INFINITY
    property real textPixelSize: Theme.px(dense ? 10.5 : 11.5)

    readonly property bool reserveSideSlots: Theme.iconGlyphsVisible && (iconName.length > 0 || showArrow)
    readonly property bool terminalInverted: Theme.terminalMode && root.hovered && !root.down
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : text
    readonly property real sideSlotWidth: reserveSideSlots ? Theme.px(dense ? 17 : 20) : 0
    readonly property real sideGap: reserveSideSlots ? Theme.px(7) : 0
    readonly property real lipDepth: Theme.terminalMode || Theme.classicMode ? 0 : Theme.px(dense ? 2.8 : 4.2)
    readonly property real capTravel: Theme.terminalMode || Theme.classicMode ? 0 : (down ? Theme.px(dense ? 1.8 : 3.0) : 0)
    property real signalPhase: screenshotMode && Theme.controlSignalEnabled ? 3.0 : 0.0

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
    scale: Theme.terminalMode || Theme.classicMode ? 1.0 : (down ? 0.978 : 1.0)

    transform: Translate {
        id: hoverLift
        y: root.hovered && !root.down && !Theme.customFrameExclusive && !Theme.terminalMode && !Theme.classicMode ? -Theme.px(1.2) : 0

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
        clip: true

        AngularControlFrame {
            anchors.fill: parent
            fillColor: root.down
                       ? Theme.primaryButtonHoverBottom
                       : (root.hovered ? Theme.primaryButtonHoverMiddle : Theme.primaryButtonMiddle)
            borderColor: root.activeFocus
                         ? Theme.focusColor
                         : (root.hovered ? Theme.primaryButtonHoverBorder : Theme.primaryButtonBorder)
            accentColor: Theme.signalSecondary
            hovered: root.hovered
            pressed: root.down
            focused: root.activeFocus
            frameEnabled: root.enabled
        }

        Rectangle {
            visible: !Theme.angularControlsEnabled
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: Theme.px(2)
            anchors.rightMargin: Theme.px(2)
            height: Theme.px(root.dense ? 5 : 7)
            radius: Theme.framedRadius(Theme.px(Metrics.controlRadius))
            color: root.hovered ? Theme.primaryButtonHoverShadow : Theme.primaryButtonShadow
            opacity: root.down ? 0.03 : (root.hovered ? 0.07 : 0.045)
            antialiasing: true
            Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
        }

        Rectangle {
            id: keycapLip
            visible: !Theme.angularControlsEnabled
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.min(parent.height, root.lipDepth + Theme.px(root.dense ? 4 : 7))
            radius: Theme.framedRadius(Theme.px(Metrics.controlRadius))
            antialiasing: true
            color: root.down ? Theme.primaryButtonLipPressed : Theme.primaryButtonLip
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: root.hovered ? Theme.primaryButtonHoverBorder : Theme.primaryButtonBorder
            opacity: root.enabled ? 0.34 : 0.14
            layer.enabled: !Theme.terminalMode && Theme.glassEffects && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: root.hovered ? Theme.primaryButtonHoverShadow : Theme.primaryButtonShadow
                shadowBlur: root.hovered ? 0.34 : 0.20
                shadowOpacity: root.hovered ? 0.10 : 0.06
                shadowHorizontalOffset: 0
                shadowVerticalOffset: Theme.px(root.down ? 0.5 : 1.2)
            }
            Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }
            Behavior on border.color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }
        }

        Rectangle {
            id: chrome
            visible: !Theme.angularControlsEnabled
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: Math.max(Theme.px(8), parent.height - (root.down ? Theme.px(1.4) : root.lipDepth))
            y: root.capTravel
            radius: Theme.framedRadius(Theme.px(Metrics.controlRadius))
            antialiasing: true
            border.width: root.activeFocus ? Theme.px(2) : (Theme.customFrameExclusive ? 0 : Theme.px(1))
            border.color: root.activeFocus ? Theme.focusColor : (root.hovered ? Theme.primaryButtonHoverBorder : Theme.primaryButtonBorder)
            opacity: root.enabled ? 1.0 : 0.42
            clip: true
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.terminalMode && root.down ? Theme.backgroundA : (root.hovered ? Theme.primaryButtonHoverTop : Theme.primaryButtonTop) }
                GradientStop { position: 0.48; color: Theme.terminalMode && root.down ? Theme.backgroundA : (root.hovered ? Theme.primaryButtonHoverMiddle : Theme.primaryButtonMiddle) }
                GradientStop { position: 1.0; color: Theme.terminalMode && root.down ? Theme.backgroundA : (root.hovered ? Theme.primaryButtonHoverBottom : Theme.primaryButtonBottom) }
            }

            Behavior on y {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: 92; easing.type: Easing.OutCubic }
            }
            Behavior on height {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: 92; easing.type: Easing.OutCubic }
            }
            Behavior on border.color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }

            ButtonGlassBackdrop {
                anchors.fill: parent
                extraOpacity: root.down ? 0.70 : (root.hovered ? 1.0 : 0.96)
            }

            Rectangle {
                anchors.fill: parent
                anchors.leftMargin: Theme.px(1.4)
                anchors.rightMargin: Theme.px(1.4)
                anchors.topMargin: Theme.px(1.2)
                anchors.bottomMargin: Theme.px(1.6)
                radius: Theme.corner(Math.max(0, chrome.radius - Theme.px(1.5)))
                antialiasing: true
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.42; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 0.72; color: Theme.primaryButtonSheenTransparent }
                    GradientStop { position: 1.0; color: root.hovered ? Theme.primaryButtonHoverBottom : Theme.primaryButtonBottom }
                }
                opacity: root.down ? 0.16 : (root.hovered ? 0.34 : 0.24)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Image {
                anchors.fill: parent
                visible: Theme.primaryButtonTextureFile.length > 0
                source: visible ? assetRoot + "/" + Theme.primaryButtonTextureFile : ""
                fillMode: Image.Tile
                opacity: Theme.primaryButtonTextureOpacity
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
                opacity: Theme.panelEdgeOpacity * (root.hovered ? 1.45 : 1.12)
                smooth: true
            }

            Image {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                visible: Theme.goldTrimFile.length > 0
                source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
                height: Math.max(1, Theme.px(1.25))
                fillMode: Image.TileHorizontally
                opacity: Theme.goldTrimOpacity * (root.hovered ? 0.92 : 0.72)
                smooth: true
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: Theme.px(2)
                anchors.rightMargin: Theme.px(2)
                anchors.topMargin: Theme.px(1.6)
                height: Math.max(Theme.px(6), parent.height * 0.30)
                radius: Theme.corner(Math.max(0, chrome.radius - Theme.px(2)))
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.46; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.18 : (root.hovered ? 0.46 : 0.34)
                antialiasing: true
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Image {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                visible: Theme.goldTrimFile.length > 0
                source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
                height: Math.max(1, Theme.px(1.35))
                fillMode: Image.TileHorizontally
                opacity: Theme.goldTrimOpacity * (root.down ? 0.58 : 0.88)
                smooth: true
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: Theme.px(1)
                anchors.rightMargin: Theme.px(1)
                anchors.topMargin: Theme.px(1)
                height: parent.height * 0.42
                radius: Theme.corner(Math.max(0, chrome.radius - Theme.px(1)))
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.72; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.15 : (root.hovered ? 0.36 : 0.25)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: Theme.px(1.4)
                radius: Theme.corner(Math.max(0, chrome.radius - Theme.px(1.4)))
                color: "transparent"
                border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
                border.color: Theme.primaryButtonGlassTop
                opacity: root.down ? 0.20 : (root.hovered ? 0.68 : 0.52)
                antialiasing: true
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(1, Theme.px(2))
                radius: Theme.corner(chrome.radius)
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.18 : (root.hovered ? 0.62 : 0.46)
            }

            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(1, Theme.px(2))
                radius: Theme.corner(chrome.radius)
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.primaryButtonSheenTransparent }
                    GradientStop { position: 1.0; color: Theme.primaryButtonInnerShadow }
                }
                opacity: root.down ? 0.08 : (root.hovered ? 0.20 : 0.14)
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Math.max(1, Theme.px(root.down ? 1.0 : 2.8))
                color: Theme.primaryButtonInnerShadow
                opacity: root.down ? 0.02 : 0.07
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: Theme.px(3)
                anchors.rightMargin: Theme.px(3)
                height: Math.max(1, Theme.px(root.down ? 1.1 : 1.8))
                radius: Theme.corner(Theme.px(2))
                color: root.hovered ? Theme.primaryButtonHoverBottom : Theme.primaryButtonBottom
                opacity: root.down ? 0.16 : (root.hovered ? 0.34 : 0.24)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Rectangle {
                anchors.fill: parent
                radius: Theme.corner(chrome.radius)
                color: Theme.primaryButtonGlassTop
                opacity: root.down ? 0.18 : 0
                antialiasing: true
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 80 } }
            }

            ButtonLensOverlay {
                anchors.fill: parent
                hovered: root.hovered
                pressed: root.down
            }

            Rectangle {
                id: sheen
                width: parent.width * Theme.interactionSweepWidth
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

            Row {
                visible: Theme.controlSignalEnabled
                anchors.left: parent.left
                anchors.leftMargin: Theme.px(root.dense ? 7 : 9)
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Theme.px(root.dense ? 2 : 3)
                spacing: Theme.px(2)

                Repeater {
                    model: 3

                    Rectangle {
                        required property int index
                        width: Theme.px(index === 2 ? 6 : 4)
                        height: Theme.px(2)
                        radius: Theme.corner(height / 2)
                        color: root.down || root.signalPhase > index
                               ? (index === 2 ? Theme.signalSecondary : Theme.signalPrimary)
                               : Theme.signalOff
                        opacity: root.down
                                 ? 0.94
                                 : (root.signalPhase > index ? 0.86 : 0.16)
                        Behavior on opacity {
                            enabled: !Theme.reducedMotion
                            NumberAnimation { duration: 85; easing.type: Easing.OutCubic }
                        }
                        Behavior on color {
                            enabled: !Theme.reducedMotion
                            ColorAnimation { duration: 85 }
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: Theme.classicMode
            anchors.fill: parent
            color: Theme.surface
            z: 100

            ClassicBevel {
                anchors.fill: parent
                pressed: root.down
            }

            ClassicFocusRect {
                anchors.fill: parent
                anchors.margins: Theme.px(4)
                active: root.activeFocus && !root.down
            }
        }
    }

    contentItem: Item {
        id: buttonContent
        implicitWidth: buttonLabel.implicitWidth
                       + (root.reserveSideSlots ? (root.sideSlotWidth + root.sideGap) * 2 : 0)
        implicitHeight: Math.max(buttonLabel.implicitHeight, root.sideSlotWidth)
        clip: true
        transform: Translate {
            y: root.down ? Theme.px(1.2) : 0
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
            tint: Theme.terminalMode
                  ? (root.terminalInverted ? Theme.primaryText : Theme.text)
                  : (Theme.angularControlsEnabled
                     ? (root.hovered || root.down ? Theme.primaryText : Theme.text)
                     : Theme.primaryButtonText)
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
            text: Theme.terminalMode ? "> " + root.text : root.text
            color: Theme.terminalMode
                   ? (root.terminalInverted ? Theme.primaryText : Theme.text)
                   : (Theme.angularControlsEnabled
                      ? (root.hovered || root.down ? Theme.primaryText : Theme.text)
                      : Theme.primaryButtonText)
            font.family: Theme.fontFamily
            font.pixelSize: root.textPixelSize
            font.weight: Font.DemiBold
            font.capitalization: Theme.terminalMode || Theme.technicalTypographyEnabled ? Font.AllUppercase : Font.MixedCase
            style: Theme.terminalMode || Theme.classicMode || Theme.angularControlsEnabled ? Text.Normal : Text.Raised
            styleColor: Theme.terminalMode || Theme.classicMode ? "transparent" : Theme.primaryButtonGlassTop
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
            tint: Theme.terminalMode
                  ? (root.terminalInverted ? Theme.primaryText : Theme.text)
                  : (Theme.angularControlsEnabled
                     ? (root.hovered || root.down ? Theme.primaryText : Theme.text)
                     : Theme.primaryButtonText)
            glow: false
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    onHoveredChanged: {
        if (hovered) {
            if (!Theme.reducedMotion) {
                sheenAnimation.restart()
                if (Theme.controlSignalEnabled)
                    signalAnimation.restart()
            } else if (Theme.controlSignalEnabled) {
                signalPhase = 3.0
            }
        } else if (!down && !screenshotMode) {
            signalPhase = 0.0
        }
    }

    onDownChanged: {
        if (Theme.controlSignalEnabled && down)
            signalPhase = 3.0
        else if (Theme.controlSignalEnabled && hovered && !Theme.reducedMotion)
            signalAnimation.restart()
    }

    KfpsToolTip {
        visible: root.hovered && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }

    SequentialAnimation {
        id: sheenAnimation
        PropertyAction { target: sheen; property: "opacity"; value: 0.46 }
        NumberAnimation {
            target: sheen
            property: "x"
            from: -sheen.width * 1.8
            to: root.width + sheen.width
            duration: Theme.interactionSweepDuration
            easing.type: Easing.OutCubic
        }
        PropertyAction { target: sheen; property: "opacity"; value: 0 }
    }

    SequentialAnimation {
        id: signalAnimation
        PropertyAction { target: root; property: "signalPhase"; value: 0.0 }
        NumberAnimation {
            target: root
            property: "signalPhase"
            to: 3.0
            duration: Math.min(210, Theme.interactionSweepDuration)
            easing.type: Easing.OutCubic
        }
    }
}
