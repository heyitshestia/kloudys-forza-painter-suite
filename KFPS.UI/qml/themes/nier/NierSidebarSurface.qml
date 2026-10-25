import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    property var sidebar: null
    Rectangle { anchors.fill: parent; color: Theme.surfaceSoft }
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.border }
}
