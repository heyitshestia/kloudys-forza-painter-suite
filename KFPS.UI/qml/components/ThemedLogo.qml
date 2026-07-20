import QtQuick 6.7
import QtQuick.Effects 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool showDial: false
    property real logoMargin: 0

    Image {
        anchors.fill: parent
        visible: root.showDial && Theme.logoDialFile.length > 0
        source: visible ? assetRoot + "/" + Theme.logoDialFile : ""
        fillMode: Image.PreserveAspectFit
        opacity: Theme.logoDialOpacity
        smooth: !Theme.classicMode
        mipmap: !Theme.classicMode
    }

    Image {
        id: plainLogo
        anchors.fill: parent
        anchors.margins: root.logoMargin
        visible: !Theme.logoColorize
        source: assetRoot + "/" + Theme.logoFile
        fillMode: Image.PreserveAspectFit
        smooth: !Theme.classicMode
        mipmap: !Theme.classicMode
    }

    Image {
        id: colorSource
        anchors.fill: parent
        anchors.margins: root.logoMargin
        visible: false
        source: assetRoot + "/" + Theme.logoFile
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }

    MultiEffect {
        anchors.fill: colorSource
        visible: Theme.logoColorize
        source: colorSource
        colorization: 1.0
        colorizationColor: Theme.logoTint
        brightness: 0.08
        contrast: 0.16
        shadowEnabled: Theme.glassEffects && !screenshotMode
        shadowColor: Theme.signalPrimary
        shadowBlur: 0.35
        shadowOpacity: 0.35
    }
}
