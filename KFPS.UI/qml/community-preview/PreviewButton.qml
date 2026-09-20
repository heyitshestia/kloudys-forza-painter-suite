import QtQuick
import Kfps.Theme 1.0
import "../components" as C

C.GhostButton {
    id: control
    property string hint: text
    property real iconRotation: 0
    readonly property string terminalGlyph: iconName === "arrow-up" ? (iconRotation === 180 ? "v" : "^")
                                            : iconName === "heart" ? "*"
                                            : iconName === "refresh" ? "R"
                                            : iconName === "chevron-left" ? "<"
                                            : iconName === "chevron-right" ? ">"
                                            : iconName === "folder" ? "[+]" : ""
    text: !Theme.iconGlyphsVisible ? terminalGlyph : ""
    readonly property bool iconOnly: iconName.length > 0
                                      && (!text.length || (!Theme.iconGlyphsVisible && text === terminalGlyph))
    toolTipText: hint
    labelColor: checkedState && !Theme.classicMode && Theme.controlSurfaceComponentFile.length === 0
                && Theme.navActiveMiddle.a >= 0.5
                ? Theme.primaryText : Theme.text
    Accessible.name: hint
    minimumWidth: Theme.px(iconOnly ? 36 : 64)
    implicitWidth: iconOnly ? Theme.px(36) : Math.max(minimumWidth, contentItem.implicitWidth + leftPadding + rightPadding)
    implicitHeight: Math.round(Theme.px(36))
    textPixelSize: Math.round(Theme.px(13))
    crispText: true
    dense: true
    Binding { target: control.contentItem; property: "rotation"; value: Theme.iconGlyphsVisible ? control.iconRotation : 0 }
}
