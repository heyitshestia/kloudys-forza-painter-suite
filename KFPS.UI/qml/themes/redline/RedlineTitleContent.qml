import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    enabled: false
    clip: true
    Rectangle { width: Theme.px(4); height: parent.height; color: Theme.primary }
    RedlineText { anchors.verticalCenter: parent.verticalCenter; x: Theme.px(14); width: parent.width - x; text: "KFPS  /  REDLINE"; font.family: Theme.monoFamily; font.pixelSize: Theme.px(10); color: Theme.subtle }
}
