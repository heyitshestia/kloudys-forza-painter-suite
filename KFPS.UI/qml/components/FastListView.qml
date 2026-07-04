import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

ListView {
    id: root

    property real wheelMultiplier: 1.0
    property bool directWheel: true

    boundsBehavior: Flickable.StopAtBounds
    maximumFlickVelocity: 100000
    flickDeceleration: 12000

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }

    WheelHandler {
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        target: null
        onWheel: event => {
            if (!root.directWheel || !root.interactive)
                return

            var delta = event.pixelDelta.y
            if (delta === 0)
                delta = (event.angleDelta.y / 120.0) * Theme.px(82)
            if (delta === 0)
                return

            var maximumY = Math.max(0, root.contentHeight - root.height)
            var nextY = root.clamp(root.contentY - delta * root.wheelMultiplier, 0, maximumY)
            if (nextY !== root.contentY) {
                root.contentY = nextY
                event.accepted = true
            }
        }
    }
}
