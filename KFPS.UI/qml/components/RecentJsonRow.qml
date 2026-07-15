import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property string fileName: ""
    property string folder: ""
    property string age: ""
    property string toolTipText: ""
    property bool dense: false
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : "Select " + fileName
    signal clicked

    implicitHeight: Theme.px(dense ? 38 : 49)
    Layout.minimumHeight: implicitHeight

    KfpsToolTip {
        visible: hover.hovered && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.px(7)
        color: hover.hovered ? Theme.rowHover : "transparent"
        Behavior on color { ColorAnimation { duration: 110 } }
    }

    Icon {
        name: "json"
        iconSize: Theme.px(root.dense ? 18 : 23)
        iconOpacity: hover.hovered ? 1 : 0.9
        glow: hover.hovered
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(3)
        anchors.verticalCenter: parent.verticalCenter
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(root.dense ? 29 : 38)
        anchors.right: ageText.left
        anchors.rightMargin: Theme.px(8)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(root.dense ? 1 : 2)

        Text {
            width: parent.width
            text: root.fileName
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 10.1 : 11.5)
            elide: Text.ElideMiddle
        }

        Text {
            width: parent.width
            text: root.folder
            color: Theme.subtle
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 8.4 : 9.3)
            elide: Text.ElideMiddle
        }
    }

    Text {
        id: ageText
        width: Math.min(implicitWidth, parent.width * 0.25)
        text: root.age
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(root.dense ? 8.5 : 9.5)
        horizontalAlignment: Text.AlignRight
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(4)
        anchors.verticalCenter: parent.verticalCenter
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.clicked() }
}
