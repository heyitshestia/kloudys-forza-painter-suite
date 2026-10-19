import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0

ColumnLayout {
    id: root
    required property var accessService
    required property var ui
    spacing: Theme.px(4)
    function utc(value) { return String(value || "").replace("T", " ").replace(".000Z", " UTC").replace("Z", " UTC") }
    PreviewText {
        objectName: "CommunityAccessStatus"
        Layout.fillWidth: true
        textWeight: Font.DemiBold
        text: !root.accessService.policyReady ? root.ui("Community access needs a refresh or client update", "이용 권한 새로고침 또는 클라이언트 업데이트가 필요합니다")
            : root.accessService.policyMode === "verified_v1"
                ? root.accessService.grandfatheredVerified ? root.ui("Verified / Existing supporter", "Verified / 기존 서포터")
                    : root.accessService.verifiedAccess ? root.ui("Verified access", "Verified 이용 권한") : root.ui("Verified progress", "Verified 진행 상황")
                : root.ui("Legacy server: Supporter access", "기존 서버: 서포터 이용 권한")
    }
    PreviewText {
        Layout.fillWidth: true
        visible: root.accessService.policyReady
        color: Theme.muted
        textSize: Theme.px(12)
        text: root.accessService.policyMode !== "verified_v1"
            ? root.ui("This server still uses Supporter access for restricted artwork. Verified claims are not available here.", "이 서버는 제한 작품에 기존 서포터 권한을 사용합니다. Verified 원작자 확인은 아직 지원하지 않습니다.")
            : root.accessService.grandfatheredVerified
                ? root.ui("Permanent Community access granted to this account after existing-supporter verification. Theme access still requires an active key.", "기존 서포터 확인 후 이 계정에 영구 커뮤니티 권한이 부여되었습니다. 테마 이용에는 계속 유효한 키가 필요합니다.")
            : root.accessService.verifiedReason === "account_suspended"
                ? root.ui("Account suspended. Community access is unavailable.", "계정이 정지되어 커뮤니티를 이용할 수 없습니다.")
            : root.accessService.verifiedReason === "unsupported_identity"
                ? root.ui("This account is not eligible for Verified access.", "이 계정은 Verified 이용 권한 대상이 아닙니다.")
            : root.accessService.verifiedReason === "connection_date_unavailable"
                ? root.ui("The first connection date could not be verified. Staff review is required.", "최초 연결 날짜를 확인할 수 없습니다. 운영진 검토가 필요합니다.")
            : root.accessService.verifiedReason === "unavailable"
                ? root.ui("Sign in and refresh to see your contribution progress.", "로그인 후 새로고침하여 기여 진행 상황을 확인하세요.")
                : root.accessService.verifiedCount + " / " + root.accessService.verifiedRequired + root.ui(" lifetime original Handmade vinyls credited. Toolmade, liveries and permission-only uploads do not count.", "개 원본 수작업 비닐의 누적 기여가 인정되었습니다. 도구 제작, 리버리, 공유 허가만 받은 작품은 제외됩니다.")
    }
    PreviewText {
        objectName: "VerifiedConnectionProgress"
        Layout.fillWidth: true
        visible: root.accessService.policyReady && root.accessService.policyMode === "verified_v1" && !root.accessService.grandfatheredVerified
        color: root.accessService.verifiedReason === "waiting_period" ? Theme.warning : Theme.muted
        textSize: Theme.px(12)
        text: root.ui("Both requirements apply: 10 original Handmade vinyls and 14 days since your first GitHub Community connection.", "두 조건을 모두 충족해야 합니다: 원본 수작업 비닐 10개와 GitHub 커뮤니티 최초 연결 후 14일.")
            + (root.accessService.connectedAt ? "\n" + root.ui("First connection: ", "최초 연결: ") + root.utc(root.accessService.connectedAt) : "")
            + (root.accessService.eligibleAfter ? "\n" + root.ui("14-day requirement from: ", "14일 조건 충족 시점: ") + root.utc(root.accessService.eligibleAfter) : "")
            + (root.accessService.verifiedReason === "waiting_period" ? "\n" + root.ui("The server is still waiting for the connection period. Credits earned now are retained.", "서버 기준으로 연결 대기 기간이 남아 있습니다. 지금 획득한 기여는 유지됩니다.") : "")
    }
    ProgressBar {
        id: progress
        objectName: "VerifiedProgress"
        visible: root.accessService.policyReady && root.accessService.policyMode === "verified_v1" && !root.accessService.grandfatheredVerified && root.accessService.verifiedReason !== "unavailable"
        Layout.fillWidth: true
        implicitHeight: Theme.px(Theme.classicMode ? 6 : (Theme.terminalMode ? 3 : 5))
        padding: 0
        from: 0; to: root.accessService.verifiedRequired; value: Math.min(to, root.accessService.verifiedCount)
        background: Rectangle {
            objectName: "VerifiedProgressTrack"
            radius: Theme.corner(height / 2)
            color: Theme.sliderTrack
        }
        contentItem: Item {
            Rectangle {
                objectName: "VerifiedProgressFill"
                x: progress.mirrored ? parent.width - width : 0
                width: progress.position * parent.width
                height: parent.height
                radius: Theme.corner(height / 2)
                color: Theme.primary
            }
        }
        Accessible.name: root.ui("Original Handmade vinyl contribution progress", "원본 수작업 비닐 기여 진행 상황")
    }
}
