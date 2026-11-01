import QtQuick 6.7
import QtQuick.Shapes 6.7
import Kfps.Theme 1.0
Item {
    id: root
    property color ink: Theme.text
    property real spread: 0
    // Original interlocking vector pennants, not a game or manufacturer logo.
    Repeater {
        model: 3
        delegate: Shape {
            required property int index
            width: root.width; height: root.height
            x: (index - 1) * root.spread
            y: -index * root.spread * 0.45
            opacity: 1 - index * 0.23
            ShapePath {
                strokeWidth: 0; fillColor: root.ink
                startX: (0.12 + index * 0.17) * root.width; startY: root.height * 0.13
                PathLine { x: (0.36 + index * 0.17) * root.width; y: root.height * 0.13 }
                PathLine { x: (0.56 + index * 0.17) * root.width; y: root.height * 0.50 }
                PathLine { x: (0.36 + index * 0.17) * root.width; y: root.height * 0.87 }
                PathLine { x: (0.12 + index * 0.17) * root.width; y: root.height * 0.87 }
                PathLine { x: (0.32 + index * 0.17) * root.width; y: root.height * 0.50 }
                PathLine { x: (0.12 + index * 0.17) * root.width; y: root.height * 0.13 }
            }
        }
    }
}
