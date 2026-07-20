import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property string name: "home"
    property real iconSize: Theme.px(22)
    property real iconOpacity: 1
    property bool glow: false
    property bool colorize: Theme.iconColorize
    property color tint: Theme.iconTint
    property color glowColor: Theme.primary
    readonly property string iconFolder: Theme.iconFolder

    implicitWidth: iconSize
    implicitHeight: iconSize
    Layout.minimumWidth: implicitWidth
    Layout.minimumHeight: implicitHeight

    Image {
        id: image
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: root.name.length > 0 ? assetRoot + "/" + root.iconFolder + "/" + root.name + ".svg" : ""
        fillMode: Image.PreserveAspectFit
        opacity: root.iconOpacity
        smooth: true
        mipmap: true
        asynchronous: true
        layer.enabled: root.colorize || (root.glow && !screenshotMode)
        layer.smooth: true
        layer.effect: MultiEffect {
            colorization: root.colorize ? 1.0 : 0.0
            colorizationColor: root.tint
            shadowEnabled: root.glow && !screenshotMode
            shadowColor: root.glowColor
            shadowBlur: 0.72
            shadowOpacity: 0.92
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
        }
    }
}
