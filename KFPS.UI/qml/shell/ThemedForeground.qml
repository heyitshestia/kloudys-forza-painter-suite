import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    Loader {
        anchors.fill: parent
        asynchronous: false
        source: Theme.foregroundComponentFile
    }
}
