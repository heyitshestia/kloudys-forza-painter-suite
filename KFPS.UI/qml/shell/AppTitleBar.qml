import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../components"

Rectangle {
    id: root

    property var window

    color: Theme.titleBarSurface
    height: Theme.px(Metrics.titleHeight)

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(1, Theme.px(1))
        color: Theme.borderSoft
        opacity: 0.5
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: Theme.px(10)
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
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(10.5)
            renderType: Text.NativeRendering
            font.hintingPreference: Font.PreferFullHinting
            verticalAlignment: Text.AlignVCenter
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Row {
        anchors.right: parent.right
        anchors.top: parent.top
        height: parent.height

        Repeater {
            model: ["min", "max", "close"]

            delegate: Rectangle {
                id: button
                required property string modelData

                objectName: "TitleBarButton:" + button.modelData

                width: Theme.px(46)
                height: parent.height
                color: hover.hovered
                       ? (modelData === "close" ? Theme.titleBarCloseHover : Theme.titleBarButtonHover)
                       : "transparent"

                Item {
                    anchors.centerIn: parent
                    width: Theme.px(16)
                    height: Theme.px(16)

                    Rectangle {
                        visible: button.modelData === "min"
                        width: Theme.px(12)
                        height: Math.max(1, Theme.px(1))
                        color: Theme.text
                        anchors.centerIn: parent
                    }

                    Rectangle {
                        visible: button.modelData === "max"
                        width: Theme.px(11)
                        height: Theme.px(10)
                        color: "transparent"
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.text
                        anchors.centerIn: parent
                    }

                    Text {
                        visible: button.modelData === "close"
                        anchors.centerIn: parent
                        text: "×"
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(19)
                        font.weight: Font.Light
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
