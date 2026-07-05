import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

ComboBox {
    id: root

    objectName: "KfpsComboBox"

    property bool dense: false
    property real minimumWidth: Theme.px(96)
    signal doubleTapped()

    implicitHeight: Math.max(
                        Theme.px(dense ? Metrics.denseButtonHeight : Metrics.fieldHeight),
                        fieldText.implicitHeight + Theme.px(dense ? 10 : 14))
    implicitWidth: Theme.px(170)
    Layout.minimumWidth: root.minimumWidth
    Layout.minimumHeight: root.implicitHeight

    leftPadding: Theme.px(dense ? 10 : 12)
    rightPadding: Theme.px(dense ? 30 : 34)
    topPadding: 0
    bottomPadding: 0
    font.family: Theme.fontFamily
    font.pixelSize: Theme.px(dense ? 10.5 : 11.5)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    contentItem: Text {
        id: fieldText
        text: root.displayText
        color: root.enabled ? Theme.text : Theme.subtle
        font: root.font
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignLeft
        wrapMode: Text.NoWrap
        elide: Text.ElideRight
        clip: true
    }

    indicator: Item {
        implicitWidth: Theme.px(22)
        implicitHeight: root.implicitHeight
        x: root.width - width - Theme.px(7)
        y: 0

        Icon {
            anchors.centerIn: parent
            name: "chevron-right"
            iconSize: Theme.px(root.dense ? 12 : 14)
            rotation: 90
            colorize: true
            tint: root.popup.visible ? Theme.primaryBright : Theme.muted
            glow: false
        }
    }

    background: Item {
        Rectangle {
            id: comboChrome
            anchors.fill: parent
            radius: Theme.px(Metrics.controlRadius)
            color: root.popup.visible ? Theme.comboSurfaceOpen : (root.hovered ? Theme.comboHoverSurface : Theme.fieldSurface)
            border.width: root.activeFocus ? Theme.px(2) : Theme.px(1)
            border.color: root.activeFocus ? Theme.focusColor
                                           : (root.popup.visible ? Theme.primaryBright
                                                                 : (root.hovered ? Theme.primary : Theme.borderSoft))
            opacity: root.enabled ? 1.0 : 0.64
            clip: true
            Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 120 } }
            Behavior on border.color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 120 } }

            Image {
                anchors.fill: parent
                visible: Theme.panelRefractionFile.length > 0
                source: visible ? assetRoot + "/" + Theme.panelRefractionFile : ""
                fillMode: Image.Tile
                opacity: Theme.panelRefractionOpacity * (root.popup.visible ? 0.34 : (root.hovered ? 0.24 : 0.16))
                smooth: true
                clip: true
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: Theme.px(1)
                anchors.rightMargin: Theme.px(1)
                anchors.topMargin: Theme.px(1)
                height: parent.height * 0.48
                radius: Math.max(0, comboChrome.radius - Theme.px(1))
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.74; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.popup.visible ? 0.42 : (root.hovered ? 0.30 : 0.20)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 120 } }
            }
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onDoubleTapped: root.doubleTapped()
    }

    delegate: ItemDelegate {
        id: delegateRoot
        required property var modelData
        width: ListView.view ? ListView.view.width : root.width
        implicitHeight: Math.max(Theme.px(36), delegateLabel.implicitHeight + Theme.px(12))
        leftPadding: Theme.px(10)
        rightPadding: Theme.px(10)

        contentItem: Text {
            id: delegateLabel
            text: delegateRoot.modelData
            color: delegateRoot.highlighted ? Theme.primaryText : Theme.text
            font: root.font
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignLeft
            elide: Text.ElideRight
        }

        background: Rectangle {
            color: delegateRoot.highlighted ? Theme.comboHighlight : "transparent"
            radius: Theme.px(6)
        }
    }

    popup: Popup {
        y: root.height + Theme.px(4)
        width: root.width
        implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, Theme.px(260))
        padding: Theme.px(4)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        background: Item {
            Rectangle {
                id: popupChrome
                anchors.fill: parent
                radius: Theme.px(10)
                color: Theme.comboPopupSurface
                border.width: Theme.px(1)
                border.color: Theme.borderStrong
                clip: true

                Image {
                    anchors.fill: parent
                    visible: Theme.panelRefractionFile.length > 0
                    source: visible ? assetRoot + "/" + Theme.panelRefractionFile : ""
                    fillMode: Image.Tile
                    opacity: Theme.panelRefractionOpacity * 0.20
                    smooth: true
                    clip: true
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: Theme.px(1)
                    anchors.rightMargin: Theme.px(1)
                    anchors.topMargin: Theme.px(1)
                    height: parent.height * 0.18
                    radius: Math.max(0, popupChrome.radius - Theme.px(1))
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                        GradientStop { position: 0.78; color: Theme.primaryButtonGlassMiddle }
                        GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                    }
                    opacity: 0.22
                }
            }
        }

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            highlightMoveDuration: Theme.reducedMotion ? 0 : 90
            ScrollIndicator.vertical: ScrollIndicator { }
        }
    }
}
