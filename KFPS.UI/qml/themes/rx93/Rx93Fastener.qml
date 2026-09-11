import QtQuick 6.7

Rectangle {
    width: 5
    height: width
    radius: width / 2
    color: "#151a1b"
    border.width: 1
    border.color: "#6b7774"
    Rectangle {
        anchors.centerIn: parent
        width: parent.width * 0.6
        height: 1
        rotation: -35
        color: "#89918a"
    }
}
