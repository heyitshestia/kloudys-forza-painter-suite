import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

FocusScope {
    id: root
    property string themeId: "ps2"
    property string videoObjectName: "ThemeStartupVideo"
    property var navigation: null
    property var service: null
    property bool waiting: false
    property bool begun: false
    property int stalledTicks: 0
    property int lastPosition: -1
    property string lastFrame: ""
    readonly property bool suspended: !Window.window || !Window.window.visible || Window.window.visibility === Window.Minimized
    signal finished()
    parent: navigation ? navigation.parent : null
    anchors.fill: parent
    z: 40
    visible: false
    enabled: visible
    clip: true

    function begin() {
        if (begun || !service || !service.claim(themeId)) return false
        begun = true
        if (Theme.reducedMotion) return false
        waiting = false; stalledTicks = 0
        lastPosition = -1; lastFrame = ""
        visible = true
        forceActiveFocus()
        if (!suspended) service.play()
        return true
    }
    function finish() {
        if (!visible) return
        if (service) service.stop()
        visible = false; waiting = false; focus = false
        finished()
    }
    function endPlayback() {
        if (service) service.stop()
        waiting = true
        if (!service || service.ready) finish()
    }
    function fail(message) {
        if (!visible) return
        if (service) service.recordPlaybackError(message)
        finish()
    }
    onSuspendedChanged: {
        if (!visible || waiting) return
        stalledTicks = 0
        if (suspended) service.pause()
        else service.play()
    }
    Connections {
        target: Theme
        function onReducedMotionChanged() { if (Theme.reducedMotion && root.visible) root.finish() }
    }
    Connections {
        target: root.service
        function onChanged() { if (root.waiting && root.service.ready) root.finish() }
        function onMediaEnded() { root.endPlayback() }
        function onPlaybackError(message) { root.fail(message) }
    }
    Component.onDestruction: { if (service && begun) service.stop() }
    Keys.onEscapePressed: function(event) { root.finish(); event.accepted = true }
    Keys.onReturnPressed: function(event) { root.finish(); event.accepted = true }
    Keys.onEnterPressed: function(event) { root.finish(); event.accepted = true }
    Keys.onSpacePressed: function(event) { root.finish(); event.accepted = true }

    Rectangle { anchors.fill: parent; color: Theme.backgroundA }
    // One decoded frame at a time, on the same clock as the supplied soundtrack.
    Image {
        id: screen
        objectName: root.videoObjectName
        anchors.fill: parent
        fillMode: Image.PreserveAspectFit
        source: root.visible && !root.waiting && root.service ? root.service.frameSource : ""
        cache: false
        smooth: true
        visible: !root.waiting
    }
    Column {
        anchors.centerIn: parent
        spacing: Theme.px(18)
        visible: root.waiting
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "KFPS"; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.px(46) }
        Text { text: qsTr("Finishing loading..."); color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(15) }
    }
    Timer {
        interval: 250; repeat: true
        running: root.visible && !root.waiting && !root.suspended
        onTriggered: {
            if (root.service.position === root.lastPosition || root.service.frameSource === root.lastFrame) root.stalledTicks++
            else root.stalledTicks = 0
            root.lastPosition = root.service.position
            root.lastFrame = root.service.frameSource
            if (root.stalledTicks >= 20) root.fail("Playback stopped advancing.")
        }
    }
}
