import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../../components"

AbstractButton {
    id: root
    property string iconName: ""
    property string hint: text
    property bool selected: false
    property bool danger: false
    property bool compact: false
    property bool vertical: false
    readonly property color ink: danger ? Theme.danger : selected ? Theme.primary : Theme.signalSecondary
    implicitHeight: Theme.px(vertical ? 54 : 36)
    implicitWidth: Theme.px(vertical ? 90 : 120)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.38
    Accessible.name: hint
    background: Item {
        Rectangle {
            anchors.fill: parent
            color: root.down ? "#243fe1bf" : root.hovered ? "#1239bfa5" : "transparent"
            border.width: root.activeFocus ? 1 : 0
            border.color: Theme.text
        }
        Rectangle { x: 3; y: parent.height - 4; width: parent.width - 6; height: root.selected ? 2 : 1; color: root.ink; opacity: root.selected ? 1 : root.hovered ? 0.7 : root.vertical ? 0.12 : 0.3 }
        Rectangle { x: 3; y: parent.height - 10; width: 1; height: 6; color: root.ink; opacity: root.selected || root.hovered ? 0.9 : 0.3 }
        Rectangle { x: parent.width - 4; y: parent.height - 10; width: 1; height: 6; color: root.ink; opacity: root.selected || root.hovered ? 0.9 : 0.3 }
    }
    contentItem: Item {
        Icon {
            visible: root.iconName.length > 0
            anchors.horizontalCenter: root.vertical ? parent.horizontalCenter : undefined
            anchors.left: root.vertical ? undefined : parent.left
            anchors.leftMargin: Theme.px(9)
            y: root.vertical ? Theme.px(6) : (parent.height - height) / 2
            iconSize: Theme.px(root.vertical ? 21 : 18)
            name: root.iconName
            tint: root.ink
            glow: false
        }
        ArchiveText {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: root.vertical ? Theme.px(3) : root.iconName ? Theme.px(34) : Theme.px(8)
            anchors.rightMargin: Theme.px(4)
            y: root.vertical ? parent.height - height - Theme.px(6) : (parent.height - height) / 2
            text: root.text
            color: root.ink
            horizontalAlignment: root.vertical || !root.iconName ? Text.AlignHCenter : Text.AlignLeft
            font.pixelSize: Theme.px(root.vertical ? 11 : 12)
            font.capitalization: Font.AllUppercase
        }
    }
    KfpsToolTip { visible: root.hovered; text: root.hint }
}
