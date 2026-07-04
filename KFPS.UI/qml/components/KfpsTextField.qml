import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

TextField {
    id: root

    objectName: "KfpsTextField:" + root.placeholderText

    property bool dense: false
    property real minimumWidth: Theme.px(80)

    implicitHeight: Math.max(
                        Theme.px(dense ? Metrics.denseButtonHeight : Metrics.fieldHeight),
                        font.pixelSize * 1.35 + topPadding + bottomPadding)
    implicitWidth: Theme.px(150)
    Layout.minimumWidth: root.minimumWidth
    Layout.minimumHeight: root.implicitHeight

    leftPadding: Theme.px(dense ? 10 : 12)
    rightPadding: Theme.px(dense ? 10 : 12)
    topPadding: Theme.px(dense ? 5 : 7)
    bottomPadding: Theme.px(dense ? 5 : 7)
    color: Theme.text
    selectionColor: Theme.primary
    selectedTextColor: Theme.primaryText
    placeholderTextColor: Theme.subtle
    font.family: Theme.fontFamily
    font.pixelSize: Theme.px(dense ? 10.5 : 11.5)
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    clip: true

    background: Rectangle {
        radius: Theme.px(Metrics.controlRadius)
        color: root.activeFocus ? Theme.fieldFocusSurface : (root.hovered ? Theme.fieldHoverSurface : Theme.fieldSurface)
        border.width: root.activeFocus ? Theme.px(2) : Theme.px(1)
        border.color: root.activeFocus ? Theme.focusColor : (root.hovered ? Theme.primary : Theme.borderSoft)
        opacity: root.enabled ? 1.0 : 0.62
        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }
}
