import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    enabled: false
    property var panel: null
    readonly property bool selected: panel && panel.interactionSelected
    Rectangle { anchors.fill: parent; color: root.selected ? "#67280916" : root.panel && root.panel.soft ? "#3010060b" : "transparent" }
    Rectangle { width: parent.width; height: 1; color: root.selected ? Theme.primary : "#3b67182c" }
    Rectangle { width: Theme.px(18); height: 3; color: Theme.primary; opacity: root.selected ? 1 : 0.5 }
}
