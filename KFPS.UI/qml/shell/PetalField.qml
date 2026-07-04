import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    clip: true
    property bool running: Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode && Theme.backdropPetalsVisible

    Repeater {
        model: [
            { y: 0.16, d: 21000, s: 23, r: 720, delay: 0, a: 0.70 },
            { y: 0.26, d: 26000, s: 17, r: 790, delay: 2100, a: 0.62 },
            { y: 0.39, d: 22500, s: 19, r: 680, delay: 4700, a: 0.64 },
            { y: 0.51, d: 28500, s: 14, r: 860, delay: 7600, a: 0.54 },
            { y: 0.64, d: 19500, s: 18, r: 660, delay: 10400, a: 0.62 },
            { y: 0.77, d: 24500, s: 15, r: 770, delay: 13200, a: 0.52 },
            { y: 0.31, d: 21800, s: 13, r: 700, delay: 1400, a: 0.48 },
            { y: 0.69, d: 26500, s: 20, r: 820, delay: 5600, a: 0.58 }
        ]
        delegate: Image {
            id: petal
            width: Theme.px(modelData.s)
            height: width * 0.72
            source: assetRoot + "/" + Theme.backdropPetalFile
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            opacity: screenshotMode ? modelData.a * 0.45 : 0
            y: root.height * modelData.y
            x: screenshotMode ? root.width * (0.08 + index * 0.105) : -60
            rotation: screenshotMode ? index * 39 : 0

            SequentialAnimation {
                running: root.running
                loops: Animation.Infinite
                PauseAnimation { duration: modelData.delay }
                ParallelAnimation {
                    NumberAnimation { target: petal; property: "x"; from: -60; to: root.width + 90; duration: modelData.d }
                    SequentialAnimation {
                        NumberAnimation { target: petal; property: "y"; to: root.height * modelData.y - 38; duration: modelData.d * 0.34; easing.type: Easing.InOutSine }
                        NumberAnimation { target: petal; property: "y"; to: root.height * modelData.y + 104; duration: modelData.d * 0.66; easing.type: Easing.InOutSine }
                    }
                    NumberAnimation { target: petal; property: "rotation"; from: 0; to: modelData.r; duration: modelData.d }
                    SequentialAnimation {
                        NumberAnimation { target: petal; property: "opacity"; from: 0; to: modelData.a; duration: 900 }
                        PauseAnimation { duration: modelData.d - 2700 }
                        NumberAnimation { target: petal; property: "opacity"; to: 0; duration: 1800 }
                    }
                }
                PropertyAction { target: petal; property: "x"; value: -60 }
                PropertyAction { target: petal; property: "y"; value: root.height * modelData.y }
            }
        }
    }
}
