import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property string artworkTitle: "Untitled"
    property string cardCreatorName: "Unknown"
    property string cardPreviewUrl: ""
    property string cardCategory: "Other"
    property string cardClassificationLabel: "Toolmade"
    property string cardGamesText: ""
    property string cardSchemaLabel: "KFPS-compatible JSON"
    property bool cardSchemaKnown: true
    property int cardShapeCount: 0
    property int cardDownloads: 0
    property int cardFavorites: 0
    property bool cardFeatured: false
    property bool cardSupporterOnly: false
    property bool cardSelected: false
    property string cardStatusLabel: "Published"
    signal clicked()
    signal doubleClicked()

    HoverCard {
        anchors.fill: parent
        padding: Theme.px(9)
        clickable: true
        strong: root.cardSelected
        toolTipText: "Click to select. Double-click to open a large preview of " + root.artworkTitle + "."
        onClicked: root.clicked()
        onDoubleClicked: root.doubleClicked()

        RowLayout {
            anchors.fill: parent
            spacing: Theme.px(10)

            Rectangle {
                Layout.preferredWidth: Theme.px(142)
                Layout.fillHeight: true
                Layout.minimumHeight: Theme.px(126)
                radius: Theme.px(6)
                color: Theme.previewSurface
                border.width: Math.max(1, Theme.px(root.cardSelected ? 2 : 1))
                border.color: root.cardSelected ? Theme.primaryBright : Theme.borderSoft
                clip: true

                Image {
                    id: previewImage
                    anchors.fill: parent
                    anchors.margins: Theme.px(4)
                    source: root.cardPreviewUrl
                    sourceSize.width: Theme.px(320)
                    sourceSize.height: Theme.px(320)
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: true
                    smooth: true
                    mipmap: false
                }

                EmptyState {
                    visible: !root.cardPreviewUrl || previewImage.status === Image.Error
                    anchors.centerIn: parent
                    scale: 0.58
                    iconName: "images"
                    title: root.cardPreviewUrl ? "Preview unavailable" : "No preview"
                    message: ""
                }

                BusyIndicator {
                    anchors.centerIn: parent
                    running: previewImage.status === Image.Loading
                    visible: running
                    palette.highlight: Theme.primaryBright
                }

                Rectangle {
                    visible: root.cardFeatured
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: Theme.px(6)
                    width: featuredText.implicitWidth + Theme.px(14)
                    height: Theme.px(22)
                    radius: Theme.px(5)
                    color: Theme.primaryDeep
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.primaryBright

                    Text {
                        id: featuredText
                        anchors.centerIn: parent
                        text: "FEATURED"
                        color: Theme.primaryText
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(8.6)
                        font.weight: Font.Bold
                    }
                }

                Rectangle {
                    visible: root.cardSupporterOnly
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.px(6)
                    width: supporterText.implicitWidth + Theme.px(14)
                    height: Theme.px(22)
                    radius: Theme.px(5)
                    color: Theme.surfaceStrong
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.primaryBright

                    Text {
                        id: supporterText
                        anchors.centerIn: parent
                        text: "SUPPORTERS"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(8.3)
                        font.weight: Font.Bold
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.px(4)

                Text {
                    Layout.fillWidth: true
                    text: root.artworkTitle
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(13.2)
                    font.weight: Font.Bold
                    maximumLineCount: 2
                    wrapMode: Text.Wrap
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: "@" + root.cardCreatorName
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.7)
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.cardClassificationLabel + " | " + root.cardCategory + " | " + root.cardSchemaLabel
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.7)
                    elide: Text.ElideRight
                }

                Text {
                    visible: root.cardGamesText.length > 0 || !root.cardSchemaKnown
                    Layout.fillWidth: true
                    text: root.cardSchemaKnown ? "Detected origin: " + root.cardGamesText : "Compatibility unverified"
                    color: root.cardSchemaKnown ? Theme.subtle : Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.3)
                    font.weight: root.cardSchemaKnown ? Font.Normal : Font.DemiBold
                    elide: Text.ElideRight
                }

                Item { Layout.fillHeight: true }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    Text {
                        Layout.fillWidth: true
                        text: root.cardShapeCount.toLocaleString(Qt.locale(), "f", 0) + " shapes"
                        color: Theme.subtle
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(9.5)
                        elide: Text.ElideRight
                    }

                    Text {
                        text: root.cardDownloads.toLocaleString(Qt.locale(), "f", 0) + " downloads"
                        color: Theme.subtle
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(9.5)
                    }

                    Text {
                        text: root.cardFavorites.toLocaleString(Qt.locale(), "f", 0) + " favorites"
                        color: Theme.subtle
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(9.5)
                    }
                }

                Text {
                    visible: root.cardStatusLabel !== "Published"
                    Layout.fillWidth: true
                    text: root.cardStatusLabel
                    color: root.cardStatusLabel === "Rejected" ? Theme.danger : Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.3)
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
            }
        }
    }
}
