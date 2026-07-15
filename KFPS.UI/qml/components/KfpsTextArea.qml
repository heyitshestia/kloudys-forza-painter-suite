import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

TextArea {
    id: root

    objectName: "KfpsTextArea:" + root.placeholderText

    property real minimumHeight: Theme.px(80)
    property string toolTipText: ""
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : placeholderText

    implicitHeight: Theme.px(120)
    implicitWidth: Theme.px(240)
    Layout.minimumWidth: Theme.px(120)
    Layout.minimumHeight: root.minimumHeight

    leftPadding: Theme.px(12)
    rightPadding: Theme.px(12)
    topPadding: Theme.px(10)
    bottomPadding: Theme.px(10)
    color: Theme.text
    selectionColor: Theme.primary
    selectedTextColor: Theme.primaryText
    placeholderTextColor: Theme.subtle
    font.family: Theme.fontFamily
    font.pixelSize: Theme.px(11.5)
    renderType: TextEdit.NativeRendering
    font.hintingPreference: Font.PreferFullHinting
    wrapMode: TextEdit.Wrap
    selectByMouse: true
    hoverEnabled: true

    KfpsToolTip {
        visible: root.hovered && !root.activeFocus && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }

    background: Item {
        Rectangle {
            id: fieldChrome
            anchors.fill: parent
            radius: Theme.px(Metrics.controlRadius)
            color: root.activeFocus ? Theme.fieldFocusSurface : (root.hovered ? Theme.fieldHoverSurface : Theme.fieldSurface)
            border.width: root.activeFocus ? Theme.px(2) : Theme.px(1)
            border.color: root.activeFocus ? Theme.focusColor : (root.hovered ? Theme.primary : Theme.borderSoft)
            opacity: root.enabled ? 1.0 : 0.62
            clip: true
            Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 120 } }
            Behavior on border.color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 120 } }

            Image {
                anchors.fill: parent
                visible: Theme.panelRefractionFile.length > 0
                source: visible ? assetRoot + "/" + Theme.panelRefractionFile : ""
                fillMode: Image.Tile
                opacity: Theme.panelRefractionOpacity * (root.activeFocus ? 0.30 : 0.16)
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
                height: parent.height * 0.28
                radius: Math.max(0, fieldChrome.radius - Theme.px(1))
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.72; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.activeFocus ? 0.34 : (root.hovered ? 0.26 : 0.18)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 120 } }
            }
        }
    }
}
