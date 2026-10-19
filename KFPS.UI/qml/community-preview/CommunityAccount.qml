import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

PreviewDialog {
    id: root
    property var ui
    anchors.centerIn: parent
    modal: true
    width: Math.min(Theme.px(620), parent ? parent.width - 40 : Theme.px(620))
    title: ui("Community account", "커뮤니티 계정")
    standardButtons: Dialog.Close
    contentItem: ColumnLayout {
        spacing: Theme.px(12)
        PreviewText { Layout.fillWidth: true; visible: !communityService.authenticated; text: root.ui("Welcome! Sign in with GitHub to upload, download, vote and save your favorites.", "환영합니다! GitHub로 로그인하면 작품을 올리고 다운로드하거나 추천하고 즐겨찾기에 저장할 수 있어요.") }
        PreviewPrimaryButton { objectName: "GitHubSignIn"; visible: !communityService.authenticated; enabled: !communityService.authenticationInProgress; text: root.ui("Sign in with GitHub", "GitHub로 로그인"); onClicked: communityService.connectAccountWith("github") }
        PreviewText { Layout.fillWidth: true; visible: communityService.authenticationInProgress; text: root.ui("Enter this code on GitHub, then approve access. This window will sign in automatically.", "GitHub에 아래 코드를 입력하고 접근을 승인해 주세요. 승인이 끝나면 이 창에서 자동으로 로그인됩니다.") }
        PreviewText { objectName: "GitHubDeviceCode"; visible: communityService.authenticationInProgress; text: communityService.githubUserCode; textSize: Theme.px(26); textWeight: Font.Bold; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
        RowLayout {
            visible: communityService.authenticationInProgress
            PreviewButton { text: root.ui("Copy code", "코드 복사"); onClicked: communityService.copyGithubCode() }
            PreviewButton { text: root.ui("Open GitHub", "GitHub 열기"); onClicked: communityService.openGithubVerification() }
            PreviewButton { text: root.ui("Cancel", "취소"); onClicked: communityService.cancelAuthentication() }
        }
        PreviewText { Layout.fillWidth: true; visible: communityService.usernameRequired; text: root.ui("Choose your Community username carefully. It cannot be changed later.", "커뮤니티에서 사용할 이름을 신중하게 골라 주세요. 나중에는 변경할 수 없어요.") }
        C.KfpsTextField { id: username; visible: communityService.usernameRequired; Layout.fillWidth: true; placeholderText: root.ui("Username", "사용자 이름") }
        C.KfpsTextField { id: confirmation; visible: communityService.usernameRequired; Layout.fillWidth: true; placeholderText: root.ui("Confirm username", "사용자 이름 다시 입력") }
        PreviewPrimaryButton { visible: communityService.usernameRequired; text: root.ui("Save username", "이름 저장"); onClicked: communityService.chooseUsername(username.text, confirmation.text) }
        PreviewText { Layout.fillWidth: true; visible: communityService.authenticated && !communityService.usernameRequired; text: "@" + communityService.username; textWeight: Font.DemiBold }
        CommunityAccess { Layout.fillWidth: true; accessService: preview; ui: root.ui }
        PreviewButton {
            objectName: "VerifyExistingSupporter"
            visible: communityService.existingSupporterVerificationAvailable
            enabled: !communityService.busy
            text: root.ui("Verify my existing supporter key", "기존 서포터 키 확인")
            onClicked: communityService.verifyExistingSupporter()
        }
        RowLayout {
            visible: communityService.authenticated
            PreviewButton { text: root.ui("Refresh access", "이용 권한 새로고침"); onClicked: preview.refreshAccess() }
            PreviewButton { text: root.ui("Sign out", "로그아웃"); onClicked: communityService.signOut() }
        }
        PreviewText { Layout.fillWidth: true; text: communityService.errorMessage || communityService.statusMessage; color: communityService.errorMessage ? Theme.danger : Theme.muted }
    }
}
