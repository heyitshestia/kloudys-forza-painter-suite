import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    enabled: false
    visible: transitionLoader.active

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
