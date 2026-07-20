import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

ScrollView {
    id: root

    property real wheelMultiplier: 1.0
    property bool directWheel: true

    clip: true

    ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
    ScrollBar.horizontal: KfpsScrollBar {
        orientation: Qt.Horizontal
        policy: ScrollBar.AsNeeded
    }

    Component.onCompleted: tuneFlickable()
    onContentItemChanged: tuneFlickable()

    function tuneFlickable() {
        if (!contentItem)
            return
        if (contentItem.hasOwnProperty("boundsBehavior"))
            contentItem.boundsBehavior = Flickable.StopAtBounds
        if (contentItem.hasOwnProperty("maximumFlickVelocity"))
            contentItem.maximumFlickVelocity = 100000
        if (contentItem.hasOwnProperty("flickDeceleration"))
            contentItem.flickDeceleration = 12000
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }

    WheelHandler {
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        target: null
        onWheel: event => {
            if (!root.directWheel || !root.contentItem)
                return
            var flickable = root.contentItem
            if (!flickable.hasOwnProperty("contentY"))
                return

            var delta = event.pixelDelta.y
            if (delta === 0)
                delta = (event.angleDelta.y / 120.0) * Theme.px(82)
            if (delta === 0)
                return

            var maximumY = Math.max(0, flickable.contentHeight - flickable.height)
            var nextY = root.clamp(flickable.contentY - delta * root.wheelMultiplier, 0, maximumY)
            if (nextY !== flickable.contentY) {
                flickable.contentY = nextY
                event.accepted = true
            }
        }
    }
}
