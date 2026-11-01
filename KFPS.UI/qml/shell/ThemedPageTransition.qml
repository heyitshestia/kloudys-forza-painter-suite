import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "ThemedPageTransition"

    enabled: false
    visible: transitionLoader.active
    readonly property real contentOffsetX: transitionLoader.item && typeof transitionLoader.item.contentOffsetX === "number" ? transitionLoader.item.contentOffsetX : 0
    readonly property real contentOffsetY: transitionLoader.item && typeof transitionLoader.item.contentOffsetY === "number" ? transitionLoader.item.contentOffsetY : 0
    readonly property bool replayOnContentReady: transitionLoader.item && transitionLoader.item.replayOnContentReady === true

    function play() {
        if (transitionLoader.item && typeof transitionLoader.item.play === "function")
            transitionLoader.item.play()
    }

    Loader {
        id: transitionLoader
        anchors.fill: parent
        active: Theme.pageTransitionComponentFile.length > 0
        asynchronous: false
        source: active ? Theme.pageTransitionComponentFile : ""
    }
}
