import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var panel: null
    Rectangle { anchors.fill: parent; color: Theme.surface; border.color: root.panel && root.panel.interactionSelected ? Theme.primary : Theme.border }
    Rectangle { x: 4; y: 0; width: 2; height: parent.height; color: Theme.border; opacity: 0.55 }
}
