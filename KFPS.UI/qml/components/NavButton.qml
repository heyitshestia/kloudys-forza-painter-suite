import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Button {
    id: root

    objectName: "NavButton:" + root.text

    property string iconName: "home"
    property string toolTipText: ""
    property bool active: false
    property bool compact: false
    property bool dense: false
    readonly property real activeLipDepth: Theme.terminalMode || Theme.classicMode ? 0 : Theme.px(dense ? 2.0 : 3.2)
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : text
    readonly property real capTravel: Theme.terminalMode || Theme.classicMode ? 0 : (down ? Theme.px(dense ? 1.1 : 2.0) : 0)
    property real signalPhase: screenshotMode && active && Theme.navSignalEnabled ? 3.0 : 0.0
    property real revealProgress: screenshotMode && active && Theme.navSignalEnabled ? 1.0 : 0.0

    onActiveChanged: {
        if (!Theme.navSignalEnabled)
            return
        if (active) {
            if (Theme.reducedMotion || screenshotMode) {
                signalPhase = 3.0
                revealProgress = 1.0
            } else {
                navSelectionAnimation.restart()
            }
        } else {
            signalPhase = 0.0
            revealProgress = 0.0
        }
    }

    Component.onCompleted: {
        if (Theme.navSignalEnabled && active) {
            signalPhase = 3.0
            revealProgress = 1.0
        }
    }

    implicitHeight: Theme.px(compact ? Metrics.compactNavButtonHeight : (dense ? 42 : Metrics.navButtonHeight))
    implicitWidth: Theme.px(compact ? Metrics.compactSidebar - 18 : Metrics.wideSidebar - 20)
    Layout.minimumHeight: root.implicitHeight

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    leftPadding: 0
    rightPadding: 0
    topPadding: 0
    bottomPadding: 0
    scale: Theme.terminalMode || Theme.classicMode ? 1.0 : (down ? 0.982 : 1.0)

    transform: Translate {
        id: hoverLift
        y: root.hovered && !root.down && !Theme.customFrameExclusive && !Theme.terminalMode && !Theme.classicMode ? -Theme.px(1) : 0
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
            id: activeGlow
            anchors.fill: parent
            anchors.margins: -Theme.px(2)
            radius: Theme.framedRadius(Theme.px(11))
            color: "transparent"
            opacity: root.active ? 1 : 0
            layer.enabled: !Theme.terminalMode && Theme.glassEffects && root.active && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Theme.navActiveGlow
                shadowBlur: 0.28
                shadowOpacity: 0.18
                shadowHorizontalOffset: 0
                shadowVerticalOffset: 0
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: Theme.px(2)
            anchors.rightMargin: Theme.px(2)
            height: Theme.px(root.dense ? 3 : 5)
            radius: Theme.framedRadius(Theme.px(9))
            color: Theme.primaryButtonHoverShadow
            opacity: root.active ? (root.down ? 0.02 : 0.04) : 0
            antialiasing: true
            Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
        }

        Rectangle {
            id: navLip
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.min(parent.height, root.activeLipDepth + Theme.px(root.dense ? 3 : 5))
            radius: Theme.framedRadius(Theme.px(9))
            antialiasing: true
            color: root.active ? (root.down ? Theme.primaryButtonLipPressed : Theme.primaryButtonLip) : "transparent"
            border.width: root.active && !Theme.customFrameExclusive ? Math.max(1, Theme.px(1)) : 0
            border.color: root.active ? Theme.primaryButtonBorder : "transparent"
            opacity: root.active ? 0.42 : 0
            Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }
            Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
        }

        Rectangle {
            id: chrome
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: root.active ? Math.max(Theme.px(8), parent.height - (root.down ? Theme.px(1) : root.activeLipDepth)) : parent.height
            y: root.active ? root.capTravel : 0
            radius: Theme.framedRadius(Theme.px(9))
            antialiasing: true
            color: root.active ? "transparent" : (root.hovered ? Theme.navHoverSurface : "transparent")
            border.width: root.activeFocus
                          ? Theme.px(2)
                          : ((!Theme.customFrameExclusive && (root.active || root.hovered)) ? Theme.px(1) : 0)
            border.color: root.activeFocus ? Theme.focusColor : (root.active ? (root.hovered ? Theme.primaryButtonHoverBorder : Theme.primaryButtonBorder) : Theme.borderSoft)
            gradient: root.active ? activeGradient : undefined
            clip: true

            Gradient {
                id: activeGradient
                GradientStop { position: 0.0; color: Theme.navActiveTop }
                GradientStop { position: 0.52; color: Theme.navActiveMiddle }
                GradientStop { position: 1.0; color: Theme.navActiveBottom }
            }

            Behavior on color { ColorAnimation { duration: 120 } }
            Behavior on y { enabled: !Theme.reducedMotion; NumberAnimation { duration: 85; easing.type: Easing.OutCubic } }
            Behavior on height { enabled: !Theme.reducedMotion; NumberAnimation { duration: 85; easing.type: Easing.OutCubic } }

            ButtonGlassBackdrop {
                anchors.fill: parent
                effectEnabled: root.active
                extraOpacity: root.down ? 0.46 : (root.hovered ? 0.84 : 0.72)
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: Theme.px(1.4)
                radius: Theme.corner(Math.max(0, chrome.radius - Theme.px(1.5)))
                visible: root.active
                antialiasing: true
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.48; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.18 : (root.hovered ? 0.42 : 0.30)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Image {
                anchors.fill: parent
                visible: root.active && Theme.primaryButtonTextureFile.length > 0
                source: visible ? assetRoot + "/" + Theme.primaryButtonTextureFile : ""
                fillMode: Image.Tile
                opacity: Theme.primaryButtonTextureOpacity * 0.54
                smooth: true
                clip: true
            }

            BorderImage {
                anchors.fill: parent
                visible: !Theme.customFrameExclusive && root.active && Theme.panelEdgeFile.length > 0
                source: visible ? assetRoot + "/" + Theme.panelEdgeFile : ""
                border.left: 42
                border.right: 42
                border.top: 42
                border.bottom: 42
                horizontalTileMode: BorderImage.Stretch
                verticalTileMode: BorderImage.Stretch
                opacity: Theme.panelEdgeOpacity * (root.hovered ? 0.64 : 0.44)
                smooth: true
            }

            Image {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                visible: root.active && Theme.goldTrimFile.length > 0
                source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
                height: Math.max(1, Theme.px(1))
                fillMode: Image.TileHorizontally
                opacity: Theme.goldTrimOpacity * 0.70
                smooth: true
            }

            Image {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                visible: root.active && Theme.goldTrimFile.length > 0
                source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
                height: Math.max(1, Theme.px(1.2))
                fillMode: Image.TileHorizontally
                opacity: Theme.goldTrimOpacity * (root.down ? 0.46 : 0.72)
                smooth: true
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: Theme.px(1)
                anchors.rightMargin: Theme.px(1)
                anchors.topMargin: Theme.px(1)
                height: parent.height * 0.46
                radius: Theme.corner(Math.max(0, chrome.radius - Theme.px(1)))
                visible: root.active
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.76; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.20 : (root.hovered ? 0.44 : 0.32)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: Theme.px(1.4)
                radius: Theme.corner(Math.max(0, chrome.radius - Theme.px(1.4)))
                visible: root.active
                color: "transparent"
                border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
                border.color: Theme.primaryButtonGlassTop
                opacity: root.down ? 0.12 : (root.hovered ? 0.34 : 0.22)
                antialiasing: true
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(1, Theme.px(1.6))
                radius: Theme.corner(chrome.radius)
                visible: root.active
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.down ? 0.14 : (root.hovered ? 0.36 : 0.26)
            }

            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(1, Theme.px(1.6))
                radius: Theme.corner(chrome.radius)
                visible: root.active
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.primaryButtonSheenTransparent }
                    GradientStop { position: 1.0; color: Theme.primaryButtonInnerShadow }
                }
                opacity: root.down ? 0.10 : (root.hovered ? 0.26 : 0.18)
            }

            Rectangle {
                anchors.fill: parent
                radius: Theme.corner(chrome.radius)
                visible: root.active
                color: Theme.primaryButtonGlassTop
                opacity: root.down ? 0.14 : 0
                antialiasing: true
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 80 } }
            }

            ButtonLensOverlay {
                anchors.fill: parent
                active: root.active
                hovered: root.hovered
                pressed: root.down
                latched: root.active
                strength: 0.82
            }

            Item {
                visible: Theme.navSignalEnabled && root.active
                anchors.fill: parent
                clip: true

                Rectangle {
                    x: -width * (1.0 - root.revealProgress)
                    width: parent.width
                    height: parent.height
                    color: Theme.signalPrimary
                    opacity: 0.09
                    Behavior on x {
                        enabled: !Theme.reducedMotion
                        NumberAnimation { duration: 260; easing.type: Easing.OutCubic }
                    }
                }
            }

            Row {
                visible: Theme.navSignalEnabled && root.active
                anchors.right: parent.right
                anchors.rightMargin: Theme.px(root.compact ? 7 : 25)
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Theme.px(3)
                spacing: Theme.px(2)

                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        width: Theme.px(index === 2 ? 7 : 4)
                        height: Theme.px(2)
                        radius: Theme.corner(height / 2)
                        color: root.signalPhase > index
                               ? (index === 2 ? Theme.signalSecondary : Theme.signalPrimary)
                               : Theme.signalOff
                        opacity: root.signalPhase > index ? 0.92 : 0.16
                        Behavior on opacity {
                            enabled: !Theme.reducedMotion
                            NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                        }
                        Behavior on color {
                            enabled: !Theme.reducedMotion
                            ColorAnimation { duration: 90 }
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.max(1, Theme.px(1))
            color: Theme.divider
            opacity: root.active ? 0 : 0.34
        }

        Rectangle {
            visible: Theme.classicMode
            anchors.fill: parent
            color: Theme.surface
            z: 100

            ClassicBevel {
                anchors.fill: parent
                pressed: root.down || root.active
            }

            ClassicFocusRect {
                anchors.fill: parent
                anchors.margins: Theme.px(4)
                active: root.activeFocus && !root.active
            }
        }
    }

    contentItem: Loader {
        sourceComponent: root.compact ? compactContent : wideContent
        transform: Translate {
            y: root.down && root.active ? Theme.px(0.8) : 0
            Behavior on y {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: 82; easing.type: Easing.OutCubic }
            }
        }
    }

    Component {
        id: wideContent
        Item {
            Row {
                anchors.left: parent.left
                anchors.leftMargin: Theme.px(17)
                anchors.right: arrowText.left
                anchors.rightMargin: Theme.px(8)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.px(Theme.terminalMode ? 7 : 13)

                Text {
                    visible: Theme.terminalMode
                    text: root.active ? ">" : (root.hovered ? ":" : " ")
                    color: root.active ? Theme.primaryText : Theme.text
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.px(root.dense ? 11.5 : 13)
                    font.weight: Font.Bold
                    anchors.verticalCenter: parent.verticalCenter
                }

                Icon {
                    name: root.iconName
                    iconSize: Theme.px(root.dense ? 18 : 20)
                    colorize: Theme.classicMode || root.active
                    tint: Theme.classicMode
                          ? Theme.borderStrong
                          : Theme.primaryButtonText
                    glow: root.active && !Theme.classicMode
                    glowColor: Theme.focusColor
                    iconOpacity: root.active ? 1 : 0.78
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    width: Math.max(0, parent.width - x)
                    text: root.text
                    color: Theme.classicMode
                           ? Theme.text
                           : (root.active ? Theme.primaryButtonText : Theme.muted)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(root.dense ? 11.5 : 13)
                    font.weight: root.active ? Font.DemiBold : Font.Medium
                    font.capitalization: Theme.terminalMode ? Font.AllUppercase : Font.MixedCase
                    anchors.verticalCenter: parent.verticalCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }

            Text {
                id: arrowText
                width: Theme.px(20)
                text: "›"
                visible: !Theme.terminalMode && !Theme.classicMode && (root.active || root.hovered)
                color: root.active ? Theme.primaryButtonText : Theme.primaryBright
                opacity: root.active ? 1 : 0.75
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(24)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                anchors.right: parent.right
                anchors.rightMargin: Theme.px(10)
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    Component {
        id: compactContent
        Column {
            anchors.centerIn: parent
            width: parent.width
            spacing: Theme.px(2)

            Icon {
                name: root.iconName
                iconSize: Theme.px(root.dense ? 17 : 19)
                colorize: Theme.classicMode || root.active
                tint: Theme.classicMode
                      ? Theme.borderStrong
                      : Theme.primaryButtonText
                glow: root.active && !Theme.classicMode
                glowColor: Theme.focusColor
                iconOpacity: root.active ? 1 : 0.78
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Text {
                width: parent.width - Theme.px(8)
                text: root.text
                color: Theme.classicMode
                       ? Theme.text
                       : (root.active ? Theme.primaryButtonText : Theme.muted)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.dense ? 8 : 9)
                font.weight: Font.DemiBold
                font.capitalization: Theme.terminalMode ? Font.AllUppercase : Font.MixedCase
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }
    }

    ParallelAnimation {
        id: navSelectionAnimation
        SequentialAnimation {
            PropertyAction { target: root; property: "signalPhase"; value: 0.0 }
            NumberAnimation {
                target: root
                property: "signalPhase"
                to: 3.0
                duration: 240
                easing.type: Easing.OutCubic
            }
        }
        SequentialAnimation {
            PropertyAction { target: root; property: "revealProgress"; value: 0.0 }
            NumberAnimation {
                target: root
                property: "revealProgress"
                to: 1.0
                duration: 260
                easing.type: Easing.OutCubic
            }
        }
    }
}
