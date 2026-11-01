import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var panel: null
    readonly property bool selected: panel && panel.interactionSelected
    Rectangle { anchors.fill: parent; color: root.selected ? "#182fa079" : "transparent" }
    Rectangle {
        x: 0; y: 0; width: parent.width; height: 1
        color: root.selected ? Theme.primary : Theme.signalSecondary
        opacity: root.selected ? 0.9 : root.panel && root.panel.soft ? 0.18 : 0.5
    }
    Rectangle { visible: root.selected; x: 0; y: 0; width: 2; height: parent.height; color: Theme.primary }
}
