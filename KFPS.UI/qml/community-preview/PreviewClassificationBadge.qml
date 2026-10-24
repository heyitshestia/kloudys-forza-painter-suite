import QtQuick
import Kfps.Theme 1.0

Rectangle {
    id: badge
    required property var artwork
    property var ui
    readonly property bool handmade: artwork.classification === "handmade"
    readonly property string label: handmade ? ui("Handmade", "수작업") : ui("Toolmade", "도구 제작")
    objectName: "ClassificationBadge:" + (artwork.id || "")
    visible: handmade || artwork.classification === "toolmade"
    width: Math.min(labelText.implicitWidth + Theme.px(14), Math.max(0, parent.width - Theme.px(16)))
    height: labelText.implicitHeight + Theme.px(6)
    radius: Theme.corner(3)
    color: Theme.surfaceStrong
    border.color: handmade ? Theme.classificationHandmade : Theme.classificationToolmade
    border.width: 1
    Accessible.role: Accessible.StaticText
    Accessible.name: label
    PreviewText {
        id: labelText
        anchors.centerIn: parent
        width: Math.max(0, parent.width - Theme.px(14))
        text: badge.label
        textSize: 12
        textWeight: Font.DemiBold
        color: badge.border.color
        maximumLineCount: 1
        elide: Text.ElideRight
    }
}
