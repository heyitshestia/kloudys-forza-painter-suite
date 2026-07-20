import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

ScrollBar {
    id: root

    hoverEnabled: true
    minimumSize: 0.08
    implicitWidth: orientation === Qt.Vertical ? Theme.px(9) : Theme.px(40)
    implicitHeight: orientation === Qt.Horizontal ? Theme.px(9) : Theme.px(40)
    padding: Theme.px(2)

    contentItem: Rectangle {
        implicitWidth: Theme.px(5)
        implicitHeight: Theme.px(40)
        radius: Theme.corner(Math.min(width, height) / 2)
        color: root.pressed
               ? Theme.primaryHot
               : (root.hovered ? Theme.primaryBright : Theme.primary)
        opacity: root.policy === ScrollBar.AlwaysOff || root.size >= 1.0
                 ? 0
                 : (root.active || root.hovered || root.pressed ? 0.92 : 0.42)

        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 95 } }
        Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 120 } }
    }

    background: Rectangle {
        radius: Theme.corner(Math.min(width, height) / 2)
        color: Theme.fieldSurface
        opacity: root.hovered || root.pressed ? 0.62 : 0.20
        Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
    }
}
