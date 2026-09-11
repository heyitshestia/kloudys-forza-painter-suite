import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var panel: null
    readonly property bool selected: panel ? panel.interactionSelected : false
    readonly property bool hovered: panel ? panel.interactionHovered : false
    readonly property bool structural: width >= Theme.px(300) && height >= Theme.px(250)
    readonly property real unit: Theme.px(100) / 100 * 0.12
    Rectangle {
        anchors.fill: parent
        radius: 3
        border.width: 1
        border.color: root.selected ? Theme.signalPrimary : (root.hovered ? "#93a5b9" : "#657482")
        gradient: Gradient {
            GradientStop { position: 0; color: "#28333f" }
            GradientStop { position: 0.18; color: "#1c2631" }
            GradientStop { position: 1; color: "#131c27" }
        }
    }
    BorderImage {
        visible: root.structural
        width: root.width / root.unit
        height: root.height / root.unit
        scale: root.unit
        transformOrigin: Item.TopLeft
        source: assetRoot + "/themes/rx93-psycho-frame/parts/inset-panel.png"
        border { left: 70; right: 70; top: 70; bottom: 70 }
        smooth: true
    }
    Rectangle {
        visible: !root.structural
        anchors.fill: parent
        anchors.margins: 2
        radius: 1
        color: "transparent"
        border.width: 1
        border.color: "#121921"
    }
    Rectangle {
        visible: root.selected
        x: 2; y: 12; width: 2; height: Math.max(0, parent.height - 24)
        color: Theme.signalPrimary
    }
}
