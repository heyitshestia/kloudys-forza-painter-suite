import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

ScrollBar {
    id: root

    hoverEnabled: true
    minimumSize: 0.08
    implicitWidth: orientation === Qt.Vertical ? Theme.px(Theme.classicMode ? 17 : 9) : Theme.px(40)
    implicitHeight: orientation === Qt.Horizontal ? Theme.px(Theme.classicMode ? 17 : 9) : Theme.px(40)
    padding: Theme.px(Theme.classicMode ? 1 : 2)
    topPadding: Theme.classicMode && orientation === Qt.Vertical ? Theme.px(17) : padding
    bottomPadding: Theme.classicMode && orientation === Qt.Vertical ? Theme.px(17) : padding
    leftPadding: Theme.classicMode && orientation === Qt.Horizontal ? Theme.px(17) : padding
    rightPadding: Theme.classicMode && orientation === Qt.Horizontal ? Theme.px(17) : padding

    contentItem: Rectangle {
        implicitWidth: Theme.px(5)
        implicitHeight: Theme.px(40)
        radius: Theme.corner(Math.min(width, height) / 2)
        color: Theme.classicMode
               ? Theme.surface
               : (root.pressed
               ? Theme.primaryHot
               : (root.hovered ? Theme.primaryBright : Theme.primary))
        opacity: root.policy === ScrollBar.AlwaysOff || root.size >= 1.0
                 ? 0
                 : (Theme.classicMode ? 1.0 : (root.active || root.hovered || root.pressed ? 0.92 : 0.42))

        ClassicBevel {
            anchors.fill: parent
            pressed: root.pressed
        }

        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 95 } }
        Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 120 } }
    }

    background: Rectangle {
        radius: Theme.corner(Math.min(width, height) / 2)
        color: Theme.classicMode ? Theme.surfaceTop : Theme.fieldSurface
        opacity: Theme.classicMode ? 1.0 : (root.hovered || root.pressed ? 0.62 : 0.20)

        ClassicBevel {
            anchors.fill: parent
            sunken: true
            depth: 1
        }

        Rectangle {
            visible: Theme.classicMode && root.orientation === Qt.Vertical
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: Theme.px(17)
            color: Theme.surface

            ClassicBevel { anchors.fill: parent; pressed: upperTap.pressed }
            Text {
                anchors.centerIn: parent
                text: "\u25b2"
                color: Theme.borderStrong
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(7)
            }
            TapHandler {
                id: upperTap
                onTapped: root.position = Math.max(0, root.position - Math.max(0.02, root.size * 0.12))
            }
        }

        Rectangle {
            visible: Theme.classicMode && root.orientation === Qt.Vertical
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Theme.px(17)
            color: Theme.surface

            ClassicBevel { anchors.fill: parent; pressed: lowerTap.pressed }
            Text {
                anchors.centerIn: parent
                text: "\u25bc"
                color: Theme.borderStrong
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(7)
            }
            TapHandler {
                id: lowerTap
                onTapped: root.position = Math.min(1 - root.size, root.position + Math.max(0.02, root.size * 0.12))
            }
        }

        Rectangle {
            visible: Theme.classicMode && root.orientation === Qt.Horizontal
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Theme.px(17)
            color: Theme.surface

            ClassicBevel { anchors.fill: parent; pressed: leftTap.pressed }
            Text {
                anchors.centerIn: parent
                text: "\u25c0"
                color: Theme.borderStrong
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(7)
            }
            TapHandler {
                id: leftTap
                onTapped: root.position = Math.max(0, root.position - Math.max(0.02, root.size * 0.12))
            }
        }

        Rectangle {
            visible: Theme.classicMode && root.orientation === Qt.Horizontal
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Theme.px(17)
            color: Theme.surface

            ClassicBevel { anchors.fill: parent; pressed: rightTap.pressed }
            Text {
                anchors.centerIn: parent
                text: "\u25b6"
                color: Theme.borderStrong
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(7)
            }
            TapHandler {
                id: rightTap
                onTapped: root.position = Math.min(1 - root.size, root.position + Math.max(0.02, root.size * 0.12))
            }
        }
        Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 110 } }
    }
}
