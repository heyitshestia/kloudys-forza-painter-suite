import QtQuick 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property string label: "Status"
    property string value: "Ready"
    property string state: "ok"
    property bool dense: false

    implicitHeight: Theme.px(dense ? 31 : 39)
    Layout.minimumHeight: implicitHeight

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(1, Theme.px(1))
        color: Theme.divider
        opacity: 0.75
    }

    RowLayout {
        anchors.fill: parent
        spacing: Theme.px(root.dense ? 6 : 9)

        Text {
            Layout.fillWidth: true
            text: root.label
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 10.2 : 11.5)
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        Text {
            Layout.preferredWidth: Math.min(implicitWidth, root.width * 0.48)
            Layout.maximumWidth: root.width * 0.48
            text: root.value
            color: root.state === "bad" ? Theme.danger : (root.state === "warn" ? Theme.warning : Theme.success)
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 9.8 : 11)
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        Rectangle {
            Layout.preferredWidth: Theme.px(root.dense ? 15 : 17)
            Layout.preferredHeight: Theme.px(root.dense ? 15 : 17)
            Layout.minimumWidth: Layout.preferredWidth
            Layout.minimumHeight: Layout.preferredHeight
            Layout.alignment: Qt.AlignVCenter
            radius: Theme.corner(width / 2)
            color: "transparent"
            border.width: Math.max(1, Theme.px(1))
            border.color: root.state === "bad" ? Theme.danger : (root.state === "warn" ? Theme.warning : Theme.success)

            Text {
                anchors.centerIn: parent
                text: root.state === "bad" ? "!" : "✓"
                color: parent.border.color
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.dense ? 8.7 : 10)
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
