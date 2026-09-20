import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

PreviewDialog {
    id: dialog
    property var ui
    property var profile: preview.creatorProfile
    signal editRequested()
    signal imageRequested(string ident)
    anchors.centerIn: parent
    modal: true
    width: Math.min(Theme.px(1100), parent.width - Theme.px(48))
    height: Math.min(Theme.px(850), parent.height - Theme.px(48))
    title: "@" + (profile.creator || "")
    standardButtons: Dialog.Close
    onOpened: gallery.positionViewAtBeginning()
    contentItem: ColumnLayout {
        spacing: Theme.px(12)
        ScrollView {
            id: infoScroll
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(info.implicitHeight, Theme.px(180))
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                id: info
                width: infoScroll.availableWidth
                spacing: Theme.px(10)
                PreviewText { text: dialog.profile.bio || dialog.ui("No bio yet.", "아직 자기소개가 없어요."); Layout.fillWidth: true }
                PreviewButton {
                    visible: !!dialog.profile.website
                    text: dialog.profile.website || ""
                    Layout.fillWidth: true
                    onClicked: Qt.openUrlExternally(dialog.profile.website)
                }
                RowLayout {
                    Layout.fillWidth: true
                    PreviewText { text: (dialog.profile.followers || 0) + dialog.ui(" followers", "명 팔로워"); color: Theme.muted }
                    Item { Layout.fillWidth: true }
                    PreviewButton { objectName: "ProfileFollow"; visible: !dialog.profile.own; enabled: preview.authenticated; text: dialog.profile.followed ? dialog.ui("Following", "팔로잉") : dialog.ui("Follow", "팔로우"); onClicked: preview.followCreator() }
                    PreviewButton { objectName: "ProfileEdit"; visible: !!dialog.profile.own; text: dialog.ui("Edit profile", "프로필 수정"); onClicked: { dialog.close(); dialog.editRequested() } }
                    PreviewButton { objectName: "ProfileBrowse"; text: dialog.ui("View in browser", "목록에서 보기"); onClicked: { preview.browseCreator(""); dialog.close() } }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
        PreviewText { text: dialog.ui("Artworks", "작품") + " (" + (dialog.profile.artworkCount || 0) + ")"; textWeight: Font.DemiBold }
        Item {
            id: galleryFrame
            Layout.fillWidth: true
            Layout.fillHeight: true
            GridView {
                id: gallery
                objectName: "CreatorGallery"
                anchors.fill: parent
                anchors.rightMargin: creatorScroll.width + Theme.px(8)
                clip: true
                readonly property int columns: width >= Theme.px(980) ? 4 : 3
                cellWidth: Math.floor(width / columns)
                cellHeight: Math.round((cellWidth - Theme.px(12)) * 0.64) + Theme.px(58)
                cacheBuffer: cellHeight * 2
                reuseItems: true
                model: preview.creatorModel
                function fetchAhead() {
                    if (visible && preview.creatorHasMore && contentY + height + cellHeight * 3 >= contentHeight)
                        preview.loadMoreCreator()
                }
                onContentYChanged: fetchAhead()
                onCountChanged: Qt.callLater(fetchAhead)
                ScrollBar.vertical: C.KfpsScrollBar {
                    id: creatorScroll
                    parent: galleryFrame
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                }
                delegate: Item {
                    id: tile
                    required property var artwork
                    objectName: "CreatorArtwork:" + artwork.id
                    width: gallery.cellWidth - Theme.px(12)
                    height: gallery.cellHeight - Theme.px(12)
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: artwork.title
                    Keys.onReturnPressed: dialog.imageRequested(artwork.id)
                    Keys.onSpacePressed: dialog.imageRequested(artwork.id)
                    Rectangle {
                        id: picture
                        width: parent.width
                        height: parent.height - Theme.px(48)
                        color: Theme.surface
                        border.color: hit.containsMouse ? Theme.focusColor : Theme.divider
                        C.ArtworkPreviewBackdrop { anchors.fill: parent; anchors.margins: 2; opacity: 0.45 }
                        Image {
                            objectName: "CreatorThumbnail:" + tile.artwork.id
                            anchors.fill: parent
                            anchors.margins: 1
                            source: tile.artwork.previewUrl || ""
                            fillMode: Image.PreserveAspectFit
                            sourceSize: Qt.size(400, 260)
                            asynchronous: false
                            cache: false
                        }
                        PreviewTimedBadge { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 7; artwork: tile.artwork; ui: dialog.ui }
                    }
                    PreviewText {
                        anchors.top: picture.bottom
                        anchors.topMargin: Theme.px(5)
                        width: parent.width
                        text: tile.artwork.title || ""
                        textSize: 15
                        textWeight: Font.DemiBold
                        maximumLineCount: 1
                        elide: Text.ElideRight
                    }
                    PreviewText {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        text: tile.artwork.game || ""
                        textSize: 12
                        color: Theme.muted
                    }
                    MouseArea {
                        id: hit
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: dialog.imageRequested(tile.artwork.id)
                    }
                }
            }
            PreviewText {
                anchors.centerIn: parent
                visible: gallery.count === 0
                text: dialog.ui("No public artworks yet.", "아직 공개된 작품이 없어요.")
                color: Theme.muted
            }
        }
    }
}
