import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property var window
    readonly property real edgeSize: Theme.px(6)
    readonly property real cornerSize: Theme.px(12)

    enabled: Boolean(window) && window.visibility === Window.Windowed

    component ResizeZone: MouseArea {
        required property int resizeEdges

        acceptedButtons: Qt.LeftButton
        preventStealing: true
        onPressed: mouse => {
            mouse.accepted = Boolean(root.window)
                             && root.window.startSystemResize(resizeEdges)
        }
    }

    ResizeZone {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: root.edgeSize
        resizeEdges: Qt.TopEdge
        cursorShape: Qt.SizeVerCursor
    }

    ResizeZone {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.edgeSize
        resizeEdges: Qt.BottomEdge
        cursorShape: Qt.SizeVerCursor
    }

    ResizeZone {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.edgeSize
        resizeEdges: Qt.LeftEdge
        cursorShape: Qt.SizeHorCursor
    }

    ResizeZone {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.edgeSize
        resizeEdges: Qt.RightEdge
        cursorShape: Qt.SizeHorCursor
    }

    ResizeZone {
        anchors.left: parent.left
        anchors.top: parent.top
        width: root.cornerSize
        height: root.cornerSize
        resizeEdges: Qt.TopEdge | Qt.LeftEdge
        cursorShape: Qt.SizeFDiagCursor
    }

    ResizeZone {
        anchors.right: parent.right
        anchors.top: parent.top
        width: root.cornerSize
        height: root.cornerSize
        resizeEdges: Qt.TopEdge | Qt.RightEdge
        cursorShape: Qt.SizeBDiagCursor
    }

    ResizeZone {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        width: root.cornerSize
        height: root.cornerSize
        resizeEdges: Qt.BottomEdge | Qt.LeftEdge
        cursorShape: Qt.SizeBDiagCursor
    }

    ResizeZone {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: root.cornerSize
        height: root.cornerSize
        resizeEdges: Qt.BottomEdge | Qt.RightEdge
        cursorShape: Qt.SizeFDiagCursor
    }
}
