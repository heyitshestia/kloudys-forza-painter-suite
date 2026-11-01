import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../../components"

Button {
    id: root
    property string iconName: ""
    property string hint: text
    property string subtitle: ""
    property string slotNumber: ""
    property url thumbnail: ""
    property bool selected: false
    property bool checkedState: selected
    property bool primary: false
    property bool compact: false
    property bool displayText: false
    property bool menuEntry: false
    property bool minimal: false
    property bool alignRight: false
    implicitHeight: Theme.px(menuEntry ? 80 : compact ? 30 : 38)
    implicitWidth: Math.max(Theme.px(iconName && !text ? 34 : 80), contentItem.implicitWidth + Theme.px(24))
    leftPadding: Theme.px(menuEntry ? 14 : 10); rightPadding: Theme.px(menuEntry ? 16 : 10)
    topPadding: 0; bottomPadding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: hint || text
    opacity: enabled ? 1 : 0.35
    background: RedlineControlSurface { control: root; controlKind: root.primary || root.selected ? "primary" : "ghost" }
    contentItem: RowLayout {
        spacing: Theme.px(8)
        Icon { visible: root.iconName.length > 0; name: root.iconName; iconSize: Theme.px(15); tint: root.selected || root.primary ? Theme.primaryText : Theme.primary; Layout.alignment: Qt.AlignVCenter }
        Image {
            visible: String(root.thumbnail).length > 0
            Layout.preferredWidth: Theme.px(34); Layout.preferredHeight: Theme.px(44)
            source: root.thumbnail; asynchronous: true; fillMode: Image.PreserveAspectFit; mipmap: true
            sourceSize: Qt.size(Theme.px(68), Theme.px(88))
        }
        Item { visible: root.alignRight; Layout.fillWidth: visible }
        ColumnLayout {
            Layout.fillWidth: !root.alignRight
            spacing: Theme.px(5)
            Text {
                objectName: "RedlineButtonLabel"
                Layout.fillWidth: true
                text: root.text
                color: root.selected || root.primary ? Theme.primaryText : root.menuEntry || root.minimal ? Theme.primary : Theme.text
                font.family: root.displayText ? Theme.displayFamily : Theme.fontFamily
                font.weight: root.displayText ? Font.Bold : Font.DemiBold
                font.pixelSize: Theme.px(root.displayText ? 13 : 14)
                fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(11)
                font.letterSpacing: 0
                horizontalAlignment: root.menuEntry ? Text.AlignLeft : root.alignRight ? Text.AlignRight : Text.AlignHCenter
                elide: Text.ElideRight
            }
            Text {
                visible: root.subtitle.length > 0
                Layout.fillWidth: true
                text: root.subtitle
                color: root.selected || root.primary ? Theme.primaryText : Theme.subtle
                font.family: Theme.fontFamily; font.pixelSize: Theme.px(11); font.letterSpacing: 0
                elide: Text.ElideRight
            }
        }
        Text {
            visible: root.slotNumber.length > 0
            text: root.slotNumber; color: root.selected ? Theme.primaryText : Theme.primary
            font.family: Theme.monoFamily; font.pixelSize: Theme.px(11)
            Layout.alignment: Qt.AlignTop; Layout.topMargin: Theme.px(10)
        }
    }
    KfpsToolTip {
        visible: root.hovered && root.hint.length > 0
        text: root.hint
        delay: 650
    }
}
