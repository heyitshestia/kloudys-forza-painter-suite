import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

AbstractButton {
    id: root
    property bool selected: false
    property int textSize: 28
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: label.implicitWidth + 24
    implicitHeight: 48
    Accessible.name: text
    background: Rectangle {
        color: "transparent"
        radius: 2
        border.width: root.visualFocus ? 1 : 0
        border.color: Theme.withAlpha(Theme.focusColor, 0.5)
    }
    contentItem: Text {
        id: label
        text: root.text
        leftPadding: 12
        rightPadding: 12
        verticalAlignment: Text.AlignVCenter
        color: root.selected || root.hovered ? Theme.primary : Theme.text
        style: Text.Raised
        styleColor: root.selected ? Theme.primaryDeep : Theme.shadow
        font.family: Theme.displayFamily
        font.pixelSize: root.textSize
        elide: Text.ElideRight
        Behavior on color { enabled: !Theme.reducedMotion && !screenshotMode; ColorAnimation { duration: 140 } }
    }
}
