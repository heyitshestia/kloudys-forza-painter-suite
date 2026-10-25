import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var panel: null
    Rectangle {
        anchors.fill: parent
        radius: Theme.px(3)
        color: Theme.surface
        border.color: root.panel && root.panel.interactionSelected ? Theme.primary : Theme.border
    }
    Rectangle {
        x: 1; y: 1; width: Math.max(0, parent.width - 2); height: 1
        color: Theme.panelTopHighlight
    }
}
