import QtQuick 6.7
import QtQuick.Window 6.7

Item {
    id: root
    property var service
    property bool ready: false
    property bool started: false
    visible: false

    Connections {
        target: root.Window.window
        function onFrameSwapped() {
            if (root.ready && !root.started && root.service) {
                root.started = true
                root.service.start()
            }
        }
    }
}
