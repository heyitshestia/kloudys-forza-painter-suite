import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    objectName: "QuickActionRow:" + root.title

    property string iconName: "images"
    property string title: "Action"
    property string subtitle: ""
    property string toolTipText: ""
    property bool dense: false
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : title
    readonly property bool hovered: hover.hovered
    readonly property bool pressed: tap.pressed
    signal clicked

    implicitHeight: Theme.px(dense ? 35 : 48)
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
        color: hover.hovered ? Theme.rowHover : "transparent"
        Behavior on color { ColorAnimation { duration: 110 } }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(1, Theme.px(1))
        color: Theme.divider
        opacity: 0.56
    }

    ClassicBevel {
        anchors.fill: parent
        visible: Theme.classicMode && (root.hovered || root.pressed)
        pressed: root.pressed
    }

    Icon {
        name: root.iconName
        iconSize: Theme.px(root.dense ? 17 : 21)
        iconOpacity: hover.hovered ? 1 : 0.82
        glow: hover.hovered
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(3)
        anchors.verticalCenter: parent.verticalCenter
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(root.dense ? 29 : 36)
        anchors.right: arrow.left
        anchors.rightMargin: Theme.px(root.dense ? 6 : 9)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(1)

        Text {
            width: parent.width
            text: root.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 10.1 : 11.5)
            font.weight: Font.Medium
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            visible: !root.dense || root.subtitle.length > 0
            text: root.subtitle
            color: Theme.subtle
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.dense ? 8.1 : 9.5)
            elide: Text.ElideRight
        }
    }

    Icon {
        id: arrow
        name: "chevron-right"
        iconSize: Theme.px(root.dense ? 12 : 15)
        colorize: true
        tint: hover.hovered ? Theme.primaryBright : Theme.muted
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(4)
        anchors.verticalCenter: parent.verticalCenter
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; onTapped: root.clicked() }
}
