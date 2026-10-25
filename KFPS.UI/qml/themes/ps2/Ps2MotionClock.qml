import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "Ps2MotionClock"
    property bool requested: true
    property bool applicationActive: Window.window ? Window.window.active : false
    readonly property bool windowVisible: Window.window ? Window.window.visible && Window.window.visibility !== Window.Minimized : false
    readonly property bool running: requested && visible && applicationActive && windowVisible
                                    && Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
    property real seconds: 17
    property double lastTick: 0
    signal tick()
    Timer {
        interval: 33
        repeat: true
        running: root.running
        onRunningChanged: root.lastTick = Date.now()
        onTriggered: {
            var now = Date.now()
            root.seconds += Math.min(100, now - root.lastTick) / 1000
            root.lastTick = now
            root.tick()
        }
    }
}
