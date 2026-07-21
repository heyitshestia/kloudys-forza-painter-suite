import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    objectName: "RecentJsonRow:" + root.fileName

    property string fileName: ""
    property string folder: ""
    property string age: ""
    property string toolTipText: ""
    property bool dense: false
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : "Select " + fileName
    readonly property bool hovered: hover.hovered
    readonly property bool pressed: tap.pressed
    signal clicked

    implicitHeight: Theme.px(dense ? 38 : 49)
    Layout.minimumHeight: implicitHeight
    scale: Theme.classicMode ? 1.0 : (tap.pressed ? 0.992 : 1.0)
    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 75; easing.type: Easing.OutCubic } }

    KfpsToolTip {
        visible: hover.hovered && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.framedRadius(Theme.px(7))
        color: Theme.angularControlsEnabled ? "transparent" : (hover.hovered ? Theme.rowHover : "transparent")
        Behavior on color { ColorAnimation { duration: 110 } }
    }

    AngularControlFrame {
        anchors.fill: parent
        visible: Theme.angularControlsEnabled && (hover.hovered || tap.pressed)
        fillColor: Theme.rowHover
        borderColor: hover.hovered ? Theme.primary : Theme.borderSoft
        accentColor: Theme.signalSecondary
        hovered: hover.hovered
        pressed: tap.pressed
    }

    ClassicBevel {
        anchors.fill: parent
        visible: Theme.classicMode && (root.hovered || root.pressed)
        pressed: root.pressed
    }

    Icon {
        name: "json"
        iconSize: Theme.px(root.dense ? 18 : 23)
        iconOpacity: hover.hovered ? 1 : 0.9
        glow: hover.hovered
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(3)
        anchors.verticalCenter: parent.verticalCenter
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(root.dense ? 29 : 38)
        anchors.right: ageText.left
        anchors.rightMargin: Theme.px(8)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(root.dense ? 1 : 2)

        Text {
            width: parent.width
            text: root.fileName
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 10.1 : 11.5)
            elide: Text.ElideMiddle
        }

        Text {
            width: parent.width
            text: root.folder
            color: Theme.subtle
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 8.4 : 9.3)
            elide: Text.ElideMiddle
        }
    }

    Text {
        id: ageText
        width: Math.min(implicitWidth, parent.width * 0.25)
        text: root.age
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(root.dense ? 8.5 : 9.5)
        horizontalAlignment: Text.AlignRight
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(4)
        anchors.verticalCenter: parent.verticalCenter
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; onTapped: root.clicked() }
}
