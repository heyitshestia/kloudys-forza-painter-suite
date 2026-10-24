import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "XboxMotion.js" as Motion

Item {
    id: root
    objectName: "XboxMotionClock"
    property bool requested: true
    property bool applicationActive: Window.window ? Window.window.active : false
    readonly property bool windowVisible: Window.window ? Window.window.visible && Window.window.visibility !== Window.Minimized : false
    readonly property bool dashboardVisible: Boolean(Window.window && Window.window.dashboardNavigationVisible)
    readonly property bool running: requested && visible && windowVisible && applicationActive
                                    && Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
    property real seconds: 0
    property double lastTick: 0
    signal tick()
    Timer {
        interval: Motion.frameInterval
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
