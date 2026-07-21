pragma Singleton
import QtQuick 6.7

QtObject {
    // The preferred launch size is fitted to the active screen by app.py.
    // Compact layouts stack and scroll down to the native resize minimum.
    readonly property int launchWidth: 1760
    readonly property int launchHeight: 1040
    readonly property int minWidth: 960
    readonly property int minHeight: 600

    // Shell dimensions in design units.
    readonly property real titleHeight: 30
    readonly property real wideSidebar: 205
    readonly property real compactSidebar: 104
    readonly property real headerHeight: 96
    readonly property real compactHeaderHeight: 78
    readonly property real consoleHeight: 178
    readonly property real compactConsoleHeight: 144
    readonly property real consoleCollapsedHeight: 50

    // General spacing and shape tokens.
    readonly property real gap: 12
    readonly property real gapCompact: 8
    readonly property real radius: 13
    readonly property real radiusLarge: 18
    readonly property real controlRadius: 8

    // Controls. Heights are minimums; controls grow if their font requires it.
    readonly property real fieldHeight: 40
    readonly property real buttonHeight: 38
    readonly property real denseButtonHeight: 30
    readonly property real navButtonHeight: 48
    readonly property real compactNavButtonHeight: 46
    readonly property real minimumTouchHeight: 30
}
