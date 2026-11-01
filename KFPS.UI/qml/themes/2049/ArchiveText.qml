import QtQuick 6.7
import Kfps.Theme 1.0

Text {
    color: Theme.text
    font.family: Theme.monoFamily
    font.pixelSize: Theme.px(13)
    font.letterSpacing: 0
    elide: Text.ElideRight
    renderType: Text.NativeRendering
    property bool phosphor: false
    style: phosphor ? Text.Outline : Text.Normal
    styleColor: Theme.withAlpha(Theme.signalSecondary, 0.25)
}
