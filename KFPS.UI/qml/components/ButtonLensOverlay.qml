import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool active: true
    property bool hovered: false
    property bool pressed: false
    property bool latched: false
    property real strength: 1.0
    property real signalPhase: screenshotMode && active ? 2.6 : (latched ? 4.0 : 0.0)

    visible: active && Theme.primaryButtonLensOverlayFile.length > 0
    clip: true

    Image {
        anchors.fill: parent
        source: root.visible ? assetRoot + "/" + Theme.primaryButtonLensOverlayFile : ""
        fillMode: Image.Stretch
        opacity: Theme.primaryButtonLensOverlayOpacity
                 * root.strength
                 * (root.pressed ? 0.78 : (root.hovered ? 1.0 : 0.88))
        smooth: true
        mipmap: true

        Behavior on opacity {
            enabled: !Theme.reducedMotion
            NumberAnimation { duration: 105; easing.type: Easing.OutCubic }
        }
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(7)
        anchors.top: parent.top
        anchors.topMargin: Theme.px(3)
        spacing: Theme.px(2)
        visible: Theme.controlSignalEnabled

        Repeater {
            model: 4

            Rectangle {
                required property int index
                width: Theme.px(index === 3 ? 6 : 3)
                height: Theme.px(2)
                radius: Theme.corner(height / 2)
                color: index === 2 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: root.pressed || root.signalPhase > index
                         ? (index === 2 ? 0.94 : 0.82)
                         : 0.10

                Behavior on opacity {
                    enabled: !Theme.reducedMotion
                    NumberAnimation { duration: 80; easing.type: Easing.OutCubic }
                }
            }
        }
    }

    onHoveredChanged: {
        if (!root.active)
            return
        if (root.hovered) {
            if (Theme.reducedMotion || screenshotMode)
                root.signalPhase = 4.0
            else
                signalAnimation.restart()
        } else if (!root.latched && !root.pressed && !screenshotMode) {
            root.signalPhase = 0.0
        }
    }

    onLatchedChanged: {
        if (root.latched)
            root.signalPhase = 4.0
        else if (!root.hovered && !screenshotMode)
            root.signalPhase = 0.0
    }

    SequentialAnimation {
        id: signalAnimation
        PropertyAction { target: root; property: "signalPhase"; value: 0.0 }
        NumberAnimation {
            target: root
            property: "signalPhase"
            to: 4.0
            duration: 190
            easing.type: Easing.OutCubic
        }
    }
}
