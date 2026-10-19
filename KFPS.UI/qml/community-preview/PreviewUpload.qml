import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

PreviewDialog {
    id: dialog
    property var ui
    property bool revision: false
    readonly property bool liveMode: typeof communityGalleryMode !== "undefined" && communityGalleryMode
    modal: true
    width: Math.min(760, parent.width - 36)
    height: Math.min(820, parent.height - 36)
    anchors.centerIn: parent
    title: revision ? ui("Upload revision", "수정본 업로드") : ui("Upload artwork", "작품 업로드")
    closePolicy: Popup.CloseOnEscape
    onOpened: {
        starts.setIso(preview.defaultStart); ends.setIso(preview.defaultEnd)
        if (revision) {
            titleField.text = preview.selected.title; description.text = preview.selected.description
            tags.reset((preview.selected.tags || []).join(", "))
            category.currentIndex = Math.max(0, category.model.indexOf(preview.selected.category))
            license.currentIndex = Math.max(0, ["kfps-community-share-v1", "cc-by-4.0", "cc-by-nc-4.0", "cc0-1.0"].indexOf(preview.selected.license))
            classification.currentIndex = preview.selected.classification === "handmade" ? 0 : 1
            supporter.checked = preview.selected.supporter; timed.checked = false
        }
        changeNote.text = ""; rights.checked = false; compatibility.checked = false; authorship.currentIndex = 0
    }
    Connections {
        target: preview
        function onPublished() { dialog.close(); rights.checked = false; titleField.text = ""; description.text = ""; tags.reset(""); timed.checked = false; supporter.checked = false }
    }
    contentItem: ColumnLayout {
        spacing: 10
        ScrollView {
            objectName: "UploadScroll"
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    PreviewButton { objectName: "ChooseUpload"; text: dialog.ui("Choose file", "파일 선택"); iconName: "folder"; enabled: !preview.busy; onClicked: preview.chooseFile() }
                    PreviewText { text: preview.busy ? dialog.ui("Checking file...", "파일 확인 중...") : preview.upload.title || dialog.ui("Vinyl JSON or .kfpslivery", "비닐 JSON 또는 .kfpslivery"); Layout.fillWidth: true }
                }
                Image { visible: !!preview.upload.previewUrl; Layout.fillWidth: true; Layout.preferredHeight: 150; source: preview.upload.previewUrl || ""; fillMode: Image.PreserveAspectFit; sourceSize: Qt.size(600,300) }
                ColumnLayout {
                    visible: preview.upload.kind === "livery"
                    Layout.fillWidth: true
                    PreviewText { text: dialog.ui("Additional photos (optional, up to 3)", "추가 사진 (선택, 최대 3장)") }
                    PreviewText { Layout.fillWidth: true; textSize: 12; color: Theme.muted; text: dialog.ui("The in-game thumbnail stays first. PNG, JPEG or WebP, up to 20 MiB each.", "게임 내 썸네일이 항상 맨 앞에 표시됩니다. PNG, JPEG, WebP 파일, 한 장당 최대 20 MiB.") }
                    RowLayout {
                        Layout.fillWidth: true
                        Repeater {
                            model: preview.upload.photoUrls || []
                            delegate: ColumnLayout {
                                required property int index
                                required property string modelData
                                Layout.fillWidth: true
                                Image { Layout.fillWidth: true; Layout.preferredHeight: 100; source: modelData; fillMode: Image.PreserveAspectFit; sourceSize: Qt.size(350,200) }
                                PreviewButton { objectName: "RemoveUploadPhoto:" + index; text: "X"; minimumWidth: 36; hint: dialog.ui("Remove photo", "사진 삭제"); enabled: !preview.busy; onClicked: preview.removePhoto(index) }
                            }
                        }
                    }
                    PreviewButton { objectName: "ChooseLiveryPhotos"; text: (preview.upload.photoUrls || []).length ? dialog.ui("Replace photos", "사진 다시 선택") : dialog.ui("Choose photos", "사진 선택"); iconName: "folder"; enabled: !preview.busy; onClicked: preview.choosePhotos() }
                }
                PreviewText { visible: !!preview.upload.kind; text: (preview.upload.game || "") + " / " + (preview.upload.kind === "livery" ? dialog.ui("Full livery", "전체 리버리") : (preview.upload.shapes || 0) + dialog.ui(" shapes", "개 도형")); color: Theme.muted }
                PreviewText { text: dialog.ui("Title", "제목") }
                C.KfpsTextField { font.pixelSize: Math.round(Theme.px(14)); renderType: TextInput.CurveRendering; id: titleField; objectName: "UploadTitle"; Layout.fillWidth: true; maximumLength: 80; placeholderText: preview.upload.title || "" }
                PreviewText { text: dialog.ui("Description", "설명") }
                C.KfpsTextArea { font.pixelSize: Math.round(Theme.px(14)); renderType: TextEdit.CurveRendering; id: description; objectName: "UploadDescription"; Layout.fillWidth: true; Layout.preferredHeight: 85; wrapMode: TextEdit.Wrap; placeholderText: dialog.ui("About your artwork", "작품을 소개해 주세요") }
                C.KfpsTextField { id: changeNote; visible: dialog.revision; Layout.fillWidth: true; maximumLength: 240; placeholderText: dialog.ui("What changed in this revision?", "이번 수정본에서 달라진 점을 적어 주세요") }
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout { Layout.fillWidth: true; PreviewText { text: dialog.ui("Category", "분류") } PreviewComboBox { id: category; objectName: "UploadCategory"; Layout.fillWidth: true; model: ["Original Artwork", "Characters", "Logos", "Motorsport", "Patterns", "Gaming", "Abstract", "Humor", "Other"] } }
                    ColumnLayout { Layout.fillWidth: true; PreviewText { text: dialog.ui("License", "라이선스") } PreviewComboBox { id: license; Layout.fillWidth: true; model: ["KFPS Community Share", "CC BY 4.0", "CC BY-NC 4.0", "CC0 1.0"] } }
                }
                PreviewText { text: dialog.ui("Tags", "태그") }
                C.CommunityTagPicker { id: tags; objectName: "PreviewUploadTags"; Layout.fillWidth: true; tagService: preview }
                RowLayout {
                    Layout.fillWidth: true
                    PreviewComboBox { id: classification; objectName: "UploadClassification"; enabled: !dialog.revision; Layout.fillWidth: true; model: [dialog.ui("Handmade", "수작업"), dialog.ui("Toolmade", "도구 제작")] }
                    C.KfpsCheckBox { crispText: true; font.pixelSize: Math.round(Theme.px(12)); id: supporter; text: preview.policyMode === "verified_v1" ? dialog.ui("Verified only", "Verified 전용") : dialog.ui("Supporters only", "서포터 전용"); enabled: preview.restrictedAccess && !dialog.revision }
                }
                ColumnLayout {
                    visible: preview.policyMode === "verified_v1" && preview.upload.kind === "vinyl"
                    Layout.fillWidth: true
                    PreviewText { text: dialog.ui("Authorship", "원작자 확인") }
                    PreviewComboBox {
                        id: authorship; objectName: "UploadAuthorship"; Layout.fillWidth: true
                        model: [dialog.ui("Choose authorship", "원작자 여부 선택"), dialog.ui("I created this original vinyl", "제가 직접 창작한 원본 비닐입니다"), dialog.ui("I have permission to share it", "공유 허가를 받은 작품입니다")]
                    }
                    PreviewText { Layout.fillWidth: true; color: Theme.muted; textSize: 12; text: dialog.ui("Only your own original Handmade vinyls earn lifetime contribution credit after publication. Toolmade uploads are welcome but do not count. Revisions do not add credit.", "직접 창작한 원본 수작업 비닐만 게시 후 누적 기여로 인정됩니다. 도구 제작 작품도 업로드할 수 있지만 기여로 계산되지 않습니다. 수정본은 추가 기여로 계산되지 않습니다.") }
                }
                PreviewText { visible: preview.policyMode === "verified_v1" && preview.upload.kind === "livery"; Layout.fillWidth: true; color: Theme.muted; textSize: 12; text: dialog.ui("Liveries do not earn original-vinyl contribution credit.", "리버리는 원본 비닐 기여로 계산되지 않습니다.") }
                C.KfpsCheckBox { crispText: true; font.pixelSize: Math.round(Theme.px(12)); id: timed; enabled: !dialog.revision; objectName: "TimedUpload"; text: dialog.ui("Scheduled release", "기간 한정 공개") }
                GridLayout {
                    visible: timed.checked; Layout.fillWidth: true; columns: 2; columnSpacing: 12
                    PreviewText { text: dialog.ui("Starts", "공개 시작") }
                    PreviewText { text: dialog.ui("Ends and deletes", "공개 종료 및 삭제") }
                    PreviewDateTime { id: starts; objectName: "UploadStarts"; Layout.fillWidth: true }
                    PreviewDateTime { id: ends; objectName: "UploadEnds"; Layout.fillWidth: true }
                    PreviewText { Layout.columnSpan: 2; Layout.fillWidth: true; textSize: 12; color: Theme.muted; text: dialog.ui("Your local time: ", "현재 현지 시간: ") + preview.clock }
                }
                PreviewText { visible: !!preview.upload.warning; text: preview.upload.warning || ""; color: Theme.warning; Layout.fillWidth: true }
                C.KfpsCheckBox { crispText: true; font.pixelSize: Math.round(Theme.px(12)); id: compatibility; visible: !!preview.upload.warning; text: dialog.ui("I acknowledge the compatibility warning.", "호환성 안내를 확인했습니다.") }
                C.KfpsCheckBox { crispText: true; font.pixelSize: Math.round(Theme.px(12)); id: rights; objectName: "UploadRights"; text: dialog.ui("I made this artwork or have permission to share it.", "직접 만든 작품이거나 공유 허가를 받았습니다.") }
                PreviewText { visible: preview.hasError; text: preview.status; color: Theme.danger; Layout.fillWidth: true }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            PreviewButton { text: dialog.ui("Cancel", "취소"); onClicked: dialog.close() }
            PreviewPrimaryButton {
                objectName: "PublishUpload"; text: dialog.liveMode ? dialog.ui("Upload", "업로드") : dialog.ui("Publish locally", "로컬에 게시")
                enabled: preview.authenticated && preview.policyReady && !!preview.upload.kind && !preview.busy && rights.checked
                    && (preview.policyMode !== "verified_v1" || preview.upload.kind !== "vinyl" || authorship.currentIndex > 0)
                onClicked: { if (!tags.commitPending()) return; preview.publish({title: titleField.text.trim() || preview.upload.title, description: description.text,
                    category: category.currentText, license: license.currentText, tags: tags.text,
                    classification: classification.currentIndex === 0 ? "handmade" : "toolmade",
                    supporter: supporter.checked, timed: timed.checked, starts: starts.isoValue, ends: ends.isoValue,
                    rights: rights.checked, compatibility: compatibility.checked,
                    authorship: authorship.currentIndex === 1 ? "own" : authorship.currentIndex === 2 ? "permission" : "",
                    revision_id: dialog.revision ? preview.selected.id : "", change_note: changeNote.text}) }
            }
        }
    }
}
