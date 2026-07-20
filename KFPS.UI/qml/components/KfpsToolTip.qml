import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

ToolTip {
    id: root

    readonly property real maximumTextWidth: Theme.px(420)
    readonly property real preferredTextWidth: Math.min(
                                                    maximumTextWidth,
                                                    Math.max(Theme.px(80), tipMetrics.advanceWidth))

    delay: 450
    timeout: 14000
    leftPadding: Theme.px(Theme.classicMode ? 5 : 11)
    rightPadding: Theme.px(Theme.classicMode ? 5 : 11)
    topPadding: Theme.px(Theme.classicMode ? 3 : 8)
    bottomPadding: Theme.px(Theme.classicMode ? 3 : 8)
    implicitWidth: preferredTextWidth + leftPadding + rightPadding
    implicitHeight: tipText.implicitHeight + topPadding + bottomPadding

    TextMetrics {
        id: tipMetrics
        text: root.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(10.8)
    }

    contentItem: Text {
        id: tipText
        width: root.preferredTextWidth
        text: root.text
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(10.8)
        font.letterSpacing: 0
        wrapMode: Text.Wrap
        lineHeight: 1.2
        renderType: Text.NativeRendering
    }

    background: Rectangle {
        radius: Theme.framedRadius(Theme.px(6))
        color: Theme.surfaceRaised
        border.width: Theme.classicMode ? Math.max(1, Theme.px(1)) : (Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1)))
        border.color: Theme.classicMode ? Theme.borderStrong : Theme.primary
        opacity: 0.98
    }
}
