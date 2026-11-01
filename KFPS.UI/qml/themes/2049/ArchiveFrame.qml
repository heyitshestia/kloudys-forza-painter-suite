import QtQuick 6.7
import QtQuick.Shapes 6.7
import Kfps.Theme 1.0

Shape {
    id: root
    property color fill: "transparent"
    property color stroke: Theme.border
    property real lineWidth: 1
    property real turn: Math.min(Theme.px(12), width / 4, height / 3)
    enabled: false
    ShapePath {
        strokeColor: root.stroke
        strokeWidth: root.lineWidth
        fillColor: root.fill
        joinStyle: ShapePath.MiterJoin
        startX: 0.5; startY: 0.5
        PathLine { x: root.width - 0.5; y: 0.5 }
        PathLine { x: root.width - 0.5; y: root.height - root.turn - 0.5 }
        PathQuad { x: root.width - root.turn - 0.5; y: root.height - 0.5; controlX: root.width - 0.5; controlY: root.height - 0.5 }
        PathLine { x: 0.5; y: root.height - 0.5 }
        PathLine { x: 0.5; y: 0.5 }
    }
}
