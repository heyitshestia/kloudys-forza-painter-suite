import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

TextField {
    id: root

    objectName: "KfpsTextField:" + root.placeholderText

    property bool dense: false
    property real minimumWidth: Theme.px(80)
    property string toolTipText: ""
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : placeholderText

    implicitHeight: Math.max(
                        Theme.px(dense ? Metrics.denseButtonHeight : Metrics.fieldHeight),
                        font.pixelSize * 1.35 + topPadding + bottomPadding)
    implicitWidth: Theme.px(150)
    Layout.minimumWidth: root.minimumWidth
    Layout.minimumHeight: root.implicitHeight

    leftPadding: Theme.px(dense ? 10 : 12)
    rightPadding: Theme.px(dense ? 10 : 12)
    topPadding: Theme.px(dense ? 5 : 7)
    bottomPadding: Theme.px(dense ? 5 : 7)
    color: Theme.text
    selectionColor: Theme.primary
    selectedTextColor: Theme.primaryText
    placeholderTextColor: Theme.subtle
    font.family: Theme.fontFamily
    font.pixelSize: Theme.px(dense ? 10.5 : 11.5)
    renderType: TextInput.NativeRendering
    font.hintingPreference: Font.PreferFullHinting
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    hoverEnabled: true
    clip: true

    KfpsToolTip {
        visible: root.hovered && !root.activeFocus && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }

    background: Item {
        Rectangle {
            id: fieldChrome
            anchors.fill: parent
            radius: Theme.framedRadius(Theme.px(Metrics.controlRadius))
            color: root.activeFocus ? Theme.fieldFocusSurface : (root.hovered ? Theme.fieldHoverSurface : Theme.fieldSurface)
            border.width: root.activeFocus
                          ? Theme.px(2)
                          : (Theme.customFrameExclusive ? 0 : Theme.px(1))
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
                opacity: Theme.panelRefractionOpacity * (root.activeFocus ? 0.32 : 0.18)
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
                radius: Math.max(0, fieldChrome.radius - Theme.px(1))
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.primaryButtonGlassTop }
                    GradientStop { position: 0.74; color: Theme.primaryButtonGlassMiddle }
                    GradientStop { position: 1.0; color: Theme.primaryButtonSheenTransparent }
                }
                opacity: root.activeFocus ? 0.38 : (root.hovered ? 0.30 : 0.20)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 120 } }
            }

            ControlStatusTicks {
                anchors.right: parent.right
                anchors.rightMargin: Theme.px(7)
                anchors.top: parent.top
                anchors.topMargin: Theme.px(3)
                activeState: root.activeFocus
                hoveredState: root.hovered
            }
        }
    }
}
