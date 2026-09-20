import QtQuick
import QtQuick.Controls
import Kfps.Theme 1.0
import "../components" as C

Rectangle {
    id: badge
    required property var artwork
    property var ui
    readonly property bool available: artwork.state === "available"
    readonly property string label: available ? ui("Timed release: available now", "기간 한정: 지금 이용 가능")
        : artwork.state === "expired" ? ui("Timed release: ended", "기간 한정: 공개 종료")
        : ui("Timed release: not available yet", "기간 한정: 공개 예정")
    objectName: "TimedBadge:" + (artwork.id || "")
    visible: !!artwork.ends
    width: Theme.px(32)
    height: Theme.px(28)
    radius: Theme.corner(3)
    color: available ? "#087443" : "#b42335"
    border.color: "#ffffff"
    border.width: 1
    z: 2
    Accessible.role: Accessible.StaticText
    Accessible.name: label + (artwork.window ? "\n" + artwork.window : "")
    Image {
        objectName: "TimedClockIcon"
        anchors.centerIn: parent
        width: Theme.px(20); height: Theme.px(20)
        source: assetRoot + "/community-icons/clock.svg"
        sourceSize: Qt.size(width, height)
    }
    HoverHandler { id: hover }
    C.KfpsToolTip {
        visible: hover.hovered
        text: badge.Accessible.name
    }
}
