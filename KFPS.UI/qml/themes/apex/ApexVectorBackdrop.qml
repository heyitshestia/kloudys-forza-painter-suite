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
    property real assemblyDrift: screenshotMode ? -8 : 0
    property real assemblyYaw: screenshotMode ? -3.5 : -6
    property real assemblyRoll: screenshotMode ? 1.2 : -1.2
    property real dataPhase: screenshotMode ? 8.0 : 0.0
    property real acquisitionProgress: screenshotMode ? 0.62 : -0.28
    property real acquisitionStrength: screenshotMode ? 0.30 : 0.0
    property real registrationPulse: screenshotMode ? 0.58 : 0.18
    property real reticleAngle: screenshotMode ? 1.4 : -2.8
    property real railProgress: screenshotMode ? 0.68 : -0.18
    property real railStrength: screenshotMode ? 0.72 : 0.0

    Rectangle {
        anchors.fill: parent
        color: Theme.backgroundA
    }

    Image {
        anchors.fill: parent
        source: assetRoot + "/" + Theme.backdropBaseFile
        fillMode: Image.PreserveAspectCrop
        horizontalAlignment: Image.AlignHCenter
        verticalAlignment: Image.AlignVCenter
        smooth: true
        mipmap: true
        cache: true
    }

    Item {
        id: assembly
        x: root.width * 0.54 + root.assemblyDrift
        y: root.height * 0.14
        width: Math.max(Theme.px(460), root.width * 0.43)
        height: Math.max(Theme.px(430), root.height * 0.70)
        opacity: 0.56

        transform: [
            Rotation {
                origin.x: assembly.width * 0.52
                origin.y: assembly.height * 0.52
                axis.x: 0
                axis.y: 1
                axis.z: 0
                angle: root.assemblyYaw
            },
            Rotation {
                origin.x: assembly.width * 0.52
                origin.y: assembly.height * 0.52
                axis.x: 0
                axis.y: 0
                axis.z: 1
                angle: root.assemblyRoll
            }
        ]

        Canvas {
            id: layerDrawing
            anchors.fill: parent
            antialiasing: true

            function polygon(context, points) {
                context.beginPath()
                context.moveTo(points[0][0], points[0][1])
                for (var point = 1; point < points.length; ++point)
                    context.lineTo(points[point][0], points[point][1])
                context.closePath()
            }

            onPaint: {
                var context = getContext("2d")
                context.setTransform(1, 0, 0, 1, 0, 0)
                context.clearRect(0, 0, width, height)
                var unit = Math.min(width, height)
                var cx = width * 0.52
                var cy = height * 0.49

                for (var layer = 11; layer >= 0; --layer) {
                    var depth = layer / 11
                    var dx = (layer - 5.5) * unit * 0.012
                    var dy = (layer - 5.5) * unit * -0.008
                    context.save()
                    context.translate(cx + dx, cy + dy)
                    context.rotate((-8 + layer * 1.25) * Math.PI / 180)
                    context.strokeStyle = layer === 3 ? "rgba(255,23,68,0.78)"
                                                     : (layer === 8 ? "rgba(0,200,229,0.72)"
                                                                    : "rgba(8,11,12," + (0.10 + (1 - depth) * 0.22) + ")")
                    context.lineWidth = Math.max(1, unit * (layer === 3 || layer === 8 ? 0.0024 : 0.0014))
                    polygon(context, [
                        [-unit * 0.36, -unit * 0.10],
                        [-unit * 0.17, -unit * 0.28],
                        [ unit * 0.18, -unit * 0.26],
                        [ unit * 0.36, -unit * 0.04],
                        [ unit * 0.23,  unit * 0.26],
                        [-unit * 0.22,  unit * 0.29],
                        [-unit * 0.38,  unit * 0.09]
                    ])
                    context.stroke()
                    context.restore()
                }

                context.save()
                context.translate(cx, cy)
                context.strokeStyle = "rgba(8,11,12,0.44)"
                context.lineWidth = Math.max(1, unit * 0.002)
                context.setLineDash([unit * 0.013, unit * 0.021])
                context.beginPath()
                context.arc(0, 0, unit * 0.31, 0, Math.PI * 2)
                context.stroke()
                context.setLineDash([])

                context.strokeStyle = "rgba(0,200,229,0.74)"
                context.lineWidth = Math.max(1, unit * 0.003)
                context.beginPath()
                context.arc(0, 0, unit * 0.235, -0.35, 1.15)
                context.stroke()

                context.strokeStyle = "rgba(255,23,68,0.80)"
                context.beginPath()
                context.arc(0, 0, unit * 0.235, 2.05, 2.92)
                context.stroke()

                context.strokeStyle = "rgba(8,11,12,0.52)"
                context.lineWidth = Math.max(1, unit * 0.0022)
                polygon(context, [
                    [-unit * 0.12, -unit * 0.15],
                    [ unit * 0.13, -unit * 0.15],
                    [ unit * 0.20, 0],
                    [ unit * 0.12,  unit * 0.16],
                    [-unit * 0.13,  unit * 0.16],
                    [-unit * 0.20, 0]
                ])
                context.stroke()

                context.beginPath()
                context.rect(-unit * 0.08, -unit * 0.08, unit * 0.16, unit * 0.16)
                context.stroke()
                context.beginPath()
                context.arc(0, 0, unit * 0.046, 0, Math.PI * 2)
                context.stroke()
                context.restore()
            }

            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
        }

        Item {
            id: registrationInstrument
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height) * 0.46
            height: width
            rotation: root.reticleAngle
            scale: 0.97 + root.registrationPulse * 0.045
            opacity: 0.10 + root.registrationPulse * 0.15

            Image {
                anchors.fill: parent
                visible: Theme.logoDialFile.length > 0
                source: visible ? assetRoot + "/" + Theme.logoDialFile : ""
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
                opacity: 0.58
            }

            Rectangle {
                anchors.centerIn: parent
                width: parent.width * 0.54
                height: width
                radius: width / 2
                color: "transparent"
                border.width: Math.max(1, Theme.px(1))
                border.color: Theme.signalSecondary
                opacity: 0.18 + root.registrationPulse * 0.22
            }

            Repeater {
                model: 4

                Rectangle {
                    required property int index
                    anchors.centerIn: parent
                    width: index % 2 === 0 ? parent.width * 0.72 : Theme.px(2)
                    height: index % 2 === 0 ? Theme.px(2) : parent.height * 0.72
                    color: index < 2 ? Theme.signalPrimary : Theme.signalSecondary
                    opacity: index < 2 ? 0.26 : 0.18
                }
            }
        }

        Item {
            anchors.fill: parent
            clip: true

            Item {
                id: acquisitionCarriage
                x: -width
                y: assembly.height * 0.14
                width: assembly.width * 0.58
                height: assembly.height * 0.55
                rotation: -13
                opacity: root.acquisitionStrength
                transform: Translate {
                    x: root.acquisitionProgress * (assembly.width + acquisitionCarriage.width)
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    height: Theme.px(44)
                    color: Theme.signalSecondary
                    opacity: 0.08
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    height: Math.max(1, Theme.px(1.2))
                    color: Theme.signalSecondary
                    opacity: 0.82
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.rightMargin: parent.width * 0.14
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.px(18)
                    height: Theme.px(3)
                    color: Theme.signalPrimary
                    opacity: 0.92
                }
            }
        }

        Repeater {
            model: 12

            Rectangle {
                required property int index
                x: assembly.width * (0.72 + (index % 3) * 0.032)
                y: assembly.height * (0.21 + Math.floor(index / 3) * 0.055)
                width: Theme.px(index % 4 === 0 ? 18 : 7)
                height: Theme.px(3)
                color: index === 7 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: root.dataPhase > index ? 0.72 : 0.11

                Behavior on opacity {
                    enabled: !Theme.reducedMotion
                    NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                }
            }
        }
    }

    Rectangle {
        x: root.width * 0.56
        y: root.height * 0.83
        width: root.width * 0.33
        height: Math.max(1, Theme.px(1))
        color: Theme.borderStrong
        opacity: 0.20
    }

    Item {
        x: root.width * 0.56
        y: root.height * 0.83 - Theme.px(3)
        width: root.width * 0.33
        height: Theme.px(7)
        clip: true

        Row {
            x: -width
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.px(3)
            opacity: root.railStrength
            transform: Translate {
                x: root.railProgress * (parent.parent.width + parent.width)
            }

            Rectangle {
                width: Theme.px(28)
                height: Theme.px(2)
                color: Theme.signalSecondary
            }

            Rectangle {
                width: Theme.px(7)
                height: Theme.px(4)
                color: Theme.signalPrimary
            }

            Rectangle {
                width: Theme.px(4)
                height: Theme.px(2)
                color: Theme.borderStrong
            }
        }
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: root.width * 0.045
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.height * 0.055
        spacing: Theme.px(4)

        Repeater {
            model: 15

            Rectangle {
                required property int index
                width: Theme.px(index % 5 === 0 ? 18 : 5)
                height: Theme.px(3)
                color: index === 11 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: root.dataPhase > index ? 0.66 : 0.10
            }
        }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        ParallelAnimation {
            NumberAnimation { target: root; property: "assemblyDrift"; to: Theme.px(16); duration: 13000; easing.type: Easing.InOutSine }
            NumberAnimation { target: root; property: "assemblyYaw"; to: 5.5; duration: 13000; easing.type: Easing.InOutSine }
            NumberAnimation { target: root; property: "assemblyRoll"; to: 1.4; duration: 13000; easing.type: Easing.InOutSine }
        }
        ParallelAnimation {
            NumberAnimation { target: root; property: "assemblyDrift"; to: -Theme.px(10); duration: 15000; easing.type: Easing.InOutSine }
            NumberAnimation { target: root; property: "assemblyYaw"; to: -5.0; duration: 15000; easing.type: Easing.InOutSine }
            NumberAnimation { target: root; property: "assemblyRoll"; to: -1.0; duration: 15000; easing.type: Easing.InOutSine }
        }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "dataPhase"; value: 0.0 }
        NumberAnimation { target: root; property: "dataPhase"; to: 15.0; duration: 1550; easing.type: Easing.OutCubic }
        PauseAnimation { duration: 5600 }
        NumberAnimation { target: root; property: "dataPhase"; to: 5.0; duration: 420; easing.type: Easing.InCubic }
        PauseAnimation { duration: 8900 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "acquisitionProgress"; value: -0.28 }
        PropertyAction { target: root; property: "acquisitionStrength"; value: 0.0 }
        PauseAnimation { duration: 2400 }
        NumberAnimation { target: root; property: "acquisitionStrength"; to: 0.34; duration: 240; easing.type: Easing.OutQuad }
        NumberAnimation { target: root; property: "acquisitionProgress"; to: 1.08; duration: 1900; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "acquisitionStrength"; to: 0.0; duration: 360; easing.type: Easing.InQuad }
        PauseAnimation { duration: 8300 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "registrationPulse"; to: 0.72; duration: 2200; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "registrationPulse"; to: 0.20; duration: 3400; easing.type: Easing.InOutSine }
        PauseAnimation { duration: 1300 }
        NumberAnimation { target: root; property: "registrationPulse"; to: 0.54; duration: 720; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "registrationPulse"; to: 0.20; duration: 1500; easing.type: Easing.InCubic }
        PauseAnimation { duration: 5100 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "reticleAngle"; to: 3.2; duration: 17000; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "reticleAngle"; to: -2.8; duration: 19000; easing.type: Easing.InOutSine }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "railProgress"; value: -0.18 }
        PropertyAction { target: root; property: "railStrength"; value: 0.0 }
        PauseAnimation { duration: 1100 }
        NumberAnimation { target: root; property: "railStrength"; to: 0.76; duration: 160; easing.type: Easing.OutQuad }
        NumberAnimation { target: root; property: "railProgress"; to: 1.12; duration: 2700; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "railStrength"; to: 0.0; duration: 240; easing.type: Easing.InQuad }
        PauseAnimation { duration: 7600 }
    }
}
