import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    // Static and noninteractive. Theme.ambientMotion, Theme.reducedMotion and
    // screenshotMode govern the backdrop, not this border.
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: Theme.px(2); color: Theme.primary }
}
