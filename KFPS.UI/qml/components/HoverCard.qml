import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    objectName: root.clickable ? "HoverCard:" + root.toolTipText : ""

    default property alias contentData: content.data
    property bool clickable: false
    property bool strong: false
    property bool soft: false
    property string toolTipText: ""
    property real padding: Theme.px(18)
    property alias hovered: hover.hovered
    readonly property bool pressed: tap.pressed
    signal clicked()
    signal doubleClicked()

    KfpsToolTip {
        visible: root.clickable && hover.hovered && root.toolTipText.length > 0
        text: root.toolTipText
    }

    implicitWidth: Theme.px(260)
    implicitHeight: Theme.px(150)
    scale: Theme.terminalMode ? 1.0 : (tap.pressed ? 0.985 : 1.0)

    transform: Translate {
        id: hoverLift
        y: hover.hovered && root.clickable && !Theme.customFrameExclusive && !Theme.terminalMode ? -Theme.px(2) : 0

        Behavior on y {
            enabled: !Theme.reducedMotion
            NumberAnimation {
                duration: 145
                easing.type: Easing.OutCubic
            }
        }
    }
    Behavior on scale {
        enabled: !Theme.reducedMotion
        NumberAnimation {
            duration: 75
            easing.type: Easing.OutCubic
        }
    }

    GlassPanel {
        id: panel
        anchors.fill: parent
        strong: root.strong
        soft: root.soft
        raised: hover.hovered && root.clickable
        glow: hover.hovered && root.clickable
        border.color: hover.hovered && root.clickable ? Theme.primary
                                                       : (root.strong ? Theme.borderStrong : Theme.border)
        Behavior on border.color { ColorAnimation { duration: 130 } }
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.corner(panel.radius)
        color: Theme.hover
        opacity: hover.hovered && root.clickable
                 ? (Theme.terminalMode ? 0.10 : (Theme.customFrameExclusive ? 0.72 : 0.10))
                 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }

    Item {
        id: content
        anchors.fill: parent
        anchors.margins: root.padding
    }

    HoverHandler {
        id: hover
        enabled: root.clickable
        cursorShape: root.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    TapHandler {
        id: tap
        enabled: root.clickable
        onTapped: root.clicked()
        onDoubleTapped: root.doubleClicked()
    }
}
