import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../components"

Rectangle {
    id: root

    property var window

    color: Theme.classicMode ? Theme.surface : Theme.titleBarSurface
    height: Theme.px(Theme.classicMode ? 30 : Metrics.titleHeight)

    ClassicBevel {
        anchors.fill: parent
        z: 20
    }

    Rectangle {
        visible: Theme.classicMode
        anchors.left: parent.left
        anchors.right: windowButtons.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: Theme.px(3)
        anchors.rightMargin: Theme.px(2)
        anchors.topMargin: Theme.px(3)
        anchors.bottomMargin: Theme.px(3)
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Theme.titleBarSurface }
            GradientStop { position: 1.0; color: Theme.primaryBright }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(1, Theme.px(1))
        color: Theme.borderSoft
        opacity: Theme.classicMode ? 0 : 0.5
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(Theme.classicMode ? 7 : 10)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.terminalMode ? 0 : Theme.px(7)

        ThemedLogo {
            visible: !Theme.terminalMode
            width: visible ? Theme.px(16) : 0
            height: width
            logoMargin: 0
        }

        Text {
            text: Theme.terminalMode
                  ? "C:\\WINDOWS\\system32\\cmd.exe - KFPS"
                  : appController.windowTitle
            color: Theme.classicMode ? Theme.primaryText : Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(Theme.classicMode ? 12 : 10.5)
            font.weight: Theme.classicMode ? Font.Bold : Font.Normal
            renderType: Text.NativeRendering
            font.hintingPreference: Font.PreferFullHinting
            verticalAlignment: Text.AlignVCenter
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Row {
        id: windowButtons
        anchors.right: parent.right
        anchors.rightMargin: Theme.classicMode ? Theme.px(3) : 0
        anchors.top: parent.top
        anchors.topMargin: Theme.classicMode ? Theme.px(3) : 0
        height: Theme.classicMode ? parent.height - Theme.px(6) : parent.height
        spacing: Theme.classicMode ? Theme.px(2) : 0

        Repeater {
            model: ["min", "max", "close"]

            delegate: Rectangle {
                id: button
                required property string modelData

                objectName: "TitleBarButton:" + button.modelData
                readonly property bool pressed: buttonTap.pressed

                width: Theme.px(Theme.classicMode ? 24 : 46)
                height: parent.height
                color: Theme.classicMode
                       ? Theme.surface
                       : (hover.hovered
                          ? (modelData === "close" ? Theme.titleBarCloseHover : Theme.titleBarButtonHover)
                          : "transparent")

                ClassicBevel {
                    anchors.fill: parent
                    pressed: buttonTap.pressed
                }

                Item {
                    anchors.centerIn: parent
                    width: Theme.px(16)
                    height: Theme.px(16)

                    Rectangle {
                        visible: button.modelData === "min"
                        width: Theme.px(12)
                        height: Math.max(1, Theme.px(1))
                        color: Theme.classicMode ? Theme.borderStrong : Theme.text
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: Theme.classicMode ? Theme.px(4) : 0
                    }

                    Rectangle {
                        visible: button.modelData === "max"
                        width: Theme.px(11)
                        height: Theme.px(10)
                        color: "transparent"
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.classicMode ? Theme.borderStrong : Theme.text
                        anchors.centerIn: parent
                    }

                    Text {
                        visible: button.modelData === "close"
                        anchors.centerIn: parent
                        text: "×"
                        color: Theme.classicMode ? Theme.borderStrong : Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(Theme.classicMode ? 15 : 19)
                        font.weight: Theme.classicMode ? Font.Bold : Font.Light
                        renderType: Text.NativeRendering
                        font.hintingPreference: Font.PreferFullHinting
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }

                KfpsToolTip {
                    visible: hover.hovered
                    text: button.modelData === "min"
                          ? "Minimize KFPS."
                          : (button.modelData === "max"
                             ? (root.window.visibility === Window.FullScreen || root.window.visibility === Window.Maximized
                                ? "Restore the KFPS window."
                                : "Maximize the KFPS window.")
                             : "Close KFPS.")
                }

                TapHandler {
                    id: buttonTap
                    onTapped: {
                        if (button.modelData === "min") {
                            root.window.showMinimized()
                        } else if (button.modelData === "max") {
                            if (root.window.visibility === Window.FullScreen || root.window.visibility === Window.Maximized)
                                root.window.showNormal()
                            else
                                root.window.showMaximized()
                        } else {
                            root.window.close()
                        }
                    }
                }
            }
        }
    }

    Row {
        visible: Theme.equipmentAccentsEnabled
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(4)
        opacity: 0.68

        Repeater {
            model: 7
            Rectangle {
                required property int index
                width: Theme.px(index === 3 ? 12 : 5)
                height: Theme.px(2)
                radius: Theme.corner(height / 2)
                color: index === 5 ? Theme.signalSecondary : Theme.signalPrimary
            }
        }
    }

    DragHandler {
        target: null
        acceptedButtons: Qt.LeftButton
        grabPermissions: PointerHandler.TakeOverForbidden
        onActiveChanged: {
            if (active && root.window && root.window.visibility !== Window.FullScreen)
                root.window.startSystemMove()
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onDoubleTapped: {
            if (root.window.visibility === Window.FullScreen || root.window.visibility === Window.Maximized)
                root.window.showNormal()
            else
                root.window.showMaximized()
        }
    }
}
