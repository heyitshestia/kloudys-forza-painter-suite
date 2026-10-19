import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C
import "CommunityPolicyText.js" as PolicyText

PreviewDialog {
    id: root
    required property var accessService
    required property var ui
    modal: true
    anchors.centerIn: parent
    width: Math.min(Theme.px(650), parent.width - 36)
    height: Math.min(Theme.px(640), parent.height - 36)
    title: ui("Original Handmade vinyl claims", "원본 수작업 비닐 확인")
    onOpened: assertion.checked = false
    contentItem: ColumnLayout {
        CommunityAccess { Layout.fillWidth: true; accessService: root.accessService; ui: root.ui }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
            ColumnLayout {
                width: parent.width
                spacing: Theme.px(8)
                PreviewText { Layout.fillWidth: true; text: root.ui("Selected uploads: ", "선택한 업로드: ") + root.accessService.claimSelection.length + " / 10" }
                PreviewText {
                    objectName: "ClaimRequestError"
                    Layout.fillWidth: true
                    visible: root.accessService.claimError.length > 0
                    color: Theme.warning
                    text: visible ? PolicyText.claimRequestError(root.accessService.claimError, root.ui) : ""
                }
                Repeater {
                    model: root.accessService.claimEntries
                    delegate: PreviewText { required property var modelData; Layout.fillWidth: true; text: modelData.title; textFormat: Text.PlainText }
                }
                PreviewText {
                    Layout.fillWidth: true; color: Theme.muted; textSize: Theme.px(12)
                    text: root.ui("Earlier sharing permission does not establish authorship. Removed or expired Handmade originals may still qualify; revisions and Toolmade uploads do not earn credit.", "이전 공유 허가는 원작자 확인을 대신하지 않습니다. 삭제되거나 만료된 수작업 원본도 인정될 수 있으며 수정본과 도구 제작 작품은 추가 기여로 계산되지 않습니다.")
                }
                PreviewText { Layout.fillWidth: true; text: root.ui("I created these original Handmade vinyls myself. Permission to share someone else's work does not count.", "이 원본 수작업 비닐들은 제가 직접 창작했습니다. 다른 사람의 작품을 공유할 수 있는 허가만으로는 인정되지 않습니다.") }
                C.KfpsCheckBox {
                    id: assertion; objectName: "ClaimAssertion"; Layout.fillWidth: true
                    enabled: root.accessService.claimsEnabled && !root.accessService.claimsBusy && root.accessService.claimSelection.length > 0
                    text: root.ui("I confirm this original-authorship statement", "위 원작자 확인 내용에 동의합니다")
                }
                Repeater {
                    model: root.accessService.claimResults
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        PreviewText { Layout.fillWidth: true; text: modelData.title; textFormat: Text.PlainText; textWeight: Font.DemiBold }
                        PreviewText {
                            Layout.fillWidth: true
                            color: modelData.outcome === "rejected" ? Theme.warning : Theme.muted
                            text: modelData.outcome === "rejected" ? PolicyText.claimError(modelData.error, root.ui)
                                : PolicyText.contribution(modelData.contribution.state, root.ui)
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            PreviewButton { text: root.ui("Close", "닫기"); onClicked: root.close() }
            PreviewPrimaryButton {
                objectName: "SubmitClaims"
                text: root.accessService.claimsBusy ? root.ui("Submitting...", "제출 중...") : root.ui("Confirm original authorship", "원작자 확인 제출")
                enabled: assertion.checked && root.accessService.claimsEnabled && !root.accessService.claimsBusy && root.accessService.claimSelection.length > 0
                onClicked: { root.accessService.submitClaims(true); assertion.checked = false }
            }
        }
    }
}
