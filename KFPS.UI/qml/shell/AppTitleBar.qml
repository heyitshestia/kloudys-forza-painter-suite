import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

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
        spacing: Theme.px(7)

        Image {
            source: assetRoot + "/" + Theme.logoFile
            width: Theme.px(16)
            height: width
            fillMode: Image.PreserveAspectFit
            smooth: true
        }

        Text {
            text: appController.windowTitle
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
