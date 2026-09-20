import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

PreviewDialog {
    id: dialog
    property var ui
    property int photoIndex: 0
    readonly property var photos: (preview.selected.photoUrls || []).length ? preview.selected.photoUrls : [preview.selected.previewUrl || ""]
    anchors.centerIn: parent
    modal: true
    width: parent.width - 60; height: parent.height - 60
    title: preview.selected.title || ""
    closePolicy: Popup.CloseOnEscape
    onOpened: zoom.value = 1
    contentItem: ColumnLayout {
        RowLayout {
            Layout.fillWidth: true
            PreviewButton { iconName: "chevron-left"; hint: dialog.ui("Previous photo", "이전 사진"); visible: dialog.photos.length > 1; enabled: dialog.photoIndex > 0; onClicked: { dialog.photoIndex--; zoom.value = 1 } }
            PreviewText { visible: dialog.photos.length > 1; text: (dialog.photoIndex + 1) + " / " + dialog.photos.length }
            PreviewButton { iconName: "chevron-right"; hint: dialog.ui("Next photo", "다음 사진"); visible: dialog.photos.length > 1; enabled: dialog.photoIndex < dialog.photos.length - 1; onClicked: { dialog.photoIndex++; zoom.value = 1 } }
            Item { Layout.fillWidth: true }
            PreviewPrimaryButton { objectName: "OpenLiveryRender"; visible: preview.selected.kind === "livery"; text: dialog.ui("3D render", "3D 보기"); enabled: preview.authenticated && !preview.selected.locked && !!preview.selected.downloadable && preview.selected.state === "available"; onClicked: preview.openRender() }
            PreviewButton { objectName: "CloseMedia"; text: "X"; minimumWidth: 36; hint: dialog.ui("Close", "닫기"); onClicked: dialog.close() }
        }
        Flickable {
            id: zoomView
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; contentWidth: width * zoom.value; contentHeight: height * zoom.value
            C.ArtworkPreviewBackdrop { width: zoomView.contentWidth; height: zoomView.contentHeight; opacity: 0.4 }
            Image { width: zoomView.contentWidth; height: zoomView.contentHeight; source: dialog.photos[Math.min(dialog.photoIndex, dialog.photos.length - 1)] || ""; fillMode: Image.PreserveAspectFit }
        }
        Slider { id: zoom; from: 1; to: 4; value: 1; Layout.preferredWidth: 240; Accessible.name: dialog.ui("Image zoom", "이미지 확대") }
    }
}
