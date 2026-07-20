import QtQuick 6.7
import Kfps.Theme 1.0

Text {
    id: root

    objectName: root.url.length > 0 ? "KfpsLinkText:" + root.text : ""

    property string url: ""
    property string toolTipText: url.length > 0 ? "Open " + url : ""
    readonly property bool interactive: url.length > 0
    readonly property bool hovered: hover.hovered
    readonly property bool pressed: tap.pressed

    color: tap.pressed
           ? Theme.warning
           : (hover.hovered ? Theme.primaryHot : Theme.primaryBright)
    topPadding: Theme.px(7)
    bottomPadding: Theme.px(7)
    verticalAlignment: Text.AlignVCenter
    font.underline: hover.hovered || activeFocus
    activeFocusOnTab: interactive
    scale: tap.pressed ? 0.985 : 1.0

    Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 95 } }
    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }

    HoverHandler {
        id: hover
        enabled: root.interactive
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        id: tap
        enabled: root.interactive
        onTapped: Qt.openUrlExternally(root.url)
    }

    Keys.onReturnPressed: if (root.interactive) Qt.openUrlExternally(root.url)
    Keys.onEnterPressed: if (root.interactive) Qt.openUrlExternally(root.url)
    Keys.onSpacePressed: if (root.interactive) Qt.openUrlExternally(root.url)

    KfpsToolTip {
        visible: hover.hovered && root.toolTipText.length > 0
        text: root.toolTipText
    }
}
