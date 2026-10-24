import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var panel: null
    readonly property bool selected: panel ? panel.interactionSelected : false
    readonly property bool hovered: panel ? panel.interactionHovered : false
    Rectangle {
        anchors.fill: parent
        radius: Theme.px(6)
        border.color: root.selected ? Theme.primary : (root.hovered ? Theme.borderStrong : Theme.border)
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.surfaceTop }
            GradientStop { position: 0.045; color: Theme.surface }
            GradientStop { position: 1; color: Theme.surfaceBottom }
        }
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: 3
        radius: Theme.px(4)
        color: "transparent"
        border.color: Theme.panelInnerBorder
    }
    Rectangle {
        x: Theme.px(10); y: Theme.px(1)
        width: Math.max(0, parent.width - Theme.px(20)); height: 1
        color: Theme.panelTopHighlight
    }
}
