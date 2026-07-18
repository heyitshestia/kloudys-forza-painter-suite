import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    required property string displayName
    required property string path
    required property string previewUrl
    required property string detailText
    property bool selected: false
    property bool validating: false
    signal clicked()

    HoverCard {
        anchors.fill: parent
        padding: Theme.px(7)
        clickable: true
        strong: root.selected
        toolTipText: "Select " + root.displayName + " and validate it for Community upload."
        onClicked: root.clicked()

        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.px(5)

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: Theme.px(72)
                radius: Theme.px(6)
                color: Theme.previewSurface
                border.width: Math.max(1, Theme.px(root.selected ? 2 : 1))
                border.color: root.selected ? Theme.primaryBright : Theme.borderSoft
                clip: true

                Image {
                    id: tilePreview
                    anchors.fill: parent
                    anchors.margins: Theme.px(4)
                    source: root.previewUrl
                    sourceSize.width: Theme.px(300)
                    sourceSize.height: Theme.px(300)
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: true
                    smooth: true
                    mipmap: false
                }

                EmptyState {
                    visible: !root.previewUrl || tilePreview.status === Image.Error
                    anchors.centerIn: parent
                    scale: 0.56
                    iconName: "json"
                    title: root.previewUrl ? "Preview unavailable" : "No preview"
                    message: ""
                }

                BusyIndicator {
                    anchors.centerIn: parent
                    running: root.validating || tilePreview.status === Image.Loading
                    visible: running
                    palette.highlight: Theme.primaryBright
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.displayName
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10.2)
                font.weight: Font.DemiBold
                maximumLineCount: 1
                elide: Text.ElideMiddle
            }

            Text {
                Layout.fillWidth: true
                text: root.validating ? "Validating for upload..." : root.detailText
                color: root.validating ? Theme.warning : Theme.subtle
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(8.9)
                maximumLineCount: 1
                elide: Text.ElideRight
            }
        }
    }
}
