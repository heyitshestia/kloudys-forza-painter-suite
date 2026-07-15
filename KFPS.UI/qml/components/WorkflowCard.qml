import QtQuick 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

HoverCard {
    id: root

    property string number: "1"
    property string title: "Generate"
    property string description: ""
    property string iconName: "generate"
    property string buttonText: "Open"
    property bool compactContent: Theme.logical(width) < 330 || Theme.logical(height) < 162
    signal action()

    clickable: true
    toolTipText: description
    padding: Theme.px(compactContent ? 14 : 18)
    implicitHeight: Theme.px(compactContent ? 154 : 170)
    Layout.minimumHeight: implicitHeight
    onClicked: action()

    RowLayout {
        anchors.fill: parent
        spacing: Theme.px(root.compactContent ? 13 : 18)

        Item {
            Layout.preferredWidth: Theme.px(root.compactContent ? 68 : 86)
            Layout.minimumWidth: Layout.preferredWidth
            Layout.fillHeight: true

            Icon {
                anchors.centerIn: parent
                name: root.iconName
                iconSize: Theme.px(root.compactContent ? 54 : 68)
                glow: true
                glowColor: Theme.primary
                iconOpacity: 0.98
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.px(root.compactContent ? 6 : 8)

            Text {
                Layout.fillWidth: true
                text: (root.number.length ? root.number + ". " : "") + root.title
                color: Theme.primaryBright
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(root.compactContent ? 15.5 : 17)
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
                maximumLineCount: root.compactContent ? 1 : 2
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.description
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.compactContent ? 10.4 : 11.5)
                wrapMode: Text.Wrap
                lineHeight: 1.25
                maximumLineCount: root.compactContent ? 2 : 3
                elide: Text.ElideRight
            }

            GhostButton {
                Layout.alignment: Qt.AlignLeft
                text: root.buttonText
                accentText: true
                showArrow: true
                dense: root.compactContent
                minimumWidth: Theme.px(root.compactContent ? 142 : 156)
                maximumTextWidth: Theme.px(root.compactContent ? 126 : 148)
                toolTipText: root.toolTipText
                onClicked: root.action()
            }
        }
    }
}
