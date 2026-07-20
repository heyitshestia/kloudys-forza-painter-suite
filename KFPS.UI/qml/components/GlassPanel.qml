import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Rectangle {
    id: root
    property bool strong: false
    property bool soft: false
    property bool raised: false
    property bool glow: false
    property real panelOpacity: 1.0
    property real shadowStrength: raised ? 0.86 : (strong ? 0.72 : 0.64)
    readonly property var backdropSource: Window.window && Window.window.glassBackdropSource ? Window.window.glassBackdropSource : null
    readonly property point backdropOrigin: backdropSource ? mapToItem(backdropSource, 0, 0) : Qt.point(0, 0)
    readonly property bool backdropBlurActive: !Theme.terminalMode && Theme.glassEffects && Theme.glassBackdropEnabled && backdropSource && width > 2 && height > 2
    readonly property bool roundedContentMaskActive: radius > 0 && width > 2 && height > 2
    readonly property bool locatorVisible: Theme.panelLocatorEnabled && (strong || raised)
    readonly property bool telemetryVisible: Theme.equipmentAccentsEnabled
                                               && (strong || raised)
                                               && width >= Theme.px(130)
                                               && height >= Theme.px(54)
    property real locatorProgress: screenshotMode && locatorVisible ? 0.62 : 0.0
    property real telemetryPhase: screenshotMode && telemetryVisible ? 3.4 : 1.0

    radius: Theme.framedRadius(Theme.px(14))
    color: "transparent"
    opacity: panelOpacity
    border.width: Theme.terminalMode ? 0 : (Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1)))
    border.color: raised ? Theme.borderStrong : (strong ? Theme.borderStrong : (soft ? Theme.borderSoft : Theme.border))
    antialiasing: !Theme.terminalMode
    clip: true

    gradient: Gradient {
        GradientStop {
            position: 0.0
            color: Theme.panelGradientTop(root.soft, root.strong)
        }
        GradientStop {
            position: 0.42
            color: Theme.panelGradientMiddle(root.soft, root.strong)
        }
        GradientStop {
            position: 1.0
            color: Theme.panelGradientBottom(root.soft, root.strong)
        }
    }

    layer.enabled: !Theme.terminalMode && Theme.glassEffects && !screenshotMode
    layer.smooth: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: root.glow ? Theme.panelGlowShadow : Theme.shadow
        shadowBlur: root.raised || root.strong ? 0.98 : 0.82
        shadowHorizontalOffset: 0
        shadowVerticalOffset: root.raised ? Theme.px(9) : Theme.px(root.strong ? 7 : 5)
        shadowOpacity: root.glow ? 0.82 : root.shadowStrength
    }

    Rectangle {
        id: roundedContentMask
        anchors.fill: parent
        radius: Theme.corner(root.radius)
        color: "#ffffffff"
        visible: false
        antialiasing: true
    }

    ShaderEffectSource {
        id: backdropCapture
        visible: false
        sourceItem: root.backdropBlurActive ? root.backdropSource : null
        sourceRect: Qt.rect(root.backdropOrigin.x, root.backdropOrigin.y, root.width, root.height)
        textureSize: Qt.size(Math.max(2, root.width * Theme.glassBackdropDownsample), Math.max(2, root.height * Theme.glassBackdropDownsample))
        live: root.backdropBlurActive
        recursive: false
        hideSource: false
        mipmap: true
    }

    Item {
        id: roundedContentLayer
        anchors.fill: parent
        layer.enabled: root.roundedContentMaskActive
        layer.smooth: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: roundedContentMask
            maskThresholdMin: 0.0
            maskSpreadAtMin: 0.035
            maskThresholdMax: 1.0
            maskSpreadAtMax: 0.0
            autoPaddingEnabled: false
        }

        MultiEffect {
            anchors.fill: parent
            visible: root.backdropBlurActive
            source: backdropCapture
            blurEnabled: true
            blur: Theme.glassBackdropBlur
            blurMax: Theme.glassBackdropBlurMax
            blurMultiplier: Theme.glassBackdropBlurMultiplier
            brightness: Theme.glassBackdropBrightness
            contrast: Theme.glassBackdropContrast
            saturation: Theme.glassBackdropSaturation
            opacity: Theme.glassBackdropOpacity
            autoPaddingEnabled: false
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.px(1.5)
            radius: Theme.corner(Math.max(0, root.radius - Theme.px(1.5)))
            color: Theme.panelConvexCenterGlow
            opacity: root.soft ? 0.13 : (root.strong || root.raised ? 0.18 : 0.15)
            antialiasing: true
        }

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Math.max(1, Theme.px(root.strong || root.raised ? 24 : 18))
            radius: Theme.corner(root.radius)
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop {
                    position: 0.0
                    color: Theme.panelConvexLeftHighlight
                }
                GradientStop {
                    position: 1.0
                    color: "#00ffffff"
                }
            }
            opacity: root.soft ? 0.38 : (root.strong || root.raised ? 0.54 : 0.46)
        }

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Math.max(1, Theme.px(root.strong || root.raised ? 26 : 20))
            radius: Theme.corner(root.radius)
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop {
                    position: 0.0
                    color: "#00000000"
                }
                GradientStop {
                    position: 1.0
                    color: Theme.panelConvexRightShadow
                }
            }
            opacity: root.soft ? 0.46 : (root.strong || root.raised ? 0.64 : 0.54)
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.max(1, Theme.px(root.strong || root.raised ? 26 : 20))
            radius: Theme.corner(root.radius)
            gradient: Gradient {
                GradientStop {
                    position: 0.0
                    color: "#00000000"
                }
                GradientStop {
                    position: 1.0
                    color: Theme.panelConvexBottomShadow
                }
            }
            opacity: root.soft ? 0.46 : (root.strong || root.raised ? 0.66 : 0.56)
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: Theme.px(1)
            anchors.rightMargin: Theme.px(1)
            anchors.topMargin: Theme.px(1)
            height: Math.max(1, Theme.px(root.strong ? 2.6 : 1.8))
            radius: Theme.corner(Math.max(0, root.radius - Theme.px(1)))
            visible: !Theme.customFrameExclusive
            color: Theme.panelTopHighlight
            opacity: Theme.panelHighlightOpacity(root.soft, root.strong)
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.px(1)
            radius: Theme.corner(Math.max(0, root.radius - Theme.px(1)))
            visible: !Theme.customFrameExclusive
            color: "transparent"
            border.width: Math.max(1, Theme.px(1))
            border.color: root.strong ? Theme.panelStrongInnerBorder : Theme.panelInnerBorder
            opacity: root.soft ? 0.74 : 0.86
            antialiasing: true
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.px(2)
            radius: Theme.corner(Math.max(0, root.radius - Theme.px(2)))
            color: root.strong ? Theme.panelStrongOverlay : Theme.panelOverlay
            opacity: Theme.panelOverlayOpacity(root.soft)
            antialiasing: true
        }

        Image {
            anchors.fill: parent
            visible: Theme.panelNoiseFile.length > 0
            source: visible ? assetRoot + "/" + Theme.panelNoiseFile : ""
            fillMode: Image.Tile
            opacity: Theme.panelNoiseOpacity(root.soft, root.strong)
            smooth: true
            clip: true
        }

        Image {
            anchors.fill: parent
            visible: Theme.panelGlintFile.length > 0
            source: visible ? assetRoot + "/" + Theme.panelGlintFile : ""
            fillMode: Image.Tile
            opacity: root.soft ? 0.025 : (root.strong ? 0.045 : 0.035)
            smooth: true
            clip: true
        }

        Image {
            anchors.fill: parent
            visible: Theme.panelRefractionFile.length > 0
            source: visible ? assetRoot + "/" + Theme.panelRefractionFile : ""
            fillMode: Image.Tile
            opacity: Theme.panelRefractionOpacity * (root.strong || root.raised ? 1.0 : 0.76)
            smooth: true
            clip: true
        }

        BorderImage {
            anchors.fill: parent
            visible: Theme.panelEdgeFile.length > 0
            source: visible ? assetRoot + "/" + Theme.panelEdgeFile : ""
            border.left: 42
            border.right: 42
            border.top: 42
            border.bottom: 42
            horizontalTileMode: BorderImage.Stretch
            verticalTileMode: BorderImage.Stretch
            opacity: Theme.panelEdgeOpacity * (root.strong || root.raised ? 1.0 : 0.68)
            smooth: true
        }

        Image {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            visible: Theme.goldTrimFile.length > 0
            source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
            height: Math.max(1, Theme.px(root.strong ? 2.1 : 1.25))
            fillMode: Image.TileHorizontally
            opacity: Theme.goldTrimOpacity * (root.strong || root.raised ? 1.0 : 0.56)
            smooth: true
        }

        Image {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            visible: Theme.goldTrimFile.length > 0
            source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
            height: Math.max(1, Theme.px(root.strong ? 1.6 : 1.0))
            fillMode: Image.TileHorizontally
            opacity: Theme.goldTrimOpacity * (root.strong || root.raised ? 0.72 : 0.36)
            smooth: true
        }

        Image {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            visible: Theme.goldTrimFile.length > 0
            source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
            width: Math.max(1, Theme.px(1))
            fillMode: Image.TileVertically
            opacity: Theme.goldTrimOpacity * (root.strong || root.raised ? 0.58 : 0.26)
            smooth: true
        }

        Image {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            visible: Theme.goldTrimFile.length > 0
            source: visible ? assetRoot + "/" + Theme.goldTrimFile : ""
            width: Math.max(1, Theme.px(1))
            fillMode: Image.TileVertically
            opacity: Theme.goldTrimOpacity * (root.strong || root.raised ? 0.58 : 0.26)
            smooth: true
        }

        Rectangle {
            visible: root.locatorVisible
            x: Theme.px(14) + Math.max(0, root.width - Theme.px(62)) * root.locatorProgress
            y: Theme.px(2)
            width: Theme.px(24)
            height: Math.max(1, Theme.px(2))
            radius: Theme.corner(height / 2)
            color: Theme.signalPrimary
            opacity: Theme.locatorOpacity * (locatorHover.hovered ? 1.0 : 0.54)
            Behavior on opacity {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
            }
        }
    }

    Item {
        anchors.fill: parent
        z: 80
        enabled: false
        visible: root.telemetryVisible

        Row {
            anchors.right: parent.right
            anchors.rightMargin: Theme.px(15)
            anchors.top: parent.top
            anchors.topMargin: Theme.px(2)
            spacing: Theme.px(2)

            Repeater {
                model: 5

                Rectangle {
                    required property int index
                    width: Theme.px(index === 4 ? 8 : (index % 2 === 0 ? 4 : 2))
                    height: Theme.px(2)
                    radius: Theme.corner(height / 2)
                    color: index === 3 ? Theme.signalSecondary : Theme.signalPrimary
                    opacity: root.telemetryPhase > index ? 0.82 : 0.10

                    Behavior on opacity {
                        enabled: !Theme.reducedMotion
                        NumberAnimation { duration: 82; easing.type: Easing.OutCubic }
                    }
                }
            }
        }

        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: Theme.px(4)
            anchors.top: parent.top
            anchors.topMargin: Theme.px(10)
            width: Theme.px(2)
            height: Theme.px(7)
            radius: Theme.corner(width / 2)
            color: Theme.signalSecondary
            opacity: root.telemetryPhase >= 4.0 ? 0.78 : 0.16

            Behavior on opacity {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: 100; easing.type: Easing.OutCubic }
            }
        }
    }


    HoverHandler {
        id: locatorHover
        enabled: root.locatorVisible
        onHoveredChanged: {
            if (!hovered || screenshotMode)
                return
            if (Theme.reducedMotion) {
                root.locatorProgress = 0.62
                root.telemetryPhase = 3.4
            } else {
                locatorAnimation.restart()
                panelTelemetryAnimation.restart()
            }
        }
    }

    SequentialAnimation {
        id: locatorAnimation
        PropertyAction { target: root; property: "locatorProgress"; value: 0.08 }
        NumberAnimation {
            target: root
            property: "locatorProgress"
            to: 0.72
            duration: 300
            easing.type: Easing.OutCubic
        }
    }

    SequentialAnimation {
        id: panelTelemetryAnimation
        PropertyAction { target: root; property: "telemetryPhase"; value: 0.0 }
        NumberAnimation {
            target: root
            property: "telemetryPhase"
            to: 5.0
            duration: 260
            easing.type: Easing.OutCubic
        }
        PauseAnimation { duration: 110 }
        NumberAnimation {
            target: root
            property: "telemetryPhase"
            to: 2.0
            duration: 170
            easing.type: Easing.InOutCubic
        }
    }
}
