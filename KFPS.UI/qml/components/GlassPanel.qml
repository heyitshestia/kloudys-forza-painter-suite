import QtQuick 6.7
import QtQuick.Effects 6.7
import Kfps.Theme 1.0

Rectangle {
    id: root
    property bool strong: false
    property bool soft: false
    property bool raised: false
    property bool glow: false
    property real panelOpacity: 1.0
    property real shadowStrength: raised ? 0.78 : (strong ? 0.64 : 0.56)

    radius: Theme.px(14)
    color: "transparent"
    opacity: panelOpacity
    border.width: Math.max(1, Theme.px(1))
    border.color: raised ? Theme.borderStrong : (strong ? Theme.borderStrong : (soft ? Theme.borderSoft : Theme.border))
    antialiasing: true
    clip: true

    gradient: Gradient {
        GradientStop { position: 0.0; color: Theme.panelGradientTop(root.soft, root.strong) }
        GradientStop { position: 0.42; color: Theme.panelGradientMiddle(root.soft, root.strong) }
        GradientStop { position: 1.0; color: Theme.panelGradientBottom(root.soft, root.strong) }
    }

    layer.enabled: Theme.glassEffects && !screenshotMode
    layer.smooth: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: root.glow ? Theme.panelGlowShadow : Theme.shadow
        shadowBlur: root.raised || root.strong ? 0.92 : 0.72
        shadowHorizontalOffset: 0
        shadowVerticalOffset: root.raised ? Theme.px(8) : Theme.px(root.strong ? 6 : 4)
        shadowOpacity: root.glow ? 0.82 : root.shadowStrength
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: Theme.px(1)
        anchors.rightMargin: Theme.px(1)
        anchors.topMargin: Theme.px(1)
        height: Math.max(1, Theme.px(root.strong ? 2 : 1.4))
        radius: Math.max(0, root.radius - Theme.px(1))
        color: Theme.panelTopHighlight
        opacity: Theme.panelHighlightOpacity(root.soft, root.strong)
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: Theme.px(1)
        radius: Math.max(0, root.radius - Theme.px(1))
        color: "transparent"
        border.width: Math.max(1, Theme.px(1))
        border.color: root.strong ? Theme.panelStrongInnerBorder : Theme.panelInnerBorder
        opacity: root.soft ? 0.82 : 0.92
        antialiasing: true
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: Theme.px(2)
        radius: Math.max(0, root.radius - Theme.px(2))
        color: root.strong ? Theme.panelStrongOverlay : Theme.panelOverlay
        opacity: Theme.panelOverlayOpacity(root.soft)
        antialiasing: true
    }

    Image {
        anchors.fill: parent
        source: assetRoot + "/glass-noise.png"
        fillMode: Image.Tile
        opacity: Theme.panelNoiseOpacity(root.soft, root.strong)
        smooth: true
        clip: true
    }
}
