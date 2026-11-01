import QtQuick 6.7
import QtQuick.Window 6.7
import QtQuick.Shapes 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "ApexBackdrop"
    readonly property bool applicationActive: Window.window ? Window.window.active && Window.window.visibility !== Window.Minimized : false
    readonly property bool menuVisible: Window.window ? Window.window.dashboardNavigationVisible : false
    readonly property bool motionAllowed: visible && menuVisible && applicationActive && Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
    property real drift: 0
    clip: true
    Rectangle { anchors.fill: parent; color: Theme.backgroundA }

    // Static tessellation moved by scene-graph transforms; no repaint loop or blur.
    Item {
        id: sculpture
        x: root.width * 0.64
        y: root.height * 0.06
        width: root.width * 0.50
        height: root.height * 0.88
        rotation: -16 + root.drift * 1.5
        transform: Translate { x: root.drift * Theme.px(12); y: root.drift * Theme.px(10) }
        Repeater {
            model: 9
            delegate: Shape {
                id: fin
                required property int index
                x: index * sculpture.width * 0.038
                y: index * sculpture.height * 0.027
                width: sculpture.width * (0.91 - index * 0.038)
                height: sculpture.height * (0.90 - index * 0.036)
                rotation: index * 5 + root.drift * (index % 3 - 1) * 1.4
                ShapePath {
                    strokeWidth: Theme.px(0.8)
                    strokeColor: Theme.withAlpha(Theme.border, 0.8)
                    fillColor: Qt.rgba(0.88 + fin.index * 0.009, 0.90 + fin.index * 0.007, 0.92 + fin.index * 0.005, 0.80)
                    startX: 0; startY: fin.height * 0.34
                    PathLine { x: fin.width * 0.32; y: 0 }
                    PathLine { x: fin.width * 0.97; y: fin.height * 0.24 }
                    PathLine { x: fin.width * 0.84; y: fin.height * 0.45 }
                    PathLine { x: fin.width * 0.35; y: fin.height * 0.22 }
                    PathLine { x: fin.width * 0.15; y: fin.height * 0.47 }
                    PathLine { x: fin.width * 0.29; y: fin.height * 0.90 }
                    PathLine { x: fin.width * 0.07; y: fin.height }
                    PathLine { x: 0; y: fin.height * 0.34 }
                }
            }
        }
    }
    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "drift"; to: 1; duration: 11000; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "drift"; to: -1; duration: 13000; easing.type: Easing.InOutSine }
    }
}
