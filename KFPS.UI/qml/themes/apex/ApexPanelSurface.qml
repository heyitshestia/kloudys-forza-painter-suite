import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var panel: null
    Rectangle { anchors.fill: parent; color: root.panel && root.panel.soft ? Theme.surfaceSoft : Theme.surface }
    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: Theme.px(root.panel && root.panel.interactionSelected ? 3 : 1)
        color: root.panel && root.panel.interactionSelected ? Theme.primary : Theme.border
    }
}
