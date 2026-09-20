import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

ColumnLayout {
    id: inspector
    property var artwork: preview.selected
    property var ui
    signal inspectImage(int index)
    signal reportRequested()
    signal removalRequested()
    signal creatorRequested(string creator)
    signal tagsRequested()
    signal revisionRequested()
    spacing: Theme.px(8)
    PreviewText { visible: !inspector.artwork.id; text: inspector.ui("No artwork selected", "선택한 작품이 없습니다"); Layout.fillWidth: true }
    ScrollView {
        id: inspectorScroll; objectName: "InspectorScroll"
        visible: !!inspector.artwork.id
        Layout.fillWidth: true; Layout.fillHeight: true
        clip: true
        rightPadding: inspectorBar.width + 8
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: C.KfpsScrollBar {
            id: inspectorBar; objectName: "InspectorScrollBar"
            parent: inspectorScroll
            anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right
        }
        ColumnLayout {
            objectName: "InspectorBody"
            width: inspectorScroll.availableWidth
            spacing: Theme.px(8)
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: Math.min(Theme.px(280), width * 0.72)
                color: Theme.surface; radius: Theme.corner(4); clip: true
                C.ArtworkPreviewBackdrop { anchors.fill: parent; opacity: 0.45 }
                Image { anchors.fill: parent; anchors.margins: 8; fillMode: Image.PreserveAspectFit; source: inspector.artwork.previewUrl || ""; sourceSize: Qt.size(900,700); asynchronous: false }
                MouseArea { objectName: "OpenArtworkImage"; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: inspector.inspectImage(0) }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: (inspector.artwork.photoUrls || []).length > 1
                Repeater {
                    model: inspector.artwork.photoUrls || []
                    delegate: AbstractButton {
                        required property int index
                        required property string modelData
                        objectName: "LiveryPhoto:" + index
                        Layout.fillWidth: true; Layout.preferredHeight: 65
                        Accessible.name: inspector.ui("Livery photo ", "리버리 사진 ") + (index + 1)
                        background: Rectangle { color: Theme.surface; border.color: parent.hovered ? Theme.primaryBright : Theme.divider }
                        contentItem: Image { source: modelData; fillMode: Image.PreserveAspectFit; sourceSize: Qt.size(320,180) }
                        onClicked: inspector.inspectImage(index)
                    }
                }
            }
            PreviewText { text: inspector.artwork.title || ""; textSize: Theme.px(18); textWeight: Font.DemiBold; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                PreviewCreatorLink { objectName: "InspectorCreator"; creator: inspector.artwork.creator || ""; Layout.fillWidth: true; onClicked: inspector.creatorRequested(creator) }
                PreviewButton { text: inspector.artwork.followed ? inspector.ui("Following", "팔로잉") : inspector.ui("Follow", "팔로우"); enabled: preview.authenticated && !inspector.artwork.own; onClicked: preview.toggle("follows") }
            }
            PreviewText { text: inspector.artwork.sample ? inspector.ui("Visual sample", "미리보기 예시") : (inspector.artwork.game || "") + " / " + (inspector.artwork.kind === "livery" ? inspector.ui("Full livery", "전체 리버리") : String(inspector.artwork.shapes || 0) + inspector.ui(" shapes", "개 도형")) + " / " + (inspector.artwork.classification === "handmade" ? inspector.ui("Handmade", "수작업") : inspector.ui("Toolmade", "도구 제작")); textSize: 13; color: Theme.muted; Layout.fillWidth: true }
            PreviewText { visible: !!inspector.artwork.car; text: inspector.ui("Car: ", "차량: ") + (inspector.artwork.car || ""); Layout.fillWidth: true }
            PreviewText { text: inspector.artwork.description || ""; Layout.fillWidth: true; lineHeight: 1.2 }
            Flow {
                Layout.fillWidth: true; spacing: 6
                Repeater {
                    model: inspector.artwork.tags || []
                    delegate: PreviewButton { required property string modelData; text: "#" + modelData; implicitHeight: 34; onClicked: preview.filter("search", modelData) }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
            PreviewText { text: inspector.ui("Availability", "공개 기간"); textWeight: Font.DemiBold }
            PreviewText { text: inspector.artwork.window || inspector.ui("No expiry", "기한 없음"); Layout.fillWidth: true; color: Theme.muted; textSize: 13 }
            PreviewText { visible: inspector.artwork.state !== "available"; text: inspector.ui("Status: ", "상태: ") + (inspector.artwork.state || ""); color: Theme.warning; Layout.fillWidth: true }
            PreviewText { visible: !!inspector.artwork.locked; text: inspector.ui("A verified supporter key is required to download this artwork.", "이 작품을 다운로드하려면 유효한 서포터 키가 필요합니다."); color: Theme.warning; Layout.fillWidth: true }
            PreviewText { text: inspector.ui("License", "라이선스"); textWeight: Font.DemiBold }
            PreviewText { text: inspector.artwork.license || ""; Layout.fillWidth: true; color: Theme.muted; textSize: 13 }
            PreviewText { visible: !!inspector.artwork.warning; text: inspector.artwork.warning || ""; Layout.fillWidth: true; color: Theme.warning }
            PreviewText { visible: !!inspector.artwork.sample; text: inspector.ui("Visual sample only. Upload a JSON or livery package to test real file transfers.", "미리보기용 예시입니다. 실제 파일 전송을 시험하려면 JSON 또는 리버리 패키지를 업로드해 주세요."); Layout.fillWidth: true; color: Theme.warning; textSize: 13 }
            RowLayout {
                Layout.fillWidth: true
                PreviewButton { objectName: "Upvote"; iconName: "arrow-up"; hint: inspector.ui("Upvote", "추천"); selected: inspector.artwork.vote === 1; enabled: preview.authenticated && inspector.artwork.state === "available" && !inspector.artwork.locked; onClicked: preview.vote(1) }
                PreviewText { text: String(inspector.artwork.score || 0); textWeight: Font.Bold; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 42 }
                PreviewButton { objectName: "Downvote"; iconName: "arrow-up"; iconRotation: 180; hint: inspector.ui("Downvote", "비추천"); selected: inspector.artwork.vote === -1; enabled: preview.authenticated && inspector.artwork.state === "available" && !inspector.artwork.locked; onClicked: preview.vote(-1) }
                Item { Layout.fillWidth: true }
                PreviewText { text: (inspector.artwork.downloads || 0) + inspector.ui(" downloads", "회 다운로드"); textSize: 12; color: Theme.muted }
            }
            RowLayout {
                Layout.fillWidth: true
                PreviewButton { iconName: "reports"; text: inspector.ui("Report", "신고"); enabled: preview.authenticated && inspector.artwork.state === "available" && !inspector.artwork.locked; onClicked: inspector.reportRequested() }
                PreviewButton { text: inspector.ui("Ignore creator", "작성자 숨기기"); enabled: preview.authenticated && !inspector.artwork.own; onClicked: preview.toggle("ignored") }
            }
            PreviewButton { objectName: "RemoveOwnUpload"; visible: !!inspector.artwork.own; text: inspector.ui("Remove upload", "업로드 삭제"); enabled: inspector.artwork.state !== "expired" && inspector.artwork.state !== "removed"; onClicked: inspector.removalRequested() }
            RowLayout {
                visible: typeof communityGalleryMode !== "undefined" && communityGalleryMode && !!inspector.artwork.own
                PreviewButton { text: inspector.ui("Edit tags", "태그 수정"); onClicked: inspector.tagsRequested() }
                PreviewButton { text: inspector.ui("Upload revision", "수정본 업로드"); visible: inspector.artwork.kind === "vinyl" && !inspector.artwork.ends; onClicked: inspector.revisionRequested() }
            }

        }
    }
    Item {
        id: actions
        visible: !!inspector.artwork.id
        Layout.fillWidth: true
        implicitHeight: Math.max(downloadAction.implicitHeight, favoriteAction.implicitHeight)
        readonly property real actionWidth: Math.floor((width - Theme.px(8)) / 2)
        PreviewPrimaryButton {
            id: downloadAction
            objectName: "Download"; anchors.left: parent.left; width: actions.actionWidth; height: parent.height
            text: inspector.artwork.locked ? "Ko-Fi" : inspector.ui("Download", "다운로드")
            enabled: !!inspector.artwork.locked || (preview.authenticated && !!inspector.artwork.downloadable && inspector.artwork.state === "available")
            toolTipText: inspector.artwork.locked ? inspector.ui("Support KFPS on Ko-Fi", "Ko-Fi에서 KFPS 후원하기") : text
            onClicked: inspector.artwork.locked ? desktop.openUrl("https://ko-fi.com/s/2d1507698d") : preview.download()
        }
        PreviewButton {
            id: favoriteAction
            objectName: "Favorite"; anchors.right: parent.right; width: actions.actionWidth; height: parent.height
            text: inspector.ui("Favorite", "즐겨찾기"); selected: !!inspector.artwork.favorite
            hint: inspector.artwork.favorite ? inspector.ui("Remove favorite", "즐겨찾기 해제") : text
            enabled: preview.authenticated; onClicked: preview.toggle("favorites")
        }
    }
}
