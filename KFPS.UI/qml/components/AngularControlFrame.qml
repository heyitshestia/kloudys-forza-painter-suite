import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Shapes 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property color fillColor: Theme.surfaceStrong
    property color borderColor: Theme.border
    property color accentColor: Theme.signalSecondary
    property bool hovered: false
    property bool pressed: false
    property bool selected: false
    property bool focused: false
    property bool panelFrame: false
    property bool enclosedPanel: false
    property bool decorationVisible: true
    property bool frameEnabled: true
    property real cutOverride: -1
    property real notchOverride: -1
    property real strokeOverride: -1

    readonly property real cutSize: Math.max(
                                               Theme.px(2),
                                               cutOverride >= 0
                                               ? cutOverride
                                               : Theme.px(panelFrame ? Theme.angularPanelCutSize : Theme.angularCutSize))
    readonly property real notchSize: Math.max(
                                                 Theme.px(1.5),
                                                 notchOverride >= 0
                                                 ? notchOverride
                                                 : Theme.px(Theme.angularNotchSize))
    readonly property real strokeSize: Math.max(
                                                  1,
                                                  strokeOverride >= 0
                                                  ? strokeOverride
                                                  : Theme.px(Theme.angularStrokeWidth))
    readonly property real edgeInset: strokeSize * 0.55
    readonly property real glowInset: edgeInset + Theme.px(panelFrame ? 1.8 : 1.35)
    readonly property bool openPanel: panelFrame && Theme.floatingPanelsEnabled && !enclosedPanel
    readonly property real stateEnergy: pressed ? 1.0 : (selected ? 0.88 : (focused ? 0.76 : (hovered ? 0.64 : 0.0)))
    property real acquisition: screenshotMode ? stateEnergy : 0.0
    property real glitchOffset: 0.0
    property real sweepProgress: screenshotMode && stateEnergy > 0 ? 0.66 : -0.08
    property real selectedPulse: screenshotMode && selected ? 0.74 : 0.34

    visible: Theme.angularControlsEnabled && decorationVisible
    opacity: frameEnabled ? 1.0 : 0.44
    clip: true

    onStateEnergyChanged: acquisition = stateEnergy
    onHoveredChanged: {
        if (hovered && !Theme.reducedMotion && !screenshotMode) {
            acquisitionSweep.restart()
            if (Theme.glitchInteractionsEnabled)
                hoverBurst.restart()
        } else if (!hovered) {
            glitchOffset = 0
            sweepProgress = -0.08
        }
    }

    Behavior on acquisition {
        enabled: !Theme.reducedMotion && !screenshotMode
        NumberAnimation { duration: Theme.interactionSweepDuration; easing.type: Easing.OutCubic }
    }

    Shape {
        id: lowerPlate
        visible: !root.openPanel
        anchors.fill: parent
        y: Theme.px(root.pressed ? 1 : 2.5)
        opacity: root.selected ? 0.92 : (root.hovered ? 0.68 : 0.38)
        antialiasing: true

        ShapePath {
            strokeWidth: 0
            fillColor: root.selected ? Theme.primaryDeep : Theme.withAlpha(Theme.primary, 0.44)
            startX: root.edgeInset + root.cutSize
            startY: root.edgeInset
            PathLine { x: root.width - root.edgeInset - root.notchSize; y: root.edgeInset }
            PathLine { x: root.width - root.edgeInset; y: root.edgeInset + root.notchSize }
            PathLine { x: root.width - root.edgeInset; y: root.height - root.edgeInset - root.cutSize }
            PathLine { x: root.width - root.edgeInset - root.cutSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize + root.notchSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.edgeInset + root.cutSize }
            PathLine { x: root.edgeInset + root.cutSize; y: root.edgeInset }
        }
    }

    Shape {
        id: softEdgeLight
        visible: !root.openPanel
        anchors.fill: parent
        opacity: Theme.glassEffects
                 ? (root.panelFrame ? 0.38 : 0.18 + root.stateEnergy * 0.32)
                 : 0
        antialiasing: true
        layer.enabled: Theme.glassEffects
        layer.smooth: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: root.focused || root.selected ? root.accentColor : root.borderColor
            shadowBlur: root.panelFrame ? 0.34 : 0.54
            shadowOpacity: root.panelFrame ? 0.34 : 0.52
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
        }

        ShapePath {
            strokeWidth: Math.max(root.strokeSize * 4.2, Theme.px(2.8))
            strokeColor: root.focused || root.selected
                         ? Theme.withAlpha(root.accentColor, 0.44)
                         : Theme.withAlpha(root.borderColor, 0.34)
            fillColor: "transparent"
            joinStyle: ShapePath.MiterJoin
            startX: root.edgeInset + root.cutSize
            startY: root.edgeInset
            PathLine { x: root.width - root.edgeInset - root.notchSize; y: root.edgeInset }
            PathLine { x: root.width - root.edgeInset; y: root.edgeInset + root.notchSize }
            PathLine { x: root.width - root.edgeInset; y: root.height - root.edgeInset - root.cutSize }
            PathLine { x: root.width - root.edgeInset - root.cutSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize + root.notchSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.edgeInset + root.cutSize }
            PathLine { x: root.edgeInset + root.cutSize; y: root.edgeInset }
        }
    }

    Shape {
        id: cyanEcho
        visible: !root.openPanel
        anchors.fill: parent
        x: -root.glitchOffset
        opacity: Theme.glassEffects
                 ? Math.min(0.78, Math.abs(root.glitchOffset) / Math.max(1, Theme.px(2.4)))
                 : 0
        antialiasing: true

        ShapePath {
            strokeWidth: root.strokeSize
            strokeColor: root.accentColor
            fillColor: "transparent"
            joinStyle: ShapePath.MiterJoin
            startX: root.edgeInset + root.cutSize
            startY: root.edgeInset
            PathLine { x: root.width - root.edgeInset - root.notchSize; y: root.edgeInset }
            PathLine { x: root.width - root.edgeInset; y: root.edgeInset + root.notchSize }
            PathLine { x: root.width - root.edgeInset; y: root.height - root.edgeInset - root.cutSize }
            PathLine { x: root.width - root.edgeInset - root.cutSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize + root.notchSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.edgeInset + root.cutSize }
            PathLine { x: root.edgeInset + root.cutSize; y: root.edgeInset }
        }
    }

    Shape {
        id: mainPlate
        visible: !root.openPanel
        anchors.fill: parent
        x: root.glitchOffset * 0.32
        y: root.pressed ? Theme.px(1.0) : 0
        antialiasing: true
        layer.enabled: Theme.glassEffects
                       && !screenshotMode
                       && !root.panelFrame
                       && root.stateEnergy > 0
        layer.smooth: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: root.focused ? root.accentColor : root.borderColor
            shadowBlur: 0.54
            shadowOpacity: 0.44
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
        }

        ShapePath {
            strokeWidth: root.focused ? Math.max(root.strokeSize, Theme.px(1.6)) : root.strokeSize
            strokeColor: root.focused ? root.accentColor : root.borderColor
            fillColor: root.fillColor
            joinStyle: ShapePath.MiterJoin
            startX: root.edgeInset + root.cutSize
            startY: root.edgeInset
            PathLine { x: root.width - root.edgeInset - root.notchSize; y: root.edgeInset }
            PathLine { x: root.width - root.edgeInset; y: root.edgeInset + root.notchSize }
            PathLine { x: root.width - root.edgeInset; y: root.height - root.edgeInset - root.cutSize }
            PathLine { x: root.width - root.edgeInset - root.cutSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize + root.notchSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.edgeInset + root.cutSize }
            PathLine { x: root.edgeInset + root.cutSize; y: root.edgeInset }
        }
    }

    Shape {
        id: materialWash
        visible: !root.openPanel
        anchors.fill: parent
        x: root.glitchOffset * 0.32
        y: root.pressed ? Theme.px(1.0) : 0
        opacity: root.panelFrame ? 0.34 : (root.hovered || root.selected ? 0.82 : 0.46)
        antialiasing: true

        ShapePath {
            strokeWidth: 0
            fillGradient: LinearGradient {
                x1: 0
                y1: 0
                x2: 0
                y2: root.height
                GradientStop {
                    position: 0.0
                    color: Theme.withAlpha(root.hovered || root.selected ? Theme.signalPrimary : Theme.primaryBright,
                                           root.hovered || root.selected ? 0.18 : 0.055)
                }
                GradientStop {
                    position: 0.42
                    color: Theme.withAlpha(Theme.signalPrimary, root.panelFrame ? 0.018 : 0.025)
                }
                GradientStop {
                    position: 1.0
                    color: Theme.withAlpha(Theme.backgroundA, root.panelFrame ? 0.12 : 0.20)
                }
            }
            startX: root.edgeInset + root.cutSize
            startY: root.edgeInset
            PathLine { x: root.width - root.edgeInset - root.notchSize; y: root.edgeInset }
            PathLine { x: root.width - root.edgeInset; y: root.edgeInset + root.notchSize }
            PathLine { x: root.width - root.edgeInset; y: root.height - root.edgeInset - root.cutSize }
            PathLine { x: root.width - root.edgeInset - root.cutSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize + root.notchSize; y: root.height - root.edgeInset }
            PathLine { x: root.edgeInset + root.cutSize; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.height - root.edgeInset - root.notchSize }
            PathLine { x: root.edgeInset; y: root.edgeInset + root.cutSize }
            PathLine { x: root.edgeInset + root.cutSize; y: root.edgeInset }
        }
    }

    // The glow is drawn inside the plate. An exterior blur is both easy to clip
    // and prone to bleeding into adjacent controls at compact UI scales.
    Shape {
        id: innerBloom
        visible: !root.openPanel
        anchors.fill: parent
        opacity: Theme.glassEffects
                 ? (root.panelFrame
                    ? 0.34 + root.selectedPulse * 0.12
                    : 0.18 + root.stateEnergy * 0.32)
                 : 0
        antialiasing: true

        ShapePath {
            strokeWidth: Math.max(Theme.px(root.panelFrame ? 5.2 : 4.2), root.strokeSize * 3.2)
            strokeColor: Theme.withAlpha(root.focused || root.selected
                                         ? root.accentColor : root.borderColor,
                                         root.panelFrame ? 0.18 : 0.22)
            fillColor: "transparent"
            joinStyle: ShapePath.MiterJoin
            startX: root.glowInset + root.cutSize
            startY: root.glowInset
            PathLine { x: root.width - root.glowInset - root.notchSize; y: root.glowInset }
            PathLine { x: root.width - root.glowInset; y: root.glowInset + root.notchSize }
            PathLine { x: root.width - root.glowInset; y: root.height - root.glowInset - root.cutSize }
            PathLine { x: root.width - root.glowInset - root.cutSize; y: root.height - root.glowInset }
            PathLine { x: root.glowInset + root.cutSize + root.notchSize; y: root.height - root.glowInset }
            PathLine { x: root.glowInset + root.cutSize; y: root.height - root.glowInset - root.notchSize }
            PathLine { x: root.glowInset; y: root.height - root.glowInset - root.notchSize }
            PathLine { x: root.glowInset; y: root.glowInset + root.cutSize }
            PathLine { x: root.glowInset + root.cutSize; y: root.glowInset }
        }
    }

    Shape {
        id: innerCoreLight
        visible: !root.openPanel
        anchors.fill: parent
        opacity: root.panelFrame
                 ? 0.42 + root.selectedPulse * 0.12
                 : 0.34 + root.stateEnergy * 0.48
        antialiasing: true

        ShapePath {
            strokeWidth: Math.max(Theme.px(1.15), root.strokeSize)
            strokeColor: root.focused || root.selected
                         ? Theme.withAlpha(root.accentColor, 0.92)
                         : Theme.withAlpha(root.borderColor, 0.72)
            fillColor: "transparent"
            joinStyle: ShapePath.MiterJoin
            startX: root.glowInset + root.cutSize
            startY: root.glowInset
            PathLine { x: root.width - root.glowInset - root.notchSize; y: root.glowInset }
            PathLine { x: root.width - root.glowInset; y: root.glowInset + root.notchSize }
            PathLine { x: root.width - root.glowInset; y: root.height - root.glowInset - root.cutSize }
            PathLine { x: root.width - root.glowInset - root.cutSize; y: root.height - root.glowInset }
            PathLine { x: root.glowInset + root.cutSize + root.notchSize; y: root.height - root.glowInset }
            PathLine { x: root.glowInset + root.cutSize; y: root.height - root.glowInset - root.notchSize }
            PathLine { x: root.glowInset; y: root.height - root.glowInset - root.notchSize }
            PathLine { x: root.glowInset; y: root.glowInset + root.cutSize }
            PathLine { x: root.glowInset + root.cutSize; y: root.glowInset }
        }
    }

    Rectangle {
        visible: !root.openPanel
        anchors.left: parent.left
        anchors.leftMargin: root.glowInset + root.cutSize + Theme.px(2)
        anchors.top: parent.top
        anchors.topMargin: root.glowInset
        width: Math.max(Theme.px(18), parent.width * (root.panelFrame ? 0.18 : 0.26))
        height: Math.max(1, Theme.px(root.focused || root.selected ? 1.8 : 1.2))
        color: root.focused || root.selected ? root.accentColor : Theme.signalPrimary
        opacity: root.panelFrame ? 0.56 : (0.42 + root.stateEnergy * 0.50)
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: root.focused || root.selected ? root.accentColor : Theme.signalPrimary
            shadowBlur: 0.72
            shadowOpacity: root.panelFrame ? 0.54 : 0.72
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            autoPaddingEnabled: false
        }
    }

    Rectangle {
        visible: !root.panelFrame && root.stateEnergy > 0
        x: root.glowInset + root.cutSize
        y: root.height - root.glowInset - Math.max(1, Theme.px(2))
        width: Math.max(Theme.px(14), (root.width - root.cutSize * 2) * root.acquisition)
        height: Math.max(1, Theme.px(1.5))
        color: root.accentColor
        opacity: 0.88
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: root.accentColor
            shadowBlur: 0.82
            shadowOpacity: 0.74
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            autoPaddingEnabled: false
        }
    }

    Item {
        anchors.fill: parent
        visible: root.openPanel

        Rectangle {
            x: root.cutSize
            y: root.edgeInset
            width: Math.min(parent.width * 0.46, Math.max(Theme.px(72), parent.width * 0.30))
            height: Theme.px(5)
            color: Theme.withAlpha(root.borderColor, 0.10)
        }
        Rectangle {
            x: root.cutSize
            y: root.edgeInset + Theme.px(1)
            width: Math.min(parent.width * 0.46, Math.max(Theme.px(72), parent.width * 0.30))
            height: Math.max(1, Theme.px(1.2))
            color: root.borderColor
            opacity: root.selected || root.focused ? 0.92 : 0.62
        }
        Rectangle {
            x: root.edgeInset
            y: root.cutSize
            width: Theme.px(5)
            height: Math.min(Theme.px(54), Math.max(Theme.px(20), parent.height * 0.10))
            color: Theme.withAlpha(root.borderColor, 0.09)
        }
        Rectangle {
            x: root.edgeInset + Theme.px(1)
            y: root.cutSize
            width: Math.max(1, Theme.px(1.2))
            height: Math.min(Theme.px(54), Math.max(Theme.px(20), parent.height * 0.10))
            color: root.borderColor
            opacity: root.selected || root.focused ? 0.90 : 0.58
        }
        Rectangle {
            x: root.cutSize + Math.min(parent.width * 0.46, Math.max(Theme.px(72), parent.width * 0.30)) - Theme.px(14)
            y: root.edgeInset
            width: Theme.px(14)
            height: Math.max(1, Theme.px(1.4))
            color: root.accentColor
            opacity: root.selected || root.focused ? 0.92 : 0.56
        }
    }

    Rectangle {
        visible: !root.openPanel
        anchors.left: parent.left
        anchors.leftMargin: root.cutSize + Theme.px(3)
        anchors.top: parent.top
        anchors.topMargin: root.edgeInset + Theme.px(1)
        width: Math.max(Theme.px(14), parent.width * (root.panelFrame ? 0.24 : 0.34))
        height: Math.max(1, Theme.px(1))
        color: root.focused || root.selected ? root.accentColor : Theme.signalPrimary
        opacity: root.panelFrame ? 0.42 : (0.28 + root.stateEnergy * 0.48)
    }

    Rectangle {
        visible: !root.openPanel
        anchors.left: parent.left
        anchors.leftMargin: root.cutSize + Theme.px(2)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.edgeInset
        width: Math.max(0, (parent.width - root.cutSize * 2 - Theme.px(8)) * root.acquisition)
        height: Math.max(1, Theme.px(root.focused ? 2 : 1))
        color: root.accentColor
        opacity: root.stateEnergy > 0 ? 0.92 : 0
    }

    Rectangle {
        visible: !root.openPanel && root.stateEnergy > 0
        x: root.cutSize + (root.width - root.cutSize * 2) * root.sweepProgress
        anchors.top: parent.top
        anchors.topMargin: root.notchSize + Theme.px(2)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.cutSize + Theme.px(2)
        width: Math.max(1, Theme.px(1.4))
        color: root.accentColor
        opacity: root.hovered || root.focused ? 0.72 : 0.30
        layer.enabled: Theme.glassEffects && !screenshotMode
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: root.accentColor
            shadowBlur: 0.72
            shadowOpacity: 0.62
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
        }
    }

    Rectangle {
        visible: !root.openPanel
        anchors.left: parent.left
        anchors.leftMargin: root.edgeInset
        anchors.top: parent.top
        anchors.topMargin: root.cutSize
        width: Math.max(1, Theme.px(2))
        height: Math.max(Theme.px(5), (parent.height - root.cutSize * 2) * root.acquisition)
        color: root.selected || root.focused ? root.accentColor : Theme.signalPrimary
        opacity: root.stateEnergy > 0 ? 0.96 : 0.28
    }

    Row {
        visible: !Theme.glyphRailsEnabled
        anchors.right: parent.right
        anchors.rightMargin: root.notchSize + Theme.px(4)
        anchors.top: parent.top
        anchors.topMargin: Theme.px(3)
        spacing: Theme.px(2)
        opacity: 0.30 + root.stateEnergy * 0.62

        Repeater {
            model: 3
            Rectangle {
                required property int index
                width: Math.max(1, Theme.px(index === 2 ? 7 : 3))
                height: Math.max(1, Theme.px(1.3))
                color: index === 2 && root.stateEnergy > 0 ? root.accentColor : Theme.signalPrimary
            }
        }
    }

    SequentialAnimation {
        id: hoverBurst
        NumberAnimation {
            target: root
            property: "glitchOffset"
            from: 0
            to: Theme.px(2.5) * Theme.glitchIntensity
            duration: 28
            easing.type: Easing.OutQuad
        }
        NumberAnimation {
            target: root
            property: "glitchOffset"
            to: -Theme.px(1.2) * Theme.glitchIntensity
            duration: 34
        }
        NumberAnimation {
            target: root
            property: "glitchOffset"
            to: 0
            duration: 92
            easing.type: Easing.OutCubic
        }
    }

    SequentialAnimation {
        id: acquisitionSweep
        PropertyAction { target: root; property: "sweepProgress"; value: -0.08 }
        NumberAnimation {
            target: root
            property: "sweepProgress"
            to: 1.08
            duration: Theme.interactionSweepDuration + 70
            easing.type: Easing.OutCubic
        }
    }

    SequentialAnimation {
        running: root.selected
                 && Theme.ambientMotion
                 && !Theme.reducedMotion
                 && !screenshotMode
        loops: Animation.Infinite
        NumberAnimation {
            target: root
            property: "selectedPulse"
            to: 0.92
            duration: 1180
            easing.type: Easing.InOutSine
        }
        NumberAnimation {
            target: root
            property: "selectedPulse"
            to: 0.28
            duration: 1760
            easing.type: Easing.InOutSine
        }
    }
}
