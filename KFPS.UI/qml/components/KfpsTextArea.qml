import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

TextArea {
    id: root

    objectName: "KfpsTextArea:" + root.placeholderText

    property real minimumHeight: Theme.px(80)

    implicitHeight: Theme.px(120)
    implicitWidth: Theme.px(240)
    Layout.minimumWidth: Theme.px(120)
    Layout.minimumHeight: root.minimumHeight

    leftPadding: Theme.px(12)
    rightPadding: Theme.px(12)
    topPadding: Theme.px(10)
    bottomPadding: Theme.px(10)
    color: Theme.text
    selectionColor: Theme.primary
    selectedTextColor: Theme.primaryText
    placeholderTextColor: Theme.subtle
    font.family: Theme.fontFamily
    font.pixelSize: Theme.px(11.5)
    wrapMode: TextEdit.Wrap
    selectByMouse: true

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
