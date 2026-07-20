import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    Image {
        anchors.fill: parent
        source: assetRoot + "/" + Theme.backdropBaseFile
        fillMode: Image.PreserveAspectCrop
        smooth: true
        mipmap: true
    }

    Image {
        id: topBranch
        visible: Theme.backdropBranchesVisible
        source: visible && Theme.backdropBranchTopFile.length > 0
                ? assetRoot + "/" + Theme.backdropBranchTopFile
                : ""
        width: parent.width * 0.70
        height: parent.height * 0.46
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: -parent.width * 0.015
        anchors.topMargin: -Theme.px(5)
        fillMode: Image.PreserveAspectFit
        transformOrigin: Item.TopRight
        opacity: Theme.backdropTopBranchOpacity
        smooth: true
        mipmap: true
        SequentialAnimation on rotation {
            running: Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode && topBranch.visible
            loops: Animation.Infinite
            NumberAnimation { from: -0.18; to: 0.22; duration: 9000; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.22; to: -0.18; duration: 9000; easing.type: Easing.InOutSine }
        }
    }

    Image {
        id: bottomBranch
        visible: Theme.backdropBranchesVisible
        source: visible && Theme.backdropBranchBottomFile.length > 0
                ? assetRoot + "/" + Theme.backdropBranchBottomFile
                : ""
        width: parent.width * 0.36
        height: parent.height * 0.42
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: -parent.width * 0.03
        anchors.bottomMargin: -parent.height * 0.02
        fillMode: Image.PreserveAspectFit
        transformOrigin: Item.BottomLeft
        opacity: Theme.backdropBottomBranchOpacity
        smooth: true
        mipmap: true
        SequentialAnimation on rotation {
            running: Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode && bottomBranch.visible
            loops: Animation.Infinite
            NumberAnimation { from: 0.18; to: -0.20; duration: 10400; easing.type: Easing.InOutSine }
            NumberAnimation { from: -0.20; to: 0.18; duration: 10400; easing.type: Easing.InOutSine }
        }
    }

    PetalField { anchors.fill: parent; visible: Theme.backdropPetalsVisible }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.backdropOverlayTop }
            GradientStop { position: 0.58; color: Theme.backdropOverlayMiddle }
            GradientStop { position: 1.0; color: Theme.backdropOverlayBottom }
        }
    }
}
