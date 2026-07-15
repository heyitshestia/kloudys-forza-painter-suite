import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

CheckBox {
    id: root

    objectName: "KfpsCheckBox:" + root.text

    property bool dense: false
    property string toolTipText: ""
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : text

    spacing: Theme.px(9)
    leftPadding: 0
    rightPadding: 0
    topPadding: Theme.px(2)
    bottomPadding: Theme.px(2)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    implicitHeight: Math.max(
                        Theme.px(dense ? 25 : 28),
                        Math.max(indicatorItem.implicitHeight, labelText.implicitHeight) + topPadding + bottomPadding)
    implicitWidth: indicatorItem.implicitWidth + spacing + labelText.implicitWidth
    Layout.minimumHeight: root.implicitHeight

    indicator: Rectangle {
        id: indicatorItem
        implicitWidth: Theme.px(dense ? 16 : 18)
        implicitHeight: implicitWidth
        x: root.leftPadding
        y: Math.round((root.height - height) / 2)
        radius: Theme.px(5)
        color: root.checked ? Theme.checkboxCheckedSurface : (root.hovered ? Theme.checkboxHoverSurface : Theme.checkboxSurface)
        border.width: root.activeFocus ? Theme.px(2) : Theme.px(1)
        border.color: root.activeFocus ? Theme.focusColor
                                       : (root.checked ? Theme.primaryBright
                                                       : (root.hovered ? Theme.primary : Theme.borderSoft))

        Text {
            anchors.centerIn: parent
            text: "✓"
            visible: root.checked
            color: Theme.primaryText
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(dense ? 10 : 12)
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    contentItem: Text {
        id: labelText
        leftPadding: indicatorItem.implicitWidth + root.spacing
        rightPadding: 0
        text: root.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(dense ? 10.5 : 11.5)
        color: root.enabled ? Theme.text : Theme.subtle
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }

    KfpsToolTip {
        visible: root.hovered && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }
}
