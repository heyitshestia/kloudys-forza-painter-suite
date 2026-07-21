import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Shapes 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root

    readonly property bool applicationActive: Window.window ? Window.window.active : true
    readonly property bool motionAllowed: Theme.ambientMotion
                                          && !Theme.reducedMotion
                                          && !screenshotMode
                                          && applicationActive
    property real scanPosition: screenshotMode ? 0.34 : -0.08
    property real signalPhase: screenshotMode ? 8.0 : 1.0
    property real pulseLevel: screenshotMode ? 0.62 : 0.22
    property real glitchOffset: 0.0
    property real glitchStrength: screenshotMode ? 0.16 : 0.0
    property real farDrift: screenshotMode ? Theme.px(8) : -Theme.px(10)
    property real nearDrift: screenshotMode ? -Theme.px(5) : Theme.px(9)
    property real depthPulse: screenshotMode ? 0.68 : 0.28

    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.backgroundA
    }

    Image {
        anchors.fill: parent
        source: assetRoot + "/" + Theme.backdropBaseFile
        fillMode: Image.PreserveAspectCrop
        horizontalAlignment: Image.AlignHCenter
        verticalAlignment: Image.AlignVCenter
        smooth: true
        mipmap: true
        cache: true
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.backdropOverlayTop }
            GradientStop { position: 0.54; color: Theme.backdropOverlayMiddle }
            GradientStop { position: 1.0; color: Theme.backdropOverlayBottom }
        }
    }

    // Three independently moving planes create depth without introducing
    // opaque cards behind the actual workspace.
    Item {
        id: farDepthPlane
        anchors.fill: parent
        x: root.farDrift
        y: -root.farDrift * 0.22
        opacity: 0.22 + root.depthPulse * 0.08

        Shape {
            anchors.fill: parent
            antialiasing: true

            ShapePath {
                strokeWidth: 0
                fillColor: Theme.withAlpha(Theme.signalPrimary, 0.055)
                startX: parent.width * 0.47
                startY: 0
                PathLine { x: parent.width * 0.76; y: 0 }
                PathLine { x: parent.width * 0.60; y: parent.height }
                PathLine { x: parent.width * 0.24; y: parent.height }
                PathLine { x: parent.width * 0.47; y: 0 }
            }

            ShapePath {
                strokeWidth: 0
                fillColor: Theme.withAlpha(Theme.signalSecondary, 0.028)
                startX: parent.width * 0.80
                startY: 0
                PathLine { x: parent.width; y: 0 }
                PathLine { x: parent.width; y: parent.height }
                PathLine { x: parent.width * 0.67; y: parent.height }
                PathLine { x: parent.width * 0.80; y: 0 }
            }
        }
    }

    Shape {
        id: perspectiveGridGlow
        anchors.fill: parent
        x: root.nearDrift
        y: -root.nearDrift * 0.12
        opacity: 0.075 + root.depthPulse * 0.045
        antialiasing: true
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.signalPrimary
            shadowBlur: 0.76
            shadowOpacity: 0.30
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            autoPaddingEnabled: false
        }

        ShapePath {
            strokeWidth: Theme.px(1.6)
            strokeColor: Theme.withAlpha(Theme.signalPrimary, 0.16)
            fillColor: "transparent"
            startX: parent.width * 0.63; startY: parent.height * 0.40
            PathLine { x: parent.width * 0.03; y: parent.height }
        }
        ShapePath {
            strokeWidth: Theme.px(1.6)
            strokeColor: Theme.withAlpha(Theme.signalPrimary, 0.13)
            fillColor: "transparent"
            startX: parent.width * 0.63; startY: parent.height * 0.40
            PathLine { x: parent.width * 0.30; y: parent.height }
        }
        ShapePath {
            strokeWidth: Theme.px(1.6)
            strokeColor: Theme.withAlpha(Theme.signalSecondary, 0.13)
            fillColor: "transparent"
            startX: parent.width * 0.63; startY: parent.height * 0.40
            PathLine { x: parent.width * 0.58; y: parent.height }
        }
        ShapePath {
            strokeWidth: Theme.px(1.6)
            strokeColor: Theme.withAlpha(Theme.signalPrimary, 0.12)
            fillColor: "transparent"
            startX: parent.width * 0.63; startY: parent.height * 0.40
            PathLine { x: parent.width * 0.88; y: parent.height }
        }
        ShapePath {
            strokeWidth: Theme.px(1.6)
            strokeColor: Theme.withAlpha(Theme.signalSecondary, 0.11)
            fillColor: "transparent"
            startX: parent.width * 0.63; startY: parent.height * 0.40
            PathLine { x: parent.width * 1.08; y: parent.height }
        }
        ShapePath {
            strokeWidth: Theme.px(1.4)
            strokeColor: Theme.withAlpha(Theme.signalPrimary, 0.14)
            fillColor: "transparent"
            startX: 0; startY: parent.height * 0.64
            PathLine { x: parent.width; y: parent.height * 0.64 }
        }
        ShapePath {
            strokeWidth: Theme.px(1.4)
            strokeColor: Theme.withAlpha(Theme.signalPrimary, 0.12)
            fillColor: "transparent"
            startX: 0; startY: parent.height * 0.76
            PathLine { x: parent.width; y: parent.height * 0.76 }
        }
        ShapePath {
            strokeWidth: Theme.px(1.4)
            strokeColor: Theme.withAlpha(Theme.signalSecondary, 0.10)
            fillColor: "transparent"
            startX: 0; startY: parent.height * 0.91
            PathLine { x: parent.width; y: parent.height * 0.91 }
        }
    }

    Shape {
        anchors.fill: parent
        x: root.nearDrift * -0.42
        opacity: 0.27
        antialiasing: true

        ShapePath {
            strokeWidth: Math.max(1, Theme.px(1.2))
            strokeColor: Theme.withAlpha(Theme.signalSecondary, 0.30)
            fillColor: "transparent"
            startX: parent.width * 0.10
            startY: parent.height * 0.18
            PathLine { x: parent.width * 0.26; y: parent.height * 0.18 }
            PathLine { x: parent.width * 0.31; y: parent.height * 0.13 }
            PathLine { x: parent.width * 0.48; y: parent.height * 0.13 }
        }
        ShapePath {
            strokeWidth: Math.max(1, Theme.px(1.2))
            strokeColor: Theme.withAlpha(Theme.signalPrimary, 0.34)
            fillColor: "transparent"
            startX: parent.width * 0.72
            startY: parent.height * 0.84
            PathLine { x: parent.width * 0.87; y: parent.height * 0.84 }
            PathLine { x: parent.width * 0.91; y: parent.height * 0.79 }
            PathLine { x: parent.width; y: parent.height * 0.79 }
        }
    }

    // An offset command field gives the workspace the broad asymmetric mass
    // used throughout the source UI without reducing content contrast.
    Shape {
        anchors.fill: parent
        antialiasing: true
        opacity: 0.18 + root.pulseLevel * 0.05

        ShapePath {
            strokeWidth: 0
            fillColor: Theme.withAlpha(Theme.primaryDeep, 0.30)
            startX: root.width * 0.68
            startY: 0
            PathLine { x: root.width; y: 0 }
            PathLine { x: root.width; y: root.height * 0.46 }
            PathLine { x: root.width * 0.91; y: root.height * 0.55 }
            PathLine { x: root.width * 0.74; y: root.height * 0.55 }
            PathLine { x: root.width * 0.80; y: root.height * 0.31 }
            PathLine { x: root.width * 0.62; y: root.height * 0.31 }
            PathLine { x: root.width * 0.68; y: 0 }
        }
    }

    Item {
        id: routeMatrix
        x: root.width * 0.61
        y: root.height * 0.13
        width: root.width * 0.34
        height: root.height * 0.70
        opacity: 0.18

        Repeater {
            model: 9

            Rectangle {
                required property int index
                x: routeMatrix.width * (0.07 + index * 0.105)
                y: index % 2 === 0 ? routeMatrix.height * 0.05 : routeMatrix.height * 0.18
                width: Math.max(1, Theme.px(index === 6 ? 2 : 1))
                height: routeMatrix.height * (index % 3 === 0 ? 0.62 : 0.42)
                color: index === 6 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: index === 6 ? 0.48 : 0.20
            }
        }

        Repeater {
            model: 7

            Rectangle {
                required property int index
                x: routeMatrix.width * (index % 2 === 0 ? 0.05 : 0.22)
                y: routeMatrix.height * (0.12 + index * 0.105)
                width: routeMatrix.width * (index % 3 === 0 ? 0.72 : 0.48)
                height: Math.max(1, Theme.px(index === 4 ? 2 : 1))
                color: index === 4 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: index === 4 ? 0.42 : 0.18
            }
        }

        Shape {
            anchors.fill: parent
            antialiasing: true

            ShapePath {
                strokeWidth: Math.max(1, Theme.px(1))
                strokeColor: Theme.withAlpha(Theme.signalSecondary, 0.42)
                fillColor: "transparent"
                startX: routeMatrix.width * 0.08
                startY: routeMatrix.height * 0.72
                PathLine { x: routeMatrix.width * 0.23; y: routeMatrix.height * 0.56 }
                PathLine { x: routeMatrix.width * 0.48; y: routeMatrix.height * 0.56 }
                PathLine { x: routeMatrix.width * 0.62; y: routeMatrix.height * 0.41 }
                PathLine { x: routeMatrix.width * 0.88; y: routeMatrix.height * 0.41 }
            }
        }
    }

    Item {
        id: scanField
        anchors.fill: parent
        visible: Theme.ambientScanEnabled
        opacity: Theme.glassEffects ? 0.46 : 0.24

        Rectangle {
            x: 0
            y: root.scanPosition * root.height
            width: parent.width
            height: Theme.px(42)
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.withAlpha(Theme.signalSecondary, 0.0) }
                GradientStop { position: 0.48; color: Theme.withAlpha(Theme.signalSecondary, 0.016) }
                GradientStop { position: 0.52; color: Theme.withAlpha(Theme.signalSecondary, 0.040) }
                GradientStop { position: 1.0; color: Theme.withAlpha(Theme.signalSecondary, 0.0) }
            }
        }

        Rectangle {
            x: 0
            y: root.scanPosition * root.height + Theme.px(21)
            width: parent.width
            height: Math.max(1, Theme.px(1))
            color: Theme.signalSecondary
            opacity: 0.075
            layer.enabled: Theme.glassEffects
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Theme.signalSecondary
                shadowBlur: 0.88
                shadowOpacity: 0.20
                shadowHorizontalOffset: 0
                shadowVerticalOffset: 0
            }
        }
    }

    Item {
        anchors.fill: parent
        visible: Theme.glitchInteractionsEnabled && Theme.glassEffects
        opacity: root.glitchStrength
        transform: Translate { x: root.glitchOffset }

        Repeater {
            model: 7

            Rectangle {
                required property int index
                x: index % 2 === 0 ? root.width * 0.09 : root.width * 0.54
                y: root.height * (0.10 + index * 0.117)
                width: root.width * (index % 3 === 0 ? 0.36 : 0.18)
                height: Theme.px(index % 2 === 0 ? 2 : 1)
                color: index === 4 ? Theme.signalSecondary : Theme.signalPrimary
            }
        }
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(28)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(24)
        spacing: Theme.px(4)
        opacity: 0.46

        Repeater {
            model: 12

            Rectangle {
                required property int index
                width: Theme.px(index % 4 === 0 ? 18 : (index % 3 === 0 ? 7 : 3))
                height: Theme.px(2)
                color: index === 9 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: root.signalPhase > index ? 0.86 : 0.15
            }
        }
    }

    SequentialAnimation {
        running: root.motionAllowed && Theme.ambientScanEnabled
        loops: Animation.Infinite
        PropertyAction { target: root; property: "scanPosition"; value: -0.08 }
        PauseAnimation { duration: 2600 }
        NumberAnimation {
            target: root
            property: "scanPosition"
            to: 1.04
            duration: 7600
            easing.type: Easing.InOutCubic
        }
        PauseAnimation { duration: 18400 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "signalPhase"; value: 0.0 }
        NumberAnimation { target: root; property: "signalPhase"; to: 12.0; duration: 980; easing.type: Easing.OutCubic }
        PauseAnimation { duration: 5200 }
        NumberAnimation { target: root; property: "signalPhase"; to: 3.0; duration: 310; easing.type: Easing.InCubic }
        PauseAnimation { duration: 7800 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "farDrift"; to: Theme.px(13); duration: 17800; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "farDrift"; to: -Theme.px(10); duration: 21400; easing.type: Easing.InOutSine }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "nearDrift"; to: -Theme.px(12); duration: 12300; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "nearDrift"; to: Theme.px(9); duration: 15600; easing.type: Easing.InOutSine }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "depthPulse"; to: 0.78; duration: 4100; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "depthPulse"; to: 0.24; duration: 6200; easing.type: Easing.InOutSine }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "pulseLevel"; to: 0.72; duration: 2500; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "pulseLevel"; to: 0.18; duration: 3700; easing.type: Easing.InOutSine }
    }

    SequentialAnimation {
        running: root.motionAllowed && Theme.glitchInteractionsEnabled && Theme.glassEffects
        loops: Animation.Infinite
        PropertyAction { target: root; property: "glitchStrength"; value: 0.0 }
        PropertyAction { target: root; property: "glitchOffset"; value: 0.0 }
        PauseAnimation { duration: 11800 }
        ParallelAnimation {
            NumberAnimation { target: root; property: "glitchStrength"; to: 0.26; duration: 32 }
            NumberAnimation { target: root; property: "glitchOffset"; to: Theme.px(8); duration: 32 }
        }
        ParallelAnimation {
            NumberAnimation { target: root; property: "glitchStrength"; to: 0.08; duration: 48 }
            NumberAnimation { target: root; property: "glitchOffset"; to: -Theme.px(3); duration: 48 }
        }
        ParallelAnimation {
            NumberAnimation { target: root; property: "glitchStrength"; to: 0.0; duration: 110 }
            NumberAnimation { target: root; property: "glitchOffset"; to: 0; duration: 110; easing.type: Easing.OutCubic }
        }
        PauseAnimation { duration: 6700 }
    }
}
