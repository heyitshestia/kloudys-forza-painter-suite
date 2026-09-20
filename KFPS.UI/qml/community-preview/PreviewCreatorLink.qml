import QtQuick
import QtQuick.Controls
import Kfps.Theme 1.0

AbstractButton {
    id: control
    property string creator: ""
    objectName: "CreatorLink:" + creator
    text: "@" + creator
    implicitWidth: contentItem.implicitWidth
    implicitHeight: Math.max(Theme.px(24), contentItem.implicitHeight)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.Link
    Accessible.name: text
    contentItem: PreviewText {
        text: control.text
        color: Theme.primaryBright
        underlineText: control.hovered || control.activeFocus
        textSize: Math.round(Theme.px(14))
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        maximumLineCount: 1
        wrapMode: Text.NoWrap
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
}
