import QtQuick 6.7
import Kfps.Theme 1.0
Item {
    property var sidebar: null
    Rectangle { anchors.fill: parent; color: Theme.surfaceStrong }
    Rectangle { anchors.right: parent.right; width: Theme.px(1); height: parent.height; color: Theme.border }
}
