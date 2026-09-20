import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

Item {
    id: root
    objectName: "CommunityPreviewPage"
    anchors.fill: parent
    clip: true
    readonly property bool liveMode: typeof communityGalleryMode !== "undefined" && communityGalleryMode
    readonly property string language: preview.language
    function ui(en, ko) { return root.language === "ko" ? ko : en }
    function openCreator(name) { preview.viewCreator(name); creatorDialog.open() }
    function openArtworkImage() { imageDialog.photoIndex = 0; imageDialog.open() }

        ColumnLayout {
            anchors.fill: parent; spacing: Theme.px(6)
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.px(8)
                PreviewText { text: root.ui("Community", "커뮤니티"); textSize: Theme.px(18); textWeight: Font.DemiBold; Layout.rightMargin: Theme.px(8) }
                C.KfpsTextField { font.pixelSize: Math.round(Theme.px(14)); renderType: TextInput.CurveRendering; id: search; objectName: "CommunitySearch"; dense: true; implicitHeight: Math.round(Theme.px(36)); Layout.fillWidth: true; text: preview.filters.search; placeholderText: root.ui("Search artwork, tags or creators", "작품, 태그, 작성자 검색"); onTextEdited: searchTimer.restart() }
                Timer { id: searchTimer; interval: 180; onTriggered: preview.filter("search", search.text) }
                PreviewPrimaryButton { objectName: "OpenUpload"; dense: true; text: root.ui("Upload artwork", "작품 업로드"); iconName: "arrow-up"; enabled: preview.authenticated; onClicked: { uploadDialog.revision = false; uploadDialog.open() } }
                PreviewButton { objectName: "OwnProfile"; Layout.maximumWidth: Theme.px(170); text: preview.username ? "@" + preview.username : root.ui("Profile", "프로필"); enabled: preview.authenticated; onClicked: root.openCreator(preview.username) }
                PreviewButton { objectName: "CommunityAccount"; visible: root.liveMode; text: communityService.authenticated ? root.ui("Account", "계정") : root.ui("Sign in with GitHub", "GitHub로 로그인"); onClicked: accountDialog.open() }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true; Layout.rightMargin: Theme.px(10); spacing: Theme.px(6)
                    Flow {
                        Layout.fillWidth: true; spacing: Theme.px(4)
                        Repeater {
                            model: [{key:"Featured", label:root.ui("Featured", "추천 작품")}, {key:"Browse",label:root.ui("Browse", "둘러보기")}, {key:"Timed Releases",label:root.ui("Timed Releases", "기간 한정")}, {key:"Livery",label:root.ui("Livery", "리버리")}, {key:"Favorites",label:root.ui("Favorites", "즐겨찾기")}, {key:"Following",label:root.ui("Following", "팔로잉")}]
                            delegate: PreviewButton { required property var modelData; objectName: "Scope:" + modelData.key; text: modelData.label; selected: preview.scope === modelData.key; enabled: ["Featured", "Browse", "Timed Releases", "Livery"].indexOf(modelData.key) >= 0 || preview.authenticated; onClicked: preview.filter("scope", modelData.key) }
                        }
                        PreviewButton { text: root.ui("My uploads", "내 업로드"); selected: preview.scope === "My uploads"; enabled: preview.authenticated; onClicked: preview.filter("scope", "My uploads") }
                        PreviewButton { objectName: "ClearCreator"; visible: !!preview.filters.creator; text: "@" + preview.filters.creator + " [x]"; hint: root.ui("Show all creators", "모든 작성자 보기"); onClicked: preview.filter("creator", "") }
                        PreviewButton { iconName: "refresh"; hint: root.ui("Refresh", "새로고침"); onClicked: preview.refresh() }
                        C.KfpsCheckBox { font.pixelSize: Math.round(Theme.px(12)); dense: true; crispText: true; text: root.ui("Supporters only", "서포터 전용"); checked: preview.filters.supporters; onToggled: preview.filterSupporters(checked) }
                        PreviewText { text: (root.liveMode ? preview.totalCount : preview.rows.length) + root.ui(" artworks", "개 작품"); height: Theme.px(30); verticalAlignment: Text.AlignVCenter; textSize: Theme.px(11); color: Theme.muted }
                    }
                    GridLayout {
                        objectName: "GalleryFilters"
                        Layout.preferredWidth: gallery.columns * gallery.cellWidth - Theme.px(10)
                        Layout.minimumWidth: Layout.preferredWidth
                        Layout.maximumWidth: Layout.preferredWidth
                        columns: gallery.columns; columnSpacing: Theme.px(10); rowSpacing: Theme.px(6)
                        uniformCellWidths: true
                        PreviewComboBox { objectName: "KindFilter"; dense: true; Layout.fillWidth: true; model: [root.ui("All artwork", "모든 작품"), root.ui("Vinyls", "비닐"), root.ui("Liveries", "리버리")]; currentIndex: ["All", "vinyl", "livery"].indexOf(preview.filters.kind); onActivated: preview.filter("kind", ["All", "vinyl", "livery"][currentIndex]) }
                        PreviewComboBox { dense: true; Layout.fillWidth: true; model: [root.ui("All games", "모든 게임"), "FH4", "FH5", "FH6", "FM8"]; currentIndex: ["All", "FH4", "FH5", "FH6", "FM8"].indexOf(preview.filters.game); onActivated: preview.filter("game", currentIndex === 0 ? "All" : currentText) }
                        PreviewComboBox { dense: true; Layout.fillWidth: true; property var keys: ["All", "Characters", "Logos", "Motorsport", "Patterns", "Original Artwork", "Gaming", "Abstract", "Humor", "Other"]; model: [root.ui("All categories", "모든 분류"), root.ui("Characters", "캐릭터"), root.ui("Logos", "로고"), root.ui("Motorsport", "모터스포츠"), root.ui("Patterns", "패턴"), root.ui("Original Artwork", "창작 작품"), root.ui("Gaming", "게임"), root.ui("Abstract", "추상"), root.ui("Humor", "유머"), root.ui("Other", "기타")]; currentIndex: keys.indexOf(preview.filters.category); onActivated: preview.filter("category", keys[currentIndex]) }
                        PreviewComboBox { dense: true; Layout.fillWidth: true; model: [root.ui("Newest", "최신순"), root.ui("Top rated", "평점순"), root.ui("Most downloaded", "다운로드순"), root.ui("Name", "이름순")]; currentIndex: ["Newest", "Top rated", "Most downloaded", "Name"].indexOf(preview.filters.sort); onActivated: preview.filter("sort", ["Newest", "Top rated", "Most downloaded", "Name"][currentIndex]) }
                        PreviewComboBox { Layout.fillWidth: true; dense: true; model: [root.ui("All methods", "모든 제작 방식"), root.ui("Handmade", "수작업"), root.ui("Toolmade", "도구 제작")]; currentIndex: ["All", "handmade", "toolmade"].indexOf(preview.filters.classification); onActivated: preview.filter("classification", ["All", "handmade", "toolmade"][currentIndex]) }
                    }
                    Item {
                        id: galleryFrame
                        Layout.fillWidth: true; Layout.fillHeight: true
                        GridView {
                            id: gallery; objectName: "CommunityGallery"
                            anchors.fill: parent
                            anchors.rightMargin: galleryScroll.width + 8
                            clip: true
                            readonly property int columns: Math.max(1, Math.floor(width / Theme.px(200)))
                            cellWidth: Math.floor(width / columns)
                            cellHeight: Math.round((cellWidth - Theme.px(10)) * 0.62 + Theme.px(88))
                            model: preview.artworkModel
                            cacheBuffer: cellHeight * 2
                            onContentYChanged: if (root.liveMode && contentY + height >= contentHeight - 3 * cellHeight) preview.loadMore()
                            onCountChanged: if (root.liveMode && contentHeight < height * 2) preview.loadMore()
                            ScrollBar.vertical: C.KfpsScrollBar {
                                id: galleryScroll; objectName: "GalleryScrollBar"
                                parent: galleryFrame
                                anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right
                            }
                            delegate: PreviewArtwork {
                                width: gallery.cellWidth - Theme.px(10); height: gallery.cellHeight - Theme.px(12)
                                selected: preview.selected.id === artwork.id
                                ui: root.ui
                                onChosen: preview.select(artwork.id)
                                onImageRequested: { preview.select(artwork.id); root.openArtworkImage() }
                                onCreatorRequested: function(creator) { root.openCreator(creator) }
                            }
                            PreviewText { anchors.centerIn: parent; visible: gallery.count === 0; text: root.ui("No matching artwork", "조건에 맞는 작품이 없습니다"); color: Theme.muted }
                        }
                    }
                }
                Rectangle { Layout.fillHeight: true; width: 1; color: Theme.divider }
                PreviewInspector {
                    Layout.preferredWidth: Theme.px(Theme.logical(root.width) >= 1250 ? 320 : 260); Layout.minimumWidth: Layout.preferredWidth; Layout.maximumWidth: Layout.preferredWidth; Layout.fillHeight: true; Layout.leftMargin: Theme.px(10)
                    ui: root.ui
                    onInspectImage: function(index) { imageDialog.photoIndex = index; imageDialog.open() }
                    onReportRequested: { reason.text = ""; reportDialog.open() }
                    onRemovalRequested: removeDialog.open()
                    onCreatorRequested: function(creator) { root.openCreator(creator) }
                    onTagsRequested: { editTags.reset((preview.selected.tags || []).join(", ")); tagsDialog.open() }
                    onRevisionRequested: { uploadDialog.revision = true; uploadDialog.open() }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.px(6)
                PreviewButton { objectName: "BackToKfps"; text: root.ui("Back", "돌아가기"); onClicked: appController.navigate("create") }
                PreviewText { visible: !root.liveMode; text: root.ui("LOCAL TEST", "로컬 테스트"); color: Theme.warning; textSize: Theme.px(11) }
                PreviewComboBox { visible: !root.liveMode; objectName: "TestAccount"; Layout.preferredWidth: Theme.px(112); model: ["Visitor", "Member", "Supporter", "Creator"]; currentIndex: root.liveMode ? 0 : model.indexOf(preview.account); onActivated: preview.setAccount(currentText) }
                PreviewText { text: preview.status || (root.liveMode ? "" : root.ui("Local test data only", "로컬 테스트 데이터만 사용")); color: preview.hasError ? Theme.danger : Theme.muted; textSize: 12; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                PreviewButton { iconName: "folder"; hint: root.ui("Downloads", "다운로드"); onClicked: preview.openDownloads() }
                PreviewButton { text: preview.language === "ko" ? "English" : "한국어"; onClicked: preview.setLanguage(preview.language === "ko" ? "en" : "ko") }
                PreviewButton { visible: !root.liveMode; objectName: "AdvanceTime"; text: "+1h"; hint: root.ui("Advance test clock one hour", "테스트 시간을 한 시간 앞으로 이동"); onClicked: preview.advanceClock(3600) }
            }
        }
    PreviewUpload { id: uploadDialog; objectName: "UploadDialog"; parent: Overlay.overlay; ui: root.ui }
    CommunityAccount { id: accountDialog; objectName: "CommunityAccountDialog"; parent: Overlay.overlay; ui: root.ui }
    PreviewProfile {
        id: creatorDialog; objectName: "CreatorProfileDialog"; parent: Overlay.overlay; ui: root.ui
        onEditRequested: { bio.text = preview.profile.bio; website.text = preview.profile.website; profileDialog.open() }
        onImageRequested: function(ident) { if (preview.inspectCreatorArtwork(ident)) root.openArtworkImage() }
    }
    PreviewMedia { id: imageDialog; objectName: "MediaDialog"; parent: Overlay.overlay; ui: root.ui }
    PreviewLiveryViewer { id: renderDialog; objectName: "LiveryRenderDialog"; parent: Overlay.overlay; ui: root.ui }
    Connections {
        target: preview
        function onRenderOpened() { imageDialog.close(); renderDialog.open() }
        function onRenderClosed() { renderDialog.close() }
    }
    onVisibleChanged: if (!visible) { imageDialog.close(); renderDialog.close(); preview.closeRender() }
    Component.onDestruction: preview.closeRender()
    PreviewDialog {
        id: reportDialog; parent: Overlay.overlay; anchors.centerIn: parent; modal: true; width: 520
        title: root.ui("Report artwork", "작품 신고"); standardButtons: Dialog.Cancel | Dialog.Ok
        contentItem: C.KfpsTextArea { font.pixelSize: Math.round(Theme.px(14)); renderType: TextEdit.CurveRendering; id: reason; implicitHeight: 160; wrapMode: TextEdit.Wrap; placeholderText: root.ui("Reason and useful details", "신고 사유와 참고할 내용") }
        onAccepted: preview.report(reason.text)
    }
    PreviewDialog {
        id: removeDialog; parent: Overlay.overlay; anchors.centerIn: parent; modal: true; width: 420
        title: root.ui("Remove this upload?", "업로드를 삭제할까요?"); standardButtons: Dialog.Cancel | Dialog.Ok
        contentItem: PreviewText { text: root.liveMode ? root.ui("This removes your artwork from Community. Your original file is unchanged.", "커뮤니티에서 작품이 삭제됩니다. 원본 파일은 변경되지 않습니다.") : root.ui("This removes the local catalog listing. Your original file is unchanged.", "로컬 목록에서 작품이 삭제됩니다. 원본 파일은 변경되지 않습니다."); height: 65 }
        onAccepted: preview.moderate("remove")
    }
    PreviewDialog {
        id: tagsDialog; parent: Overlay.overlay; anchors.centerIn: parent; modal: true; width: 550
        title: root.ui("Edit tags", "태그 수정"); standardButtons: Dialog.Cancel | Dialog.Save
        contentItem: C.CommunityTagPicker { id: editTags; tagService: preview; implicitHeight: 150 }
        onAccepted: if (editTags.commitPending()) preview.updateTags(editTags.text)
    }
    PreviewDialog {
        id: profileDialog; parent: Overlay.overlay; anchors.centerIn: parent; modal: true; width: 550
        title: root.ui("Profile", "프로필"); standardButtons: Dialog.Cancel | Dialog.Save
        contentItem: ColumnLayout {
            PreviewText { text: "@" + preview.username; textSize: 22 }
            C.KfpsTextArea { font.pixelSize: Math.round(Theme.px(14)); renderType: TextEdit.CurveRendering; id: bio; Layout.fillWidth: true; Layout.preferredHeight: 130; wrapMode: TextEdit.Wrap; placeholderText: root.ui("A little about you", "자기소개") }
            C.KfpsTextField { font.pixelSize: Math.round(Theme.px(14)); renderType: TextInput.CurveRendering; id: website; Layout.fillWidth: true; placeholderText: "https://" }
            PreviewText { text: root.ui("Ignored creators", "숨긴 작성자"); visible: preview.ignoredCreators.length > 0 }
            Repeater { model: preview.ignoredCreators; delegate: PreviewButton { required property string modelData; text: root.ui("Unignore @", "숨기기 해제 @") + modelData; onClicked: preview.unignore(modelData) } }
        }
        onAccepted: preview.saveProfile(bio.text, website.text)
    }
}
