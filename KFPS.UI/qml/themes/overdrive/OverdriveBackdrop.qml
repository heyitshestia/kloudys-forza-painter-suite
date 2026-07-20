import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root

    readonly property bool applicationActive: Window.window ? Window.window.active : true
    readonly property bool motionAllowed: Theme.ambientMotion
                                          && !Theme.reducedMotion
                                          && !screenshotMode
                                          && applicationActive
    property real meterPhase: screenshotMode ? 5.0 : 0.0

    Rectangle {
        anchors.fill: parent
        color: Theme.backgroundA
    }

    Image {
        id: chassis
        anchors.fill: parent
        source: assetRoot + "/" + Theme.backdropBaseFile
        fillMode: Image.PreserveAspectCrop
        horizontalAlignment: Image.AlignHCenter
        verticalAlignment: Image.AlignVCenter
        smooth: true
        mipmap: true
        cache: true
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.backdropOverlayTop }
            GradientStop { position: 0.52; color: Theme.backdropOverlayMiddle }
            GradientStop { position: 1.0; color: Theme.backdropOverlayBottom }
        }
    }

    Item {
        id: displayWindow
        x: root.width * 0.155
        y: root.height * 0.184
        width: root.width * 0.69
        height: root.height * 0.142
        clip: true

        Rectangle {
            id: displayGlow
            anchors.fill: parent
            radius: Theme.px(18)
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.withAlpha(Theme.primaryDeep, 0.07) }
                GradientStop { position: 0.62; color: Theme.withAlpha(Theme.signalPrimary, 0.11) }
                GradientStop { position: 1.0; color: Theme.withAlpha(Theme.signalPrimary, 0.035) }
            }
            opacity: screenshotMode ? 0.72 : 0.66

            SequentialAnimation on opacity {
                running: root.motionAllowed
                loops: Animation.Infinite
                NumberAnimation { to: 0.70; duration: 6000; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0.64; duration: 6000; easing.type: Easing.InOutSine }
            }
        }

        Rectangle {
            id: scanLine
            x: screenshotMode ? displayWindow.width * 0.36 : -width
            y: Theme.px(5)
            width: Math.max(Theme.px(2), displayWindow.width * 0.004)
            height: displayWindow.height - Theme.px(10)
            radius: width / 2
            opacity: 0.44
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.withAlpha(Theme.signalPrimary, 0.0) }
                GradientStop { position: 0.5; color: Theme.withAlpha(Theme.signalPrimary, 0.72) }
                GradientStop { position: 1.0; color: Theme.withAlpha(Theme.signalPrimary, 0.0) }
            }

            SequentialAnimation {
                running: root.motionAllowed && Theme.ambientScanEnabled
                loops: Animation.Infinite
                PauseAnimation { duration: 4200 }
                PropertyAction { target: scanLine; property: "x"; value: -scanLine.width }
                NumberAnimation {
                    target: scanLine
                    property: "x"
                    to: displayWindow.width + scanLine.width
                    duration: 2300
                    easing.type: Easing.InOutCubic
                }
                PauseAnimation { duration: 17400 }
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: parent.width * 0.055
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.px(8)
            spacing: Theme.px(4)

            Repeater {
                model: 10

                Rectangle {
                    required property int index
                    width: Theme.px(3)
                    height: Theme.px(4 + (index % 3) * 2)
                    radius: width / 2
                    anchors.bottom: parent.bottom
                    color: index < 7 ? Theme.signalPrimary : Theme.signalSecondary
                    opacity: root.meterPhase > index ? 0.82 : 0.13
                    Behavior on opacity {
                        enabled: !Theme.reducedMotion
                        NumberAnimation { duration: 105; easing.type: Easing.OutCubic }
                    }
                }
            }
        }
    }

    SequentialAnimation {
        running: root.motionAllowed && Theme.ambientScanEnabled
        loops: Animation.Infinite
        PauseAnimation { duration: 2900 }
        PropertyAction { target: root; property: "meterPhase"; value: 0.0 }
        NumberAnimation {
            target: root
            property: "meterPhase"
            to: 10.0
            duration: 1300
            easing.type: Easing.OutCubic
        }
        PauseAnimation { duration: 900 }
        NumberAnimation {
            target: root
            property: "meterPhase"
            to: 2.0
            duration: 460
            easing.type: Easing.InCubic
        }
        PauseAnimation { duration: 14200 }
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: root.width * 0.017
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.height * 0.105
        spacing: Theme.px(7)

        Repeater {
            model: [Theme.signalSuccess, Theme.signalSecondary, Theme.signalDanger]
            Rectangle {
                required property color modelData
                width: Theme.px(5)
                height: width
                radius: width / 2
                color: modelData
                opacity: 0.72
            }
        }
    }
}
