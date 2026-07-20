import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool activeState: false
    property bool hoveredState: false
    property bool warningState: false
    readonly property real phase: activeState ? 3.0 : (hoveredState ? 2.0 : 0.0)

    visible: Theme.equipmentAccentsEnabled
    implicitWidth: Theme.px(20)
    implicitHeight: Theme.px(3)

    Row {
        anchors.fill: parent
        spacing: Theme.px(2)

        Repeater {
            model: 3

            Rectangle {
                required property int index
                width: Theme.px(index === 2 ? 8 : 4)
                height: Theme.px(2)
                radius: height / 2
                color: root.warningState && index === 2
                       ? Theme.signalSecondary
                       : Theme.signalPrimary
                opacity: root.phase > index ? 0.84 : 0.10

                Behavior on opacity {
                    enabled: !Theme.reducedMotion
                    NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                }
            }
        }
    }
}
