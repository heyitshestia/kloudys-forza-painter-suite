import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

Item {
    id: tile
    required property var artwork
    property bool selected: false
    property var ui
    signal chosen()
    signal imageRequested()
    signal creatorRequested(string creator)
    MouseArea { objectName: "ArtworkHit:" + tile.artwork.id; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: tile.chosen(); onDoubleClicked: tile.imageRequested() }
    Rectangle {
        id: picture
        width: parent.width
        height: parent.height - Theme.px(76)
        color: Theme.surface
        radius: Theme.corner(6)
        border.color: tile.selected ? Theme.primaryBright : Theme.borderSoft
        border.width: tile.selected ? 2 : 1
        clip: true
        C.ArtworkPreviewBackdrop { anchors.fill: parent; anchors.margins: 3; opacity: 0.45 }
        Image { anchors.fill: parent; anchors.margins: 7; source: tile.artwork.previewUrl || ""; fillMode: Image.PreserveAspectFit; sourceSize: Qt.size(560, 400); asynchronous: false }
        C.ClassicBevel { anchors.fill: parent; sunken: true; depth: 1 }
        Rectangle {
            visible: tile.artwork.supporter || tile.artwork.state !== "available" || tile.artwork.kind === "livery"
            anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 9
            width: badge.implicitWidth + 14; height: 23; radius: Theme.corner(3); color: Theme.surfaceStrong
            PreviewText { id: badge; anchors.centerIn: parent; textSize: 12; color: tile.artwork.supporter ? Theme.warning : Theme.text; text: tile.artwork.state !== "available" ? tile.artwork.state : [tile.artwork.supporter ? tile.ui("Supporter", "서포터") : "", tile.artwork.kind === "livery" ? tile.ui("Livery", "리버리") : ""].filter(Boolean).join(" / ") }
        }
        PreviewTimedBadge { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 9; artwork: tile.artwork; ui: tile.ui }
    }
    ColumnLayout {
        anchors.top: picture.bottom; anchors.topMargin: Theme.px(5); width: parent.width; spacing: Theme.px(2)
        PreviewText { text: tile.artwork.title; textWeight: Font.DemiBold; textSize: 15; Layout.fillWidth: true; maximumLineCount: 1; elide: Text.ElideRight }
        PreviewCreatorLink { creator: tile.artwork.creator; Layout.fillWidth: true; onClicked: tile.creatorRequested(creator) }
        RowLayout {
            Layout.fillWidth: true
            PreviewText { text: tile.artwork.sample ? tile.ui("Visual sample", "미리보기 예시") : tile.artwork.kind === "livery" ? tile.artwork.game + " / " + tile.artwork.car : tile.artwork.game + " / " + tile.artwork.shapes + tile.ui(" shapes", "개 도형"); textSize: 12; color: Theme.muted; Layout.fillWidth: true; maximumLineCount: 1; elide: Text.ElideRight }
            C.Icon { name: "arrow-up"; iconSize: 12; colorize: false; tint: tile.artwork.vote ? Theme.primaryBright : Theme.muted }
            PreviewText { text: tile.artwork.score; textSize: 13; color: Theme.muted }
            C.Icon { visible: tile.artwork.favorite; name: "heart"; iconSize: 13; colorize: false; tint: Theme.primaryBright }
        }
    }
    Keys.onReturnPressed: chosen()
    Keys.onSpacePressed: chosen()
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: artwork.title
}
