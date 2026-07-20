import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool active: false
    readonly property real stroke: Math.max(1, Theme.px(1))
    readonly property real dash: Math.max(2, Theme.px(2))
    readonly property real stride: dash * 2

    visible: Theme.classicMode && active
    enabled: false
    clip: true

    Repeater {
        model: Math.max(0, Math.ceil(root.width / root.stride))
        Rectangle {
            required property int index
            x: index * root.stride
            y: 0
            width: root.dash
            height: root.stroke
            color: Theme.focusColor
        }
    }
    Repeater {
        model: Math.max(0, Math.ceil(root.width / root.stride))
        Rectangle {
            required property int index
            x: index * root.stride
            y: root.height - root.stroke
            width: root.dash
            height: root.stroke
            color: Theme.focusColor
        }
    }
    Repeater {
        model: Math.max(0, Math.ceil(root.height / root.stride))
        Rectangle {
            required property int index
            x: 0
            y: index * root.stride
            width: root.stroke
            height: root.dash
            color: Theme.focusColor
        }
    }
    Repeater {
        model: Math.max(0, Math.ceil(root.height / root.stride))
        Rectangle {
            required property int index
            x: root.width - root.stroke
            y: index * root.stride
            width: root.stroke
            height: root.dash
            color: Theme.focusColor
        }
    }
}
